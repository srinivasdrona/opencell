"""Shared fixture helpers for the L2.2 evidence-gate test suites
(test_l22_evidence_sweep.py, test_l22_evidence_generator.py,
test_l22_evidence_anticheat.py, test_l22_evidence_portability.py).

Since the Phase-A/R1-R2-R3 provenance hardening, evidence is only ever
considered valid/current when it carries the four mandatory sidecars
(thresholds.json/null_calibration.json/SUMMARY.json/analytical_check.json)
AND a tracked `sweep_provenance.json` completion sentinel whose
process/n_seeds/m_ticks/completion_status, per-sidecar-file sha256
(`sidecar_hashes`), source hashes (runner/helpers/projections/catalog +
this process's own oc_module), `result_schema_version` (the raw-evidence
field contract; gating), and `inputs_verified` attestation all match the
CURRENT tree/evidence -- the gating authority. Git SHA/dirty and
`evaluator_schema_version` (the mechanical re-derivation logic version) are
recorded for human inspection but are informational only, never gating (as
of v3 -- see `verdict.EVALUATOR_SCHEMA_VERSION`'s docstring). These helpers
build exactly that -- using the REAL current `sweep.current_source_hashes()`
/ `populate._git_sha` / `populate._git_dirty` /
`verdict.EVALUATOR_SCHEMA_VERSION` / `schema.RESULT_SCHEMA_VERSION`
-- so tests exercise the real staleness-detection code path rather than a
parallel hand-rolled one that could silently drift from it.

Run indirectly via any `bin\\oc-pytest tests/scripts/test_l22_evidence_*.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_evidence import (
    schema,  # noqa: E402
    sweep,  # noqa: E402
)
from scripts.l22_evidence import verdict as vd  # noqa: E402
from scripts.l22_evidence.populate import _git_dirty, _git_sha  # noqa: E402

# A real, always-tracked-in-git code file: used as the default
# input_manifest.json input so `write_full_valid_evidence` never needs a
# fake/synthetic path that would fail the "non-empty inputs, path+sha256
# must match the current tree" check (R3) by construction.
_DEFAULT_INPUT_PATH = "tests/vivarium/l2_2_design_a_runner.py"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_mandatory_sidecars(evidence_dir: Path) -> None:
    """Write minimal but validly-parseable copies of all four mandatory
    sidecars the runner unconditionally writes for every process."""
    _write_json(evidence_dir / "thresholds.json", {"channels": {}})
    _write_json(evidence_dir / "null_calibration.json", {"channels": {}})
    _write_json(evidence_dir / "SUMMARY.json", {"note": "fixture summary"})
    _write_json(evidence_dir / "analytical_check.json", {"applicable": False, "reason": "fixture"})


def default_input_records() -> list[dict[str, Any]]:
    """A single non-empty, real, hash-verifiable `input_manifest.json`
    input entry pointing at a tracked repo file (never a synthetic path),
    so it always passes `_check_current_tree_staleness`'s current-tree
    rehash regardless of whether raw oracle `.mat` data happens to be
    mounted on the machine running the tests."""
    return [{"path": _DEFAULT_INPUT_PATH, "sha256": sweep._sha256_file(REPO_ROOT / _DEFAULT_INPUT_PATH)}]


def compute_sidecar_hashes(evidence_dir: Path) -> dict[str, str]:
    """sha256 of every fixed R1-tracked authority/sidecar file as it
    ACTUALLY exists in `evidence_dir` right now -- the real
    `sweep.build_sweep_provenance`-equivalent computation, so tests exercise
    the real sentinel-binding hash rather than a hand-rolled stand-in."""
    hashes: dict[str, str] = {}
    for fname in schema.SWEEP_PROVENANCE_SIDECAR_FILES:
        digest = sweep._sha256_file(evidence_dir / fname)
        if digest is not None:
            hashes[fname] = digest
    return hashes


def valid_sweep_provenance_payload(
    *,
    process: str,
    n_seeds: int,
    m_ticks: int,
    oc_module: str | None = None,
    sidecar_hashes: dict[str, str] | None = None,
    inputs_verified: bool = True,
    harness_type: str | None = "design_a_per_tick",
) -> dict[str, Any]:
    """A `sweep_provenance.json` payload that will pass EVERY staleness
    check against the CURRENT tree (real current source hashes, real
    current `result_schema_version` -- the gating authority; git SHA and
    `evaluator_schema_version` are included for realism but are
    informational only) -- exactly what `sweep.build_sweep_provenance`
    would have produced right now.

    `harness_type` defaults to `"design_a_per_tick"` (every current caller
    exercises a design_a_per_tick fixture process); pass `"event_class"`
    (or `None`) explicitly for an event_class fixture so the F1
    harness-scoped `l2_replay_common` dependency is correctly NOT bound --
    matching `sweep.current_source_hashes`'s real production contract
    (`SweepJob.harness_type` is always `"design_a_per_tick"` by
    construction; see `plan_sweep`).

    `sidecar_hashes` should normally be computed via `compute_sidecar_hashes`
    from the SAME `evidence_dir` this sentinel is written into (see
    `write_valid_sweep_provenance`), so the sentinel genuinely binds to the
    evidence sitting next to it (R1) rather than passing by coincidence."""
    return {
        "schema_version": schema.SWEEP_PROVENANCE_SCHEMA_VERSION,
        "process": process,
        "n_seeds": n_seeds,
        "m_ticks": m_ticks,
        "completion_status": schema.COMPLETION_STATUS_COMPLETE,
        "git_sha": _git_sha(REPO_ROOT),
        "git_dirty": _git_dirty(REPO_ROOT),
        "source_hashes": sweep.current_source_hashes(oc_module, process=process, harness_type=harness_type),
        "sidecar_hashes": sidecar_hashes or {},
        "inputs_verified": inputs_verified,
        "evaluator_schema_version": vd.EVALUATOR_SCHEMA_VERSION,
        "result_schema_version": schema.RESULT_SCHEMA_VERSION,
        "written_at": "2026-01-01T00:00:00+00:00",
    }


def write_valid_sweep_provenance(
    evidence_dir: Path,
    *,
    process: str,
    n_seeds: int,
    m_ticks: int,
    oc_module: str | None = None,
    harness_type: str | None = "design_a_per_tick",
) -> None:
    """Write a `sweep_provenance.json` sentinel into `evidence_dir` whose
    `sidecar_hashes` are computed from whatever mandatory sidecar files
    ALREADY exist there right now -- call this AFTER writing every other
    evidence file (see `write_full_valid_evidence`), never before."""
    _write_json(
        evidence_dir / schema.SWEEP_PROVENANCE_FILE,
        valid_sweep_provenance_payload(
            process=process,
            n_seeds=n_seeds,
            m_ticks=m_ticks,
            oc_module=oc_module,
            sidecar_hashes=compute_sidecar_hashes(evidence_dir),
            harness_type=harness_type,
        ),
    )


def write_full_valid_evidence(
    evidence_dir: Path,
    *,
    process: str,
    seeds: int,
    m_ticks: int,
    verdict: str = "PASS",
    channels: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    result_overrides: dict[str, Any] | None = None,
    inputs: list[dict[str, Any]] | None = None,
    oc_module: str | None = None,
    harness_type: str | None = "design_a_per_tick",
) -> None:
    """Write a complete, currently-valid evidence directory: the three
    runner authority files, all four mandatory sidecars, and a real,
    current `sweep_provenance.json` completion sentinel. Used wherever a
    test needs `evidence_is_valid`/the generator to see fully-satisfied,
    non-stale evidence without invoking the real (slow) runner or `run_job`.

    `inputs` defaults to `default_input_records()` (a real, tracked,
    hash-verifiable file) rather than an empty list: since R3, an empty
    `input_manifest.json["inputs"]` is itself a failure condition, so a
    test that wants THAT failure must pass `inputs=[]` explicitly.
    """
    evidence_dir.mkdir(parents=True, exist_ok=True)
    expected_seeds = list(range(seeds))
    result = {
        "process": process,
        "verdict": verdict,
        "seeds": expected_seeds,
        "ticks": m_ticks,
        "channels": channels or {},
        "warnings": warnings or [],
    }
    if result_overrides:
        result.update(result_overrides)
    _write_json(evidence_dir / "result.json", result)
    _write_json(
        evidence_dir / "input_manifest.json",
        {
            "resolved_seeds": expected_seeds,
            "m_ticks": m_ticks,
            "inputs": default_input_records() if inputs is None else inputs,
        },
    )
    _write_json(evidence_dir / "provenance.json", {"generated_at": "2026-01-01T00:00:00+00:00", "git_sha": "unknown"})
    write_mandatory_sidecars(evidence_dir)
    write_valid_sweep_provenance(
        evidence_dir, process=process, n_seeds=seeds, m_ticks=m_ticks, oc_module=oc_module, harness_type=harness_type
    )
