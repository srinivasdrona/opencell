#!/usr/bin/env python3
"""Derive the canonical L2.5 scope: eligible-process set + minimal covering pair set.

This script exists to replace the ambiguous/stale L2.5 pair denominator with a
single, mechanically-derivable answer. It does **not** hand-copy any stored
verdict string. Every per-process eligibility fact is *re-derived live* on
each run from the same tracked/authoritative inputs the rest of the ladder
already trusts:

  * bit-identity (``bucket == DETERMINISTIC``) processes -> a fresh rerun of
    ``scripts/probe_l2_1_strict_rubric.audit_one_process`` (honest-mode L2.1
    replay; GENUINE is the only verdict that counts as "closed").
  * distributional (all other, ``in_scope_L2_2: true``) processes -> a fresh
    call to ``scripts.l22_evidence.generator.build_evidence_index()``
    (mechanical_verdict == PASS is the only verdict that counts as "closed";
    the tracked ``evidence_index.json`` is never read for this purpose).

The structural pair universe (WID-overlap classification, 378 total / 256
shared-pool pairs) is reused unmodified from ``scripts/derive_l25_pair_matrix``
-- that machinery is sound; only its ``l2_2_passed`` fallback field (which is
a scope flag in disguise, not a verdict) is discarded and replaced.

A "known short-circuit gap" overlay is computed by grepping each process's
``oc_module`` source for the literal token ``trace_hint`` (cross-referenced
against ``docs/phase_f/L2_5_SHORTCIRCUIT_AUDIT.md``, but re-verified live here
rather than trusted as a static list) -- a process flagged this way is never
eligible for *selection* even if its gate verdict is otherwise green, per the
"no known-gap waiver" rule.

Usage (always via the WSL wrapper -- see repo Copilot instructions):
    bin\\oc-py scripts/derive_l25_scope.py                 # regenerate + write + validate
    bin\\oc-py scripts/derive_l25_scope.py --check          # regenerate, diff vs tracked file, no write
    bin\\oc-py scripts/derive_l25_scope.py --out <path>     # write elsewhere (tests)

Exit code is 0 iff every required coverage class is covered by a selected
pair whose both processes are eligible and gap-free. Today's honest answer
is exit 1 (see docs/phase_f/L2_5_SCOPE_RATIFICATION.md) -- that is the
correct, disciplined, non-waived outcome, not a bug in this script.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = Path(__file__).resolve().parent
for _p in (_REPO, _SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import derive_l25_pair_matrix as pairmat  # noqa: E402 (flat sibling module)

from scripts.l22_evidence import generator as l22gen  # noqa: E402

DEFAULT_OUT = _REPO / "docs" / "phase_f" / "l2_5" / "L2_5_SCOPE_CATALOG.yaml"
SHORTCIRCUIT_AUDIT_DOC = "docs/phase_f/L2_5_SHORTCIRCUIT_AUDIT.md"
CANONICAL_STATE_GROUPS = pairmat.CANONICAL_STATE_GROUPS

L2_1_GATE_PASS_VERDICTS = frozenset({"GENUINE"})
L2_2_GATE_PASS_VERDICTS = frozenset({"PASS"})


@dataclass(frozen=True)
class ProcessVerdict:
    name: str
    bucket: str
    oracle_type: str
    oc_module: str | None
    gate_verdict: str
    gate_detail: dict[str, Any]
    eligible: bool
    known_short_circuit_gap: bool
    gap_reason: str | None

    @property
    def eligible_gap_free(self) -> bool:
        return self.eligible and not self.known_short_circuit_gap


def _load_raw_catalog_rows(catalog_path: Path) -> dict[str, dict[str, Any]]:
    """Minimal, single-purpose parse of PROCESS_CATALOG.yaml's `processes` list.

    Deliberately independent from scripts/l22_evidence/catalog.py's
    `in_scope_processes` (which only covers the 22 L2.2-in-scope rows): this
    script needs the ``oc_module`` and ``bucket`` fields for *all 28* rows.
    """
    data = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    rows = data.get("processes", [])
    if not isinstance(rows, list):
        raise ValueError("PROCESS_CATALOG.yaml must define a top-level list `processes`.")
    out: dict[str, dict[str, Any]] = {}
    for entry in rows:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        out[name] = entry
    return out


def _grep_known_short_circuit_gap(oc_module: str | None) -> tuple[bool, str | None]:
    """Mechanically re-check for a live `trace_hint` short-circuit reference.

    Heuristic (documented, not a certified gate): a literal `trace_hint`
    token in the process's own implementation module means the short-circuit
    bypass catalogued in L2_5_SHORTCIRCUIT_AUDIT.md is still present in code,
    independent of whether L2.1/L2.2 currently report green. If the token is
    ever removed from a module, this check clears automatically -- it is not
    a hardcoded process-name list.

    Fail-closed contract: when the module cannot be inspected at all (no
    `oc_module` declared, or the declared path does not exist on disk), this
    returns ``gap=True`` -- "cannot verify absence of a short-circuit" must
    never be silently treated the same as "verified clean". As of this
    writing all 28 catalog processes declare an existing `oc_module`, so this
    branch is currently dead in practice; it exists so a future catalog
    regression (a row losing its `oc_module`, or a module being deleted
    without updating the catalog) fails a process *out* of gap-free
    eligibility rather than silently clearing it.
    """
    if not oc_module:
        return True, "no oc_module declared in catalog; cannot verify absence of a short-circuit (failing closed)"
    module_path = _REPO / oc_module
    if not module_path.exists():
        return True, f"oc_module path does not exist: {oc_module} (failing closed)"
    text = module_path.read_text(encoding="utf-8", errors="replace")
    if "trace_hint" in text:
        return True, (
            f"live `trace_hint` reference found in {oc_module} "
            f"(cf. {SHORTCIRCUIT_AUDIT_DOC})"
        )
    return False, None


def _l2_1_verdict(name: str) -> tuple[str, dict[str, Any]]:
    """Fresh, live rerun of the honest-mode L2.1 strict rubric for one process."""
    try:
        import probe_l2_1_strict_rubric as l21probe
    except Exception as exc:  # pragma: no cover - import-time environment issue
        return "ERROR", {"error": f"import probe_l2_1_strict_rubric failed: {exc}"}

    result = l21probe.audit_one_process(name)
    if "error" in result:
        return "ERROR", result
    return str(result["verdict"]), result


def _l2_2_verdicts() -> dict[str, tuple[str, dict[str, Any]]]:
    """Fresh, live rebuild of the L2.2 mechanical evidence index (all in-scope rows).

    Never reads the tracked evidence_index.json -- calls the same builder the
    project's own audit tooling uses to detect STALE_VS_TREE, so a code
    change since the last committed snapshot downgrades the verdict here too.
    """
    try:
        payload = l22gen.build_evidence_index()
    except Exception as exc:  # pragma: no cover - environment/data dependency
        return {"__error__": ("ERROR", {"error": f"build_evidence_index failed: {exc}"})}
    out: dict[str, tuple[str, dict[str, Any]]] = {}
    for row in payload["rows"]:
        out[row["process"]] = (str(row["mechanical_verdict"]), row)
    return out


def derive_process_verdicts(catalog_rows: dict[str, dict[str, Any]]) -> list[ProcessVerdict]:
    l2_2_rows = _l2_2_verdicts()
    l2_2_error = l2_2_rows.pop("__error__", None)

    verdicts: list[ProcessVerdict] = []
    for name in sorted(catalog_rows):
        entry = catalog_rows[name]
        bucket = str(entry.get("bucket", "")).strip().upper()
        oracle_type = pairmat._oracle_type_for_process(entry)
        oc_module = str(entry.get("oc_module")) if entry.get("oc_module") else None
        gap, gap_reason = _grep_known_short_circuit_gap(oc_module)

        if oracle_type == "bit_identity":
            verdict, detail = _l2_1_verdict(name)
            eligible = verdict in L2_1_GATE_PASS_VERDICTS
        else:
            if l2_2_error is not None:
                verdict, detail = l2_2_error
            elif name not in l2_2_rows:
                verdict, detail = "NOT_IN_L2_2_SCOPE", {
                    "note": "catalog entry is not in_scope_L2_2 but oracle_type resolved "
                    "to distributional; treat as ineligible pending catalog review",
                }
            else:
                verdict, detail = l2_2_rows[name]
            eligible = verdict in L2_2_GATE_PASS_VERDICTS

        verdicts.append(
            ProcessVerdict(
                name=name,
                bucket=bucket,
                oracle_type=oracle_type,
                oc_module=oc_module,
                gate_verdict=verdict,
                gate_detail=detail,
                eligible=eligible,
                known_short_circuit_gap=gap,
                gap_reason=gap_reason,
            )
        )
    return verdicts


def _channels_present(pairs: list[pairmat.PairRecord], shared_pool_only: bool) -> set[str]:
    present: set[str] = set()
    for pair in pairs:
        if shared_pool_only and pair.classification != "shared_pool":
            continue
        for group in CANONICAL_STATE_GROUPS:
            if getattr(pair, f"{group}_overlap") > 0:
                present.add(group)
    return present


def _required_coverage_classes(shared_pool_pairs: list[pairmat.PairRecord]) -> list[tuple[str, str]]:
    """Coverage classes required *because they structurally exist* among the
    256 shared-pool pairs -- independent of current eligibility. A class only
    appears here if at least one structural shared-pool pair could satisfy it
    in principle; that keeps the obligation list itself mechanically derived
    (no fixed hand-authored list of "the 5 things we care about")."""
    classes: list[tuple[str, str]] = []
    complexities = sorted({p.pair_oracle_complexity for p in shared_pool_pairs})
    for c in complexities:
        classes.append(("oracle_complexity", c))
    tiers = sorted({p.tier for p in shared_pool_pairs})
    for t in tiers:
        classes.append(("contention_tier", str(t)))
    for group in sorted(_channels_present(shared_pool_pairs, shared_pool_only=True)):
        classes.append(("shared_wid_channel", group))
    return classes


def _class_predicate(cls: tuple[str, str], pair: pairmat.PairRecord) -> bool:
    kind, value = cls
    if kind == "oracle_complexity":
        return pair.pair_oracle_complexity == value
    if kind == "contention_tier":
        return str(pair.tier) == value
    if kind == "shared_wid_channel":
        return getattr(pair, f"{value}_overlap") > 0
    raise ValueError(f"unknown coverage class kind: {kind}")


def select_minimal_covering_set(
    shared_pool_pairs: list[pairmat.PairRecord],
    eligibility: dict[str, ProcessVerdict],
) -> dict[str, Any]:
    """Deterministic greedy set-cover over gap-free eligible pairs only.

    ``shared_pool_pairs`` is already sorted deterministically by
    ``derive_l25_pair_matrix._compute_pairs`` (tier priority, then
    -total_overlap, then process names) -- that pre-existing order is reused
    as the greedy candidate order so results are reproducible without a
    second sort here.
    """

    def is_eligible_pair(pair: pairmat.PairRecord) -> bool:
        a = eligibility.get(pair.process_a)
        b = eligibility.get(pair.process_b)
        return bool(a and b and a.eligible and b.eligible)

    def is_gap_free_pair(pair: pairmat.PairRecord) -> bool:
        a = eligibility.get(pair.process_a)
        b = eligibility.get(pair.process_b)
        return bool(a and b and a.eligible_gap_free and b.eligible_gap_free)

    eligible_pairs = [p for p in shared_pool_pairs if is_eligible_pair(p)]
    gap_free_pairs = [p for p in shared_pool_pairs if is_gap_free_pair(p)]

    required_classes = _required_coverage_classes(shared_pool_pairs)

    selected: list[pairmat.PairRecord] = []
    selected_keys: set[tuple[str, str]] = set()
    coverage_report: list[dict[str, Any]] = []

    for cls in required_classes:
        covering_selected = next((p for p in selected if _class_predicate(cls, p)), None)
        if covering_selected is not None:
            coverage_report.append(
                {
                    "class": {"kind": cls[0], "value": cls[1]},
                    "covered": True,
                    "covering_pair": [covering_selected.process_a, covering_selected.process_b],
                    "newly_selected": False,
                }
            )
            continue

        candidate = next((p for p in gap_free_pairs if _class_predicate(cls, p)), None)
        if candidate is not None:
            key = (candidate.process_a, candidate.process_b)
            if key not in selected_keys:
                selected.append(candidate)
                selected_keys.add(key)
            coverage_report.append(
                {
                    "class": {"kind": cls[0], "value": cls[1]},
                    "covered": True,
                    "covering_pair": [candidate.process_a, candidate.process_b],
                    "newly_selected": True,
                }
            )
            continue

        blocked_by_gap = next((p for p in eligible_pairs if _class_predicate(cls, p)), None)
        if blocked_by_gap is not None:
            coverage_report.append(
                {
                    "class": {"kind": cls[0], "value": cls[1]},
                    "covered": False,
                    "reason": "UNCOVERED_ONLY_VIA_KNOWN_GAP",
                    "blocking_pair": [blocked_by_gap.process_a, blocked_by_gap.process_b],
                }
            )
        else:
            coverage_report.append(
                {
                    "class": {"kind": cls[0], "value": cls[1]},
                    "covered": False,
                    "reason": "UNCOVERED_NO_ELIGIBLE_PAIR",
                }
            )

    selected.sort(key=lambda p: (p.process_a, p.process_b))
    # Deep-copy (not merely filter-reference) so the rendered YAML never
    # aliases dicts between `coverage_report` and `uncovered_classes` --
    # keeps the tracked artifact free of PyYAML anchor/alias noise.
    uncovered = [copy.deepcopy(row) for row in coverage_report if not row["covered"]]

    return {
        "required_classes": required_classes,
        "coverage_report": coverage_report,
        "selected_pairs": selected,
        "eligible_pairs": eligible_pairs,
        "gap_free_pairs": gap_free_pairs,
        "uncovered": uncovered,
    }


def _check_registry_integrity(
    catalog_rows: dict[str, dict[str, Any]],
    schemas: list[pairmat.ProcessSchema],
    all_pairs: list[pairmat.PairRecord],
) -> list[str]:
    """Hard structural sanity checks that must hold before eligibility and
    coverage obligations mean anything at all.

    A violation here means the *registry itself* has drifted -- a
    per-process TOML went missing or gained an unexpected name, or the
    WID-overlap pair universe no longer matches the structural
    ``378 total / 256 shared-pool / 122 disjoint`` scope block quoted
    verbatim from ``PROCESS_CATALOG.yaml`` in
    ``docs/phase_f/L2_5_SCOPE_RATIFICATION.md``. Any violation forces
    ``ok = False`` in ``build_payload`` regardless of the coverage outcome --
    a shrunk registry must never be allowed to silently shrink the required
    coverage classes (see ``_required_coverage_classes``, which only
    considers classes structurally present among the pairs it is given) and
    let a degenerate, under-populated case report ``ok=True``.
    """
    violations: list[str] = []
    catalog_names = set(catalog_rows)
    schema_names = {s.name for s in schemas}
    if catalog_names != schema_names:
        missing_schema = sorted(catalog_names - schema_names)
        extra_schema = sorted(schema_names - catalog_names)
        violations.append(
            "schema/catalog name-set mismatch: "
            f"missing_per_process_toml={missing_schema} extra_per_process_toml={extra_schema}"
        )
    if len(catalog_names) != 28:
        violations.append(f"catalog process count is {len(catalog_names)}, expected 28")
    if len(all_pairs) != 378:
        violations.append(f"total pair count is {len(all_pairs)}, expected C(28,2)=378")
    shared_pool_count = sum(1 for p in all_pairs if p.classification == "shared_pool")
    disjoint_count = sum(1 for p in all_pairs if p.classification == "disjoint")
    if shared_pool_count != 256:
        violations.append(f"structural shared-pool pair count is {shared_pool_count}, expected 256")
    if disjoint_count != 122:
        violations.append(f"structural disjoint pair count is {disjoint_count}, expected 122")
    return violations


def _pair_record_to_dict(pair: pairmat.PairRecord) -> dict[str, Any]:
    return {
        "process_a": pair.process_a,
        "process_b": pair.process_b,
        "tier": pair.tier,
        "pair_oracle_complexity": pair.pair_oracle_complexity,
        "total_overlap": pair.total_overlap,
        "overlap_by_channel": {
            group: getattr(pair, f"{group}_overlap") for group in CANONICAL_STATE_GROUPS
        },
    }


def build_payload() -> tuple[dict[str, Any], bool]:
    # Single authoritative catalog-path resolution, reused for both this
    # script's own raw-row parse and the pair/schema machinery below.
    # `derive_l25_pair_matrix._load_catalog`'s candidate-list precedence
    # (docs/phase_f/PROCESS_CATALOG.yaml, then
    # docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml) is resolved exactly
    # once here -- if a future docs/phase_f/PROCESS_CATALOG.yaml is ever
    # created, both derivations will agree on which file "the catalog" is
    # instead of a second, independently hardcoded path silently reading a
    # different file and creating split authority.
    catalog_lookup, catalog_path, _fallback_mode = pairmat._load_catalog(_REPO)
    catalog_rows = _load_raw_catalog_rows(catalog_path)
    verdicts = derive_process_verdicts(catalog_rows)
    eligibility = {v.name: v for v in verdicts}

    # Reuse the structural WID-overlap machinery unmodified, but override its
    # ambiguous `l2_2_passed` fallback field with our freshly-derived verdicts
    # before computing pairs (the field name is kept only because PairRecord
    # is a frozen dataclass we do not want to fork; its *meaning* here is
    # "freshly-derived eligible", not "has passed L2.2").
    schemas = pairmat._load_process_schemas(_REPO, catalog_lookup)
    # `.get(..., False)` rather than `[...]`: a schema whose name is not in
    # `eligibility` at all (extra/renamed per-process TOML) must not crash
    # payload construction -- it is instead caught and reported below by
    # `_check_registry_integrity`, which forces `ok=False` for exactly this
    # drift instead of letting a KeyError mask it or letting it silently
    # default to eligible.
    fresh_schemas = [
        replace(
            s,
            l2_2_passed=(eligibility[s.name].eligible if s.name in eligibility else False),
        )
        for s in schemas
    ]
    all_pairs = pairmat._compute_pairs(fresh_schemas)
    shared_pool_pairs = [p for p in all_pairs if p.classification == "shared_pool"]
    disjoint_pairs = [p for p in all_pairs if p.classification == "disjoint"]

    registry_violations = _check_registry_integrity(catalog_rows, schemas, all_pairs)

    selection = select_minimal_covering_set(shared_pool_pairs, eligibility)

    n_eligible = sum(1 for v in verdicts if v.eligible)
    n_eligible_gap_free = sum(1 for v in verdicts if v.eligible_gap_free)
    n_known_gap = sum(1 for v in verdicts if v.known_short_circuit_gap)

    ok = len(selection["uncovered"]) == 0 and len(verdicts) == 28 and not registry_violations

    try:
        catalog_source_desc = catalog_path.relative_to(_REPO).as_posix()
    except ValueError:
        # Defensive only (e.g. a test double resolves to a path outside
        # _REPO); production catalog_path is always _REPO-relative because
        # pairmat._load_catalog(_REPO) only ever joins _REPO with a
        # candidate-relative path.
        catalog_source_desc = str(catalog_path)

    payload: dict[str, Any] = {
        "schema_version": 1,
        "denominator": {
            "canonical_karr_process_count": 28,
            "source": (
                f"{catalog_source_desc} (processes list length; path resolved via "
                "derive_l25_pair_matrix._load_catalog's candidate precedence, the "
                "single authoritative catalog-path resolution)"
            ),
            "total_pairs_c_28_2": len(all_pairs),
            "structural_shared_pool_pairs": len(shared_pool_pairs),
            "structural_disjoint_pairs": len(disjoint_pairs),
        },
        "registry_integrity": {
            "ok": not registry_violations,
            "violations": registry_violations,
        },
        "eligibility_rule": {
            "bit_identity_bucket_deterministic": (
                "eligible iff a fresh scripts/probe_l2_1_strict_rubric.audit_one_process "
                "verdict == GENUINE (PARTIAL/COINCIDENTAL/UNINFORMATIVE/FAIL/ERROR are not eligible)"
            ),
            "distributional_bucket_stochastic": (
                "eligible iff a fresh scripts.l22_evidence.generator.build_evidence_index() "
                "row mechanical_verdict == PASS (the tracked evidence_index.json is never "
                "read for this determination)"
            ),
            "fail_closed_on_error": True,
        },
        "known_gap_overlay": {
            "method": (
                "live grep of each process's oc_module source for the literal token "
                "`trace_hint`; not a hardcoded process-name list"
            ),
            "reference": SHORTCIRCUIT_AUDIT_DOC,
        },
        "processes": [
            {
                "name": v.name,
                "bucket": v.bucket,
                "oracle_type": v.oracle_type,
                "oc_module": v.oc_module,
                "gate_verdict": v.gate_verdict,
                "eligible": v.eligible,
                "known_short_circuit_gap": v.known_short_circuit_gap,
                "gap_reason": v.gap_reason,
                "eligible_gap_free": v.eligible_gap_free,
            }
            for v in verdicts
        ],
        "pair_universe": {
            "total": len(all_pairs),
            "shared_pool": len(shared_pool_pairs),
            "disjoint": len(disjoint_pairs),
            "eligible_pairs": len(selection["eligible_pairs"]),
            "gap_free_eligible_pairs": len(selection["gap_free_pairs"]),
        },
        "coverage_classes": [
            {"kind": k, "value": val} for (k, val) in selection["required_classes"]
        ],
        "coverage_report": selection["coverage_report"],
        "selected_pairs": [_pair_record_to_dict(p) for p in selection["selected_pairs"]],
        "uncovered_classes": selection["uncovered"],
        "summary": {
            "n_eligible_processes": n_eligible,
            "n_eligible_gap_free_processes": n_eligible_gap_free,
            "n_known_gap_processes": n_known_gap,
            "n_selected_pairs": len(selection["selected_pairs"]),
            "n_uncovered_classes": len(selection["uncovered"]),
            "ok": ok,
        },
    }

    digest_source = _source_digest_for_hash(payload)
    payload["generated_at"] = pairmat._deterministic_generated_at(digest_source)
    payload["content_hash"] = _content_hash(payload)
    return payload, ok


def _source_digest_for_hash(payload_without_hash: dict[str, Any]) -> str:
    # Deterministic pseudo-source-digest derived from the payload's own
    # (order-stable) YAML rendering, so generated_at is content-derived
    # rather than wall-clock -- required for byte-stable double runs.
    rendered = yaml.safe_dump(payload_without_hash, sort_keys=True, default_flow_style=False)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _content_hash(payload: dict[str, Any]) -> str:
    scoped = copy.deepcopy(payload)
    scoped.pop("content_hash", None)
    scoped.pop("generated_at", None)
    rendered = yaml.safe_dump(scoped, sort_keys=True, default_flow_style=False)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


class _NoAliasDumper(yaml.SafeDumper):
    """Never emit YAML anchors/aliases -- keeps the tracked artifact fully
    inline and readable even if two rendered sub-dicts happen to be the same
    Python object in memory."""

    def ignore_aliases(self, data: Any) -> bool:
        return True


def render_yaml(payload: dict[str, Any]) -> str:
    return yaml.dump(
        payload, Dumper=_NoAliasDumper, sort_keys=False, default_flow_style=False, width=100
    )


def print_summary(payload: dict[str, Any]) -> None:
    d = payload["denominator"]
    s = payload["summary"]
    print("# L2.5 scope derivation")
    print(
        f"denominator: {d['canonical_karr_process_count']} canonical Karr processes, "
        f"C(28,2)={d['total_pairs_c_28_2']} total pairs, "
        f"{d['structural_shared_pool_pairs']} structurally shared-pool, "
        f"{d['structural_disjoint_pairs']} structurally disjoint"
    )
    registry = payload["registry_integrity"]
    if not registry["ok"]:
        print("REGISTRY INTEGRITY VIOLATIONS (registry/pair-universe drift detected):")
        for violation in registry["violations"]:
            print(f"  VIOLATION: {violation}")
    print(
        f"eligible processes: {s['n_eligible_processes']}/28 "
        f"({s['n_eligible_gap_free_processes']} gap-free, {s['n_known_gap_processes']} known-gap)"
    )
    print(
        f"pairs: {payload['pair_universe']['eligible_pairs']} eligible, "
        f"{payload['pair_universe']['gap_free_eligible_pairs']} gap-free-eligible, "
        f"{s['n_selected_pairs']} selected"
    )
    print(f"uncovered coverage classes: {s['n_uncovered_classes']}")
    for row in payload["uncovered_classes"]:
        print(f"  UNCOVERED {row['class']['kind']}={row['class']['value']}: {row['reason']}")
    print(f"result: {'OK' if s['ok'] else 'FAIL'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Regenerate in-memory and diff against --out without writing; nonzero exit on diff.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload, ok = build_payload()
    rendered = render_yaml(payload)
    print_summary(payload)

    if args.check:
        if not args.out.exists():
            print(f"CHECK FAILED: {args.out} does not exist")
            return 1
        existing = args.out.read_text(encoding="utf-8")
        if existing != rendered:
            print(f"CHECK FAILED: {args.out} is stale vs. fresh derivation")
            return 1
        print(f"CHECK OK: {args.out} matches fresh derivation byte-for-byte")
        return 0 if ok else 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
