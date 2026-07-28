"""Shared fixture helpers for the L2.2 evidence-gate test suites
(test_l22_evidence_sweep.py, test_l22_evidence_generator.py,
test_l22_evidence_anticheat.py, test_l22_evidence_portability.py).

Since the Phase-A provenance hardening, evidence is only ever considered
valid/current when it carries the four mandatory sidecars
(thresholds.json/null_calibration.json/SUMMARY.json/analytical_check.json)
AND a tracked `sweep_provenance.json` completion sentinel whose source
hashes (runner/helpers/projections/catalog) and evaluator schema version
match the CURRENT tree -- the gating authority. Git SHA/dirty are recorded
for human inspection but are informational only, never gating. These
helpers build exactly that -- using the REAL current
`sweep.current_source_hashes()` / `populate._git_sha` / `populate._git_dirty`
/ `verdict.EVALUATOR_SCHEMA_VERSION` -- so tests exercise the real
staleness-detection code path rather than a parallel hand-rolled one that
could silently drift from it.

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

from scripts.l22_evidence import schema  # noqa: E402
from scripts.l22_evidence import sweep  # noqa: E402
from scripts.l22_evidence import verdict as vd  # noqa: E402
from scripts.l22_evidence.populate import _git_dirty, _git_sha  # noqa: E402


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


def valid_sweep_provenance_payload(*, process: str, n_seeds: int, m_ticks: int) -> dict[str, Any]:
    """A `sweep_provenance.json` payload that will pass EVERY staleness
    check against the CURRENT tree (real current source hashes, real
    current evaluator schema version -- the gating authority; git SHA is
    included for realism but is informational only) -- exactly what
    `sweep.build_sweep_provenance` would have produced right now."""
    return {
        "schema_version": schema.SWEEP_PROVENANCE_SCHEMA_VERSION,
        "process": process,
        "n_seeds": n_seeds,
        "m_ticks": m_ticks,
        "git_sha": _git_sha(REPO_ROOT),
        "git_dirty": _git_dirty(REPO_ROOT),
        "source_hashes": sweep.current_source_hashes(),
        "evaluator_schema_version": vd.EVALUATOR_SCHEMA_VERSION,
        "written_at": "2026-01-01T00:00:00+00:00",
    }


def write_valid_sweep_provenance(evidence_dir: Path, *, process: str, n_seeds: int, m_ticks: int) -> None:
    _write_json(
        evidence_dir / schema.SWEEP_PROVENANCE_FILE,
        valid_sweep_provenance_payload(process=process, n_seeds=n_seeds, m_ticks=m_ticks),
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
) -> None:
    """Write a complete, currently-valid evidence directory: the three
    runner authority files, all four mandatory sidecars, and a real,
    current `sweep_provenance.json` completion sentinel. Used wherever a
    test needs `evidence_is_valid`/the generator to see fully-satisfied,
    non-stale evidence without invoking the real (slow) runner or `run_job`.
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
        {"resolved_seeds": expected_seeds, "m_ticks": m_ticks, "inputs": inputs or []},
    )
    _write_json(evidence_dir / "provenance.json", {"generated_at": "2026-01-01T00:00:00+00:00", "git_sha": "unknown"})
    write_mandatory_sidecars(evidence_dir)
    write_valid_sweep_provenance(evidence_dir, process=process, n_seeds=seeds, m_ticks=m_ticks)
