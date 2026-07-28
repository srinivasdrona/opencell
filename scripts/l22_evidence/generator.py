"""L2.2 evidence-index generator (generator-only; never hand-edit the output).

Reads ``docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml`` for scope and, for
every ``in_scope_L2_2`` process, looks for machine-produced runner evidence
under ``artifacts/l2_2_gates/<Process>/{latest,latest_event}/``. Emits one
row per process (never zero, never duplicated, never extra), mechanically
re-deriving the process verdict from raw channel numbers via
``scripts.l22_evidence.verdict`` -- the stored ``result.json["verdict"]``
string is never trusted as authority.

CLI:
    bin\\oc-py scripts/l22_evidence/generator.py generate [--out PATH]
    bin\\oc-py scripts/l22_evidence/generator.py audit [--index PATH] [--require-all-pass]

See ``docs/phase_f/l2_2_design_a/EVIDENCE_INDEX_SPEC.md`` for the full
contract, including why ``audit`` works by regenerating the index from
scratch and diffing against the tracked file rather than trusting anything
already written to disk.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_BOOTSTRAP))

from scripts.l22_evidence import catalog as cat  # noqa: E402
from scripts.l22_evidence import schema  # noqa: E402
from scripts.l22_evidence import verdict as vd  # noqa: E402


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "missing"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"unreadable: {exc}"


def _evidence_dir_for(entry: cat.ProcessEntry, evidence_root: Path) -> Path:
    subdir = schema.EVENT_CLASS_SUBDIR if entry.harness_type == "event_class" else schema.DESIGN_A_SUBDIR
    return evidence_root / entry.name / subdir


def _check_current_tree_staleness(input_manifest: dict[str, Any]) -> list[str]:
    """Recompute sha256 of every path input_manifest.json declares it consumed,
    as those files exist *right now* in the working tree, and flag any drift.

    This is what catches a committed evidence directory going stale after the
    catalog, the runner source, or an oracle .mat file changes underneath it.
    """
    reasons: list[str] = []
    for record in input_manifest.get("inputs", ()):
        path_str = record.get("path")
        recorded_sha = record.get("sha256")
        if not path_str or not recorded_sha:
            reasons.append(f"{schema.STATUS_STALE_VS_TREE}: malformed input_manifest record {record!r}")
            continue
        path = Path(str(path_str))
        if not path.is_absolute():
            path = cat.REPO_ROOT / path
        current_sha = _sha256_file(path)
        if current_sha is None:
            reasons.append(f"{schema.STATUS_STALE_VS_TREE}: input {path_str} no longer exists on disk")
        elif current_sha != recorded_sha:
            reasons.append(
                f"{schema.STATUS_STALE_VS_TREE}: input {path_str} sha256 changed since evidence was generated "
                f"(recorded={recorded_sha[:12]}.., current={current_sha[:12]}..)"
            )
    return reasons


def build_process_row(entry: cat.ProcessEntry, evidence_root: Path) -> dict[str, Any]:
    evidence_dir = _evidence_dir_for(entry, evidence_root)
    row: dict[str, Any] = {
        "process": entry.name,
        "bucket": entry.bucket,
        "harness_type": entry.harness_type,
        # High-sensitivity catalog soft flags. Hashing PROCESS_CATALOG.yaml
        # alone does not make these trustworthy -- see EVIDENCE_INDEX_SPEC.md
        # "soft flags" section. Supporting evidence (or its absence) is
        # surfaced via `reasons` below, not silently assumed.
        "catalog_soft_flags": {
            "harness_type": entry.harness_type,
            "N_seeds": entry.n_seeds,
            "M_ticks": entry.m_ticks,
            "primary_channel": entry.primary_channel,
            "closed_form_dominant": entry.closed_form_dominant,
            "primary_distance": entry.primary_distance,
            "in_scope_L2_2": True,
        },
        "evidence_dir": cat.relative_to_repo(evidence_dir),
        "reasons": [],
        "artifact_hashes": {},
    }

    missing_authority = [name for name in schema.REQUIRED_AUTHORITY_FILES if not (evidence_dir / name).is_file()]
    if missing_authority:
        row["reasons"].append(
            f"{schema.STATUS_MISSING_EVIDENCE}: missing required authority file(s) {missing_authority} "
            f"under {row['evidence_dir']}"
        )
        row["mechanical_verdict"] = schema.STATUS_MISSING_EVIDENCE
        row["green"] = False
        return row

    for fname in schema.REQUIRED_AUTHORITY_FILES + schema.OPTIONAL_SIDECAR_FILES:
        digest = _sha256_file(evidence_dir / fname)
        if digest is not None:
            row["artifact_hashes"][fname] = digest

    result_payload, result_err = _load_json(evidence_dir / "result.json")
    manifest_payload, manifest_err = _load_json(evidence_dir / "input_manifest.json")
    provenance_payload, provenance_err = _load_json(evidence_dir / "provenance.json")

    schema_reasons: list[str] = []
    for label, err in (
        ("result.json", result_err),
        ("input_manifest.json", manifest_err),
        ("provenance.json", provenance_err),
    ):
        if err:
            schema_reasons.append(f"{schema.STATUS_SCHEMA_INVALID}: {label} {err}")

    if result_payload is None or manifest_payload is None or provenance_payload is None:
        row["reasons"].extend(schema_reasons)
        row["mechanical_verdict"] = schema.STATUS_SCHEMA_INVALID
        row["green"] = False
        return row

    all_reasons: list[str] = list(schema_reasons)
    all_reasons.extend(_check_current_tree_staleness(manifest_payload))

    process_verdict = vd.rederive_process(entry.name, entry, result_payload)
    all_reasons.extend(process_verdict.reasons)
    row["channel_verdicts"] = process_verdict.channel_verdicts

    final_verdict = process_verdict.mechanical_verdict
    if all_reasons and final_verdict == schema.STATUS_PASS:
        # process_verdict itself saw no reasons, but staleness/schema checks
        # above did -- never let a row read PASS with open reasons attached.
        final_verdict = schema.STATUS_FAIL

    row["reasons"] = all_reasons
    row["mechanical_verdict"] = final_verdict
    row["green"] = final_verdict == schema.STATUS_PASS
    row["provenance_git_sha"] = provenance_payload.get("git_sha")
    return row


def build_evidence_index(
    *,
    evidence_root: Path = schema.EVIDENCE_ROOT,
    catalog_path: Path = schema.CATALOG_PATH,
) -> dict[str, Any]:
    entries = cat.in_scope_processes(catalog_path)
    rows = [build_process_row(entries[name], evidence_root) for name in sorted(entries)]

    tally: dict[str, int] = {}
    for row in rows:
        tally[row["mechanical_verdict"]] = tally.get(row["mechanical_verdict"], 0) + 1

    aggregate_verdict = "GREEN" if rows and all(row["green"] for row in rows) else "NON_GREEN"

    payload: dict[str, Any] = {
        "schema_version": schema.SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "catalog_path": cat.relative_to_repo(catalog_path),
        "catalog_sha256": cat.catalog_sha256(catalog_path),
        "evidence_root": cat.relative_to_repo(evidence_root),
        "n_in_scope": len(rows),
        "aggregate_verdict": aggregate_verdict,
        "tally": tally,
        "rows": rows,
    }
    payload["content_hash"] = content_hash(payload)
    return payload


def content_hash(payload: dict[str, Any]) -> str:
    """Deterministic content hash, excluding `generated_at` and itself.

    Two calls to build_evidence_index() against an unchanged tree/catalog
    must produce identical content_hash values even though `generated_at`
    differs between calls.
    """
    scrubbed = copy.deepcopy(payload)
    scrubbed.pop("generated_at", None)
    scrubbed.pop("content_hash", None)
    canonical = json.dumps(scrubbed, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def write_index(payload: dict[str, Any], path: Path = schema.INDEX_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass
class AuditResult:
    ok: bool
    aggregate_verdict: str
    tally: dict[str, int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def _strip_volatile(payload: dict[str, Any]) -> dict[str, Any]:
    scrubbed = copy.deepcopy(payload)
    scrubbed.pop("generated_at", None)
    scrubbed.pop("content_hash", None)
    return scrubbed


def audit(
    *,
    index_path: Path = schema.INDEX_PATH,
    evidence_root: Path = schema.EVIDENCE_ROOT,
    catalog_path: Path = schema.CATALOG_PATH,
) -> AuditResult:
    """Integrity check: does the tracked index match a fresh regeneration?

    This is the sole tamper/staleness defense: rather than trusting the
    stored index's own internal fields, `audit` rebuilds the index from
    scratch (mechanically re-deriving every verdict from raw evidence, per
    `verdict.rederive_process`) and diffs it against what's tracked on disk.
    Any hand-edit, stale commit, missing/extra row, or forged content_hash
    shows up as a mismatch here -- integrity can PASS even when the
    aggregate verdict is NON_GREEN (that's the honest, expected state before
    process closure); integrity FAILS only when the tracked file has drifted
    from the truth.
    """
    problems: list[str] = []
    if not index_path.is_file():
        return AuditResult(ok=False, aggregate_verdict="NON_GREEN", problems=[f"{index_path} does not exist; run `generate` first"])

    try:
        stored = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return AuditResult(ok=False, aggregate_verdict="NON_GREEN", problems=[f"stored index is not valid JSON: {exc}"])

    fresh = build_evidence_index(evidence_root=evidence_root, catalog_path=catalog_path)

    if _strip_volatile(stored) != _strip_volatile(fresh):
        problems.append(
            "stored evidence_index.json does not match a fresh regeneration from the current catalog + "
            "evidence tree (hand-edited, stale, or tampered). Run `generate` and commit the refreshed index."
        )
        stored_processes = {row.get("process") for row in stored.get("rows", ())}
        fresh_processes = {row["process"] for row in fresh["rows"]}
        if stored_processes != fresh_processes:
            problems.append(
                f"row-set mismatch: stored has extra {sorted(stored_processes - fresh_processes)}, "
                f"missing {sorted(fresh_processes - stored_processes)}"
            )
        recorded_hash = stored.get("content_hash")
        if recorded_hash and recorded_hash != content_hash(stored):
            problems.append("stored content_hash does not match the stored payload (index was edited after hashing)")

    return AuditResult(
        ok=not problems,
        aggregate_verdict=fresh["aggregate_verdict"],
        tally=fresh["tally"],
        problems=problems,
    )


def _cmd_generate(args: argparse.Namespace) -> int:
    payload = build_evidence_index(evidence_root=Path(args.evidence_root), catalog_path=Path(args.catalog))
    out_path = Path(args.out)
    write_index(payload, out_path)
    print(f"wrote {out_path} ({payload['n_in_scope']} rows, aggregate={payload['aggregate_verdict']})")
    for status, count in sorted(payload["tally"].items()):
        print(f"  {status}: {count}")
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    result = audit(index_path=Path(args.index), evidence_root=Path(args.evidence_root), catalog_path=Path(args.catalog))
    print(f"integrity: {'OK' if result.ok else 'FAIL'}")
    print(f"aggregate_verdict (mechanically re-derived): {result.aggregate_verdict}")
    for status, count in sorted(result.tally.items()):
        print(f"  {status}: {count}")
    for problem in result.problems:
        print(f"PROBLEM: {problem}")

    if not result.ok:
        return 1
    if args.require_all_pass and result.aggregate_verdict != "GREEN":
        print("--require-all-pass: aggregate verdict is not GREEN; this is the acceptance gate, not yet activated in CI")
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Regenerate evidence_index.json from the catalog + evidence tree.")
    gen.add_argument("--out", default=str(schema.INDEX_PATH))
    gen.add_argument("--evidence-root", default=str(schema.EVIDENCE_ROOT))
    gen.add_argument("--catalog", default=str(schema.CATALOG_PATH))
    gen.set_defaults(func=_cmd_generate)

    aud = sub.add_parser("audit", help="Verify the tracked evidence_index.json is truthful and untampered.")
    aud.add_argument("--index", default=str(schema.INDEX_PATH))
    aud.add_argument("--evidence-root", default=str(schema.EVIDENCE_ROOT))
    aud.add_argument("--catalog", default=str(schema.CATALOG_PATH))
    aud.add_argument(
        "--require-all-pass",
        action="store_true",
        help="Acceptance gate: exit nonzero unless every in-scope process is GREEN. "
        "Expected to fail (exit 2) until process closure; not yet wired into CI.",
    )
    aud.set_defaults(func=_cmd_audit)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
