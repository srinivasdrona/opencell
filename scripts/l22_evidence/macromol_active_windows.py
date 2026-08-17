"""Process-local ordinary Design-A verdict for MacromolecularComplexation.

This module keeps the active-window closeout local to MacromolecularComplexation:

1. validate the genuine-provider active-window cohort under
   `data/m1_sources/karr_native/macromol_active_window/`;
2. temporarily route ONLY MacromolecularComplexation's Design-A oracle loader
   to that cohort in-process, without editing shared helper files;
3. run the ordinary shared Design-A runner; and
4. emit a portable process-local artifact that binds the cohort hashes, runner
   source hashes, fixture/source/driver hashes, and the ordinary runner verdict.

The resulting artifact is intentionally NOT consumed by the shared evidence
index or generator until an explicit promotion step lands elsewhere.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_extraction import macromol_active_window as maw  # noqa: E402
from tests.vivarium import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402
from tests.vivarium import l2_2_design_a_runner as runner  # noqa: E402

PROCESS = maw.PROCESS_NAME
ARTIFACT_KIND = "macromol_active_window_process_local_design_a"
ARTIFACT_VERSION = "1.0.0"
GENERATOR_SOURCE_PATH = "scripts/l22_evidence/macromol_active_windows.py"
RUNNER_SOURCE_PATH = "tests/vivarium/l2_2_design_a_runner.py"
RUNNER_HELPERS_SOURCE_PATH = "tests/vivarium/_l2_2_design_a_runner_helpers.py"
DEFAULT_RUN_OUTPUT_DIR = REPO_ROOT / "artifacts" / "l22_macromol_genuine_design_a" / "latest"
DEFAULT_OUT_PATH = (
    REPO_ROOT
    / "docs"
    / "phase_f"
    / "l2_2_design_a"
    / "active_windows"
    / "MacromolecularComplexation_genuine_provider_design_a.json"
)
EXPECTED_NOT_CONSUMED_BY = [
    "scripts/l22_evidence/verdict.py",
    "scripts/l22_evidence/generator.py",
    "docs/phase_f/l2_2_design_a/evidence_index.json",
    "docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml",
]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_lf_normalized(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def _path_for_record(path: Path | str) -> str:
    raw = Path(path)
    try:
        return raw.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(raw)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_runner_payloads(raw_result: dict[str, Any], raw_summary: dict[str, Any], raw_thresholds: dict[str, Any], raw_null: dict[str, Any], raw_analytical: dict[str, Any], raw_manifest: dict[str, Any], raw_provenance: dict[str, Any], run_output_dir: Path) -> dict[str, Any]:
    result = deepcopy(raw_result)
    result["allocator_inputs_ref"] = _path_for_record(run_output_dir / "allocator_inputs.json")
    result["provenance_ref"] = _path_for_record(run_output_dir / "provenance.json")

    manifest = deepcopy(raw_manifest)
    for entry in manifest.get("inputs", []):
        if "path" in entry:
            entry["path"] = _path_for_record(entry["path"])

    provenance = deepcopy(raw_provenance)
    oracle_path = provenance.get("oracle_path")
    if isinstance(oracle_path, str):
        provenance["oracle_path"] = _path_for_record(oracle_path)

    return {
        "result": result,
        "summary": deepcopy(raw_summary),
        "thresholds": deepcopy(raw_thresholds),
        "null_calibration": deepcopy(raw_null),
        "analytical_check": deepcopy(raw_analytical),
        "input_manifest": manifest,
        "provenance": provenance,
    }


@contextmanager
def process_local_oracle_root(data_root: Path) -> Iterator[None]:
    original_seed_mat_path = runner_helpers._v2_seed_mat_path  # noqa: SLF001

    def patched_seed_mat_path(process_name: str, seed: int) -> Path:
        if process_name == PROCESS:
            return maw._seed_trace_path(int(seed), data_root)  # noqa: SLF001
        return original_seed_mat_path(process_name, seed)

    runner_helpers._v2_seed_mat_path = patched_seed_mat_path  # type: ignore[assignment]  # noqa: SLF001
    try:
        yield
    finally:
        runner_helpers._v2_seed_mat_path = original_seed_mat_path  # type: ignore[assignment]  # noqa: SLF001


def build_process_local_artifact(
    *,
    data_root: Path = maw.ACTIVE_WINDOW_ROOT,
    run_output_dir: Path = DEFAULT_RUN_OUTPUT_DIR,
    bootstrap_B: int = runner.DEFAULT_BOOTSTRAP_B,
) -> dict[str, Any]:
    audit = maw.audit_active_window_evidence(data_roots=(data_root,))
    if audit.status != "SUFFICIENT_ENSEMBLE":
        raise ValueError(
            "active-window cohort is not complete enough for an ordinary Design-A verdict: "
            f"{audit.status} deficit={audit.deficit}"
        )

    valid_windows = {
        str(seed): maw.validate_seed_window(seed, maw._seed_trace_path(seed, data_root)).to_dict()  # noqa: SLF001
        for seed in range(maw.REQUIRED_N_SEEDS)
    }
    seed_trace_sha256 = {seed: window["sha256"] for seed, window in valid_windows.items()}

    run_output_dir.mkdir(parents=True, exist_ok=True)
    with process_local_oracle_root(data_root):
        runner_payload = runner.run_design_a(
            process=PROCESS,
            seeds=list(range(maw.REQUIRED_N_SEEDS)),
            m_ticks=maw.REQUIRED_M_TICKS,
            out_dir=run_output_dir,
            bootstrap_B=bootstrap_B,
        )

    raw_summary = _load_json(run_output_dir / "SUMMARY.json")
    raw_thresholds = _load_json(run_output_dir / "thresholds.json")
    raw_null = _load_json(run_output_dir / "null_calibration.json")
    raw_analytical = _load_json(run_output_dir / "analytical_check.json")
    raw_manifest = _load_json(run_output_dir / "input_manifest.json")
    raw_provenance = _load_json(run_output_dir / "provenance.json")
    normalized_runner = _normalize_runner_payloads(
        runner_payload["result"],
        raw_summary,
        raw_thresholds,
        raw_null,
        raw_analytical,
        raw_manifest,
        raw_provenance,
        run_output_dir,
    )

    artifact = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_version": ARTIFACT_VERSION,
        "process": PROCESS,
        "gating": (
            "PROCESS_LOCAL ordinary Design-A verdict only; not consumed by the shared evidence index or generator "
            "without an explicit promotion step."
        ),
        "not_consumed_by": list(EXPECTED_NOT_CONSUMED_BY),
        "generated_at": datetime.now(UTC).isoformat(),
        "generator_source_path": GENERATOR_SOURCE_PATH,
        "generator_source_sha256_lf_normalized": _sha256_lf_normalized(REPO_ROOT / GENERATOR_SOURCE_PATH),
        "runner_source_path": RUNNER_SOURCE_PATH,
        "runner_source_sha256_lf_normalized": _sha256_lf_normalized(REPO_ROOT / RUNNER_SOURCE_PATH),
        "runner_helpers_source_path": RUNNER_HELPERS_SOURCE_PATH,
        "runner_helpers_source_sha256_lf_normalized": _sha256_lf_normalized(REPO_ROOT / RUNNER_HELPERS_SOURCE_PATH),
        "active_window_root": _path_for_record(data_root),
        "active_window_driver_path": _path_for_record(maw.MATLAB_DRIVER),
        "active_window_driver_sha256_lf_normalized": _sha256_lf_normalized(maw.MATLAB_DRIVER),
        "fixture_path": _path_for_record(maw.FIXTURE_PATH),
        "fixture_sha256": _sha256_file(maw.FIXTURE_PATH),
        "vendored_source_path": _path_for_record(maw.VENDORED_SOURCE_PATH),
        "vendored_source_sha256_lf_normalized": _sha256_lf_normalized(maw.VENDORED_SOURCE_PATH),
        "audit": audit.to_dict(),
        "seed_windows_verified": valid_windows,
        "seed_trace_sha256": seed_trace_sha256,
        "runner_output_dir": _path_for_record(run_output_dir),
        "runner_output_hashes": {
            name: _sha256_file(run_output_dir / name)
            for name in (
                "result.json",
                "SUMMARY.json",
                "thresholds.json",
                "null_calibration.json",
                "analytical_check.json",
                "input_manifest.json",
                "provenance.json",
            )
        },
        "ordinary_design_a": normalized_runner,
    }
    return artifact


def validate_process_local_artifact(payload: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> str | None:
    if payload.get("artifact_kind") != ARTIFACT_KIND:
        return f"artifact_kind != {ARTIFACT_KIND!r} (got {payload.get('artifact_kind')!r})"
    if payload.get("artifact_version") != ARTIFACT_VERSION:
        return f"artifact_version != {ARTIFACT_VERSION!r} (got {payload.get('artifact_version')!r})"
    if payload.get("process") != PROCESS:
        return f"process != {PROCESS!r} (got {payload.get('process')!r})"
    if payload.get("not_consumed_by") != EXPECTED_NOT_CONSUMED_BY:
        return "not_consumed_by drifted from the pinned process-local isolation contract"

    if payload.get("generator_source_path") != GENERATOR_SOURCE_PATH:
        return f"generator_source_path != {GENERATOR_SOURCE_PATH!r}"
    if payload.get("generator_source_sha256_lf_normalized") != _sha256_lf_normalized(repo_root / GENERATOR_SOURCE_PATH):
        return "generator_source_sha256_lf_normalized is stale/tampered"
    if payload.get("runner_source_path") != RUNNER_SOURCE_PATH:
        return f"runner_source_path != {RUNNER_SOURCE_PATH!r}"
    if payload.get("runner_source_sha256_lf_normalized") != _sha256_lf_normalized(repo_root / RUNNER_SOURCE_PATH):
        return "runner_source_sha256_lf_normalized is stale/tampered"
    if payload.get("runner_helpers_source_path") != RUNNER_HELPERS_SOURCE_PATH:
        return f"runner_helpers_source_path != {RUNNER_HELPERS_SOURCE_PATH!r}"
    if payload.get("runner_helpers_source_sha256_lf_normalized") != _sha256_lf_normalized(repo_root / RUNNER_HELPERS_SOURCE_PATH):
        return "runner_helpers_source_sha256_lf_normalized is stale/tampered"

    if payload.get("active_window_driver_path") != _path_for_record(maw.MATLAB_DRIVER):
        return "active_window_driver_path drifted from the tracked extractor path"
    if payload.get("active_window_driver_sha256_lf_normalized") != _sha256_lf_normalized(maw.MATLAB_DRIVER):
        return "active_window_driver_sha256_lf_normalized is stale/tampered"
    if payload.get("fixture_path") != _path_for_record(maw.FIXTURE_PATH):
        return "fixture_path drifted from the tracked fixture path"
    if payload.get("fixture_sha256") != _sha256_file(maw.FIXTURE_PATH):
        return "fixture_sha256 is stale/tampered"
    if payload.get("vendored_source_path") != _path_for_record(maw.VENDORED_SOURCE_PATH):
        return "vendored_source_path drifted from the tracked vendored-source path"
    if payload.get("vendored_source_sha256_lf_normalized") != _sha256_lf_normalized(maw.VENDORED_SOURCE_PATH):
        return "vendored_source_sha256_lf_normalized is stale/tampered"

    audit = payload.get("audit") or {}
    if audit.get("status") != "SUFFICIENT_ENSEMBLE":
        return f"audit.status must be 'SUFFICIENT_ENSEMBLE' (got {audit.get('status')!r})"

    seed_hashes = payload.get("seed_trace_sha256")
    seed_windows = payload.get("seed_windows_verified")
    if not isinstance(seed_hashes, dict) or not isinstance(seed_windows, dict):
        return "seed_trace_sha256 / seed_windows_verified missing or invalid"
    if set(seed_hashes) != set(seed_windows):
        return "seed_trace_sha256 and seed_windows_verified keys are not aligned"
    for seed_text, recorded_hash in seed_hashes.items():
        seed = int(seed_text)
        path = maw._seed_trace_path(seed, repo_root / payload["active_window_root"])  # noqa: SLF001
        if not path.is_file():
            return f"seed {seed} trace missing on disk: {_path_for_record(path)}"
        current_hash = _sha256_file(path)
        if current_hash != recorded_hash:
            return f"seed {seed} trace hash stale/tampered"

    ordinary = payload.get("ordinary_design_a") or {}
    result = ordinary.get("result") or {}
    if result.get("process") != PROCESS:
        return f"ordinary_design_a.result.process != {PROCESS!r}"
    if result.get("verdict") not in {"PASS", "FAIL", "NO_GATEABLE_CHANNELS"}:
        return f"ordinary_design_a.result.verdict is unexpected: {result.get('verdict')!r}"

    runner_output_dir = repo_root / payload.get("runner_output_dir", "")
    recorded_output_hashes = payload.get("runner_output_hashes") or {}
    for name, recorded_hash in recorded_output_hashes.items():
        path = runner_output_dir / name
        if not path.is_file():
            return f"runner output missing on disk: {_path_for_record(path)}"
        if _sha256_file(path) != recorded_hash:
            return f"runner output hash stale/tampered for {name}"

    return None


def write_artifact(payload: dict[str, Any], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=maw.ACTIVE_WINDOW_ROOT)
    parser.add_argument("--run-output-dir", type=Path, default=DEFAULT_RUN_OUTPUT_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH)
    parser.add_argument("--bootstrap-B", type=int, default=runner.DEFAULT_BOOTSTRAP_B)
    args = parser.parse_args(argv)

    artifact = build_process_local_artifact(
        data_root=args.data_root,
        run_output_dir=args.run_output_dir,
        bootstrap_B=args.bootstrap_B,
    )
    write_artifact(artifact, args.out)
    validation_error = validate_process_local_artifact(artifact)
    if validation_error is not None:
        print(f"[macromol-active-windows] self-validation failed: {validation_error}", file=sys.stderr)
        return 2

    print(
        f"[macromol-active-windows] verdict={artifact['ordinary_design_a']['result']['verdict']} "
        f"seeds={artifact['audit']['required_n_seeds']} -> {args.out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
