"""Tests for the real N=50/M=200 RibosomeAssembly event-class evidence
pipeline (``scripts/l2_event/ribosome_assembly_seed_audit.py`` +
``scripts/l2_event/ribosome_assembly_n50_gate.py``).

Distinct from ``test_l2_event_ribosome_assembly_gate.py`` (pure adapter
unit tests + synthetic 50-seed cohorts + the real seed-0-only structural
round-trip): this file is scoped to the two NEW process-local drivers this
task adds on top of that existing, unmodified adapter -- the seed audit
(never mutates a trace file; refuses to certify N=50 unless every seed is
individually hash-bound-valid AND non-aliased across seeds) and the real
gate computation (builds real 50-seed Karr/OC EventTimelines from the
now-complete on-disk cohort and calls the real
``scripts.l2_event.runner.evaluate_gate``, never a synthetic/hand-built
cohort).

Real-data tests are skipped (never xfail/error) when the local, gitignored
50-seed cohort is not present -- e.g. a fresh clone with no MATLAB
extraction ever run. The audit's OWN malformed-input refusal tests need no
real data and always run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l2_event.launcher import KARR_NATIVE_ROOT, event_window_mat_path  # noqa: E402
from scripts.l2_event.ribosome_assembly_n50_gate import (  # noqa: E402
    GateRunRefused,
    run_real_n50_gate,
)
from scripts.l2_event.ribosome_assembly_seed_audit import (  # noqa: E402
    DEFAULT_SPECS_PATH,
    REQUIRED_N_SEEDS,
    SeedAuditError,
    audit_ribosome_assembly_n50_seeds,
)
from scripts.l2_event.runner import RunnerRefusal  # noqa: E402

_SPECS_PATH = DEFAULT_SPECS_PATH


def _all_50_real_seeds_present() -> bool:
    """Existence-only pre-check for skipif (the tests themselves exercise
    the REAL validation -- this is deliberately not a substitute for it)."""
    if not _SPECS_PATH.exists():
        return False
    for seed in range(REQUIRED_N_SEEDS):
        path = event_window_mat_path("RibosomeAssembly", seed, n_ticks=100, karr_native_root=KARR_NATIVE_ROOT)
        if not path.exists():
            return False
    return True


_ALL_50_PRESENT = _all_50_real_seeds_present()

_missing_reason = "Full 50-seed RibosomeAssembly event-window cohort not present locally"


# ---------------------------------------------------------------------------
# Seed audit -- malformed-input refusal (no real data required)
# ---------------------------------------------------------------------------


def test_seed_audit_raises_on_wrong_seed_count(tmp_path):
    specs = [
        {
            "process": "RibosomeAssembly",
            "seed": i,
            "window_contract": "fixed",
            "tick_offset": 200,
            "n_ticks": 100,
            "required_observables": ["substrates", "monomers", "complexs", "RNAs"],
        }
        for i in range(49)
    ]
    specs_path = tmp_path / "specs.json"
    specs_path.write_text(json.dumps(specs), encoding="utf-8")

    with pytest.raises(SeedAuditError, match="expected exactly 50"):
        audit_ribosome_assembly_n50_seeds(specs_path, karr_native_root=tmp_path)


def test_seed_audit_raises_on_non_contiguous_seed_set(tmp_path):
    """50 rows, but seed 7 is duplicated and seed 49 is missing -- a
    caller error distinct from merely having the wrong COUNT."""
    seed_values = [i for i in range(49)] + [7]
    specs = [
        {
            "process": "RibosomeAssembly",
            "seed": s,
            "window_contract": "fixed",
            "tick_offset": 200,
            "n_ticks": 100,
            "required_observables": ["substrates", "monomers", "complexs", "RNAs"],
        }
        for s in seed_values
    ]
    specs_path = tmp_path / "specs.json"
    specs_path.write_text(json.dumps(specs), encoding="utf-8")

    with pytest.raises(SeedAuditError, match="expected seeds 0..49"):
        audit_ribosome_assembly_n50_seeds(specs_path, karr_native_root=tmp_path)


def test_seed_audit_reports_all_missing_when_no_trace_files_exist(tmp_path):
    """A well-formed 50-row spec list against an empty directory must
    report every seed invalid (missing), never crash, and
    `all_seeds_valid` must be False -- the honest "0 of 50" report this
    task's fallback-reporting requirement depends on."""
    specs = [
        {
            "process": "RibosomeAssembly",
            "seed": i,
            "window_contract": "fixed",
            "tick_offset": 200,
            "n_ticks": 100,
            "required_observables": ["substrates", "monomers", "complexs", "RNAs"],
        }
        for i in range(50)
    ]
    specs_path = tmp_path / "specs.json"
    specs_path.write_text(json.dumps(specs), encoding="utf-8")

    report = audit_ribosome_assembly_n50_seeds(specs_path, karr_native_root=tmp_path)
    assert report["all_seeds_valid"] is False
    assert report["n_seeds_valid"] == 0
    assert report["n_seeds_total"] == 50
    assert all(not row["ok"] for row in report["per_seed"])


def test_seed_audit_detects_a_byte_identical_aliased_seed_pair(tmp_path):
    """The exact failure mode this task's pre-mortem names: two "seeds"
    that are actually one physical file copy-pasted under two seed
    directories must be refused (`all_seeds_valid=False`) even though a
    naive existence-only check would count both as present. This uses
    real (unvalidatable-as-fixed-window) placeholder bytes -- the point is
    the CONTENT-HASH cross-check, not the M4 structural validation (which
    real seed files exercise via the skipif-guarded real-cohort test
    below)."""
    specs = [
        {
            "process": "RibosomeAssembly",
            "seed": i,
            "window_contract": "fixed",
            "tick_offset": 200,
            "n_ticks": 100,
            "required_observables": ["substrates", "monomers", "complexs", "RNAs"],
        }
        for i in range(50)
    ]
    specs_path = tmp_path / "specs.json"
    specs_path.write_text(json.dumps(specs), encoding="utf-8")

    # Seeds 0 and 1 share byte-identical (bogus) content; every other seed
    # has no file at all. Neither seed 0 nor seed 1 will pass the real
    # window-loader validation (not a real HDF5/.mat file), so
    # `validate_existing_event_window` already reports both `ok=False` --
    # this test's job is only to prove the duplicate-hash bookkeeping
    # itself does not crash and does not silently mark either as valid.
    for seed in (0, 1):
        out_dir = tmp_path / f"per_process_traces_v2_event_s{seed:03d}"
        out_dir.mkdir(parents=True)
        (out_dir / "RibosomeAssembly_100ticks.mat").write_bytes(b"not a real mat file, deliberately identical")

    report = audit_ribosome_assembly_n50_seeds(specs_path, karr_native_root=tmp_path)
    assert report["all_seeds_valid"] is False
    seed0_row = next(r for r in report["per_seed"] if r["seed"] == 0)
    seed1_row = next(r for r in report["per_seed"] if r["seed"] == 1)
    assert seed0_row["sha256"] == seed1_row["sha256"]
    assert seed0_row["ok"] is False
    assert seed1_row["ok"] is False


# ---------------------------------------------------------------------------
# Real 50-seed cohort (skipped unless the full local extraction exists)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _ALL_50_PRESENT, reason=_missing_reason)
def test_seed_audit_reports_exactly_50_unique_valid_hash_bound_seeds_on_real_data():
    """Beat-3 predicted outcome, proven directly against the real,
    extracted cohort: exactly 50 unique seeds, each individually valid
    (hash-bound mnrnd shim + M4 contract) and mutually non-aliased (50
    distinct file hashes)."""
    report = audit_ribosome_assembly_n50_seeds(_SPECS_PATH, karr_native_root=KARR_NATIVE_ROOT)
    assert report["n_seeds_total"] == 50
    assert report["n_seeds_valid"] == 50
    assert report["all_seeds_valid"] is True
    assert report["duplicated_hashes"] == {}
    seeds_seen = sorted(row["seed"] for row in report["per_seed"] if row["ok"])
    assert seeds_seen == list(range(50))
    hashes_seen = {row["sha256"] for row in report["per_seed"]}
    assert len(hashes_seen) == 50


@pytest.mark.skipif(not _ALL_50_PRESENT, reason=_missing_reason)
def test_real_n50_gate_computes_a_genuine_verdict_from_real_data_not_a_placeholder():
    """The core Beat-3/contract deliverable: a REAL computed
    scripts.l2_event.runner.evaluate_gate verdict from the real 50-seed
    RibosomeAssembly cohort, through the real registered
    ribosome_assembly.gate.v1 adapter and the real (now gating_ready)
    event_registry.yaml row -- never a synthetic cohort, never a
    structural-smoke NOT_APPLICABLE placeholder."""
    outcome = run_real_n50_gate()
    result = outcome["result"]

    assert outcome["audit"]["all_seeds_valid"] is True
    assert result.mode == "gate"
    assert result.n_seeds_karr == 50
    assert result.n_seeds_oc == 50
    assert result.verdict in ("PASS", "FAIL", "REFUSED")
    assert len(result.channels) == 3
    for channel in result.channels:
        # A genuinely computed channel must carry a real statistic, not
        # the structural-smoke placeholder ("n/a" / None throughout).
        assert channel.statistic_name != "n/a"
        assert channel.verdict != "NOT_COMPUTED"


@pytest.mark.skipif(not _ALL_50_PRESENT, reason=_missing_reason)
def test_real_n50_gate_refuses_rather_than_computes_when_registry_still_says_structural_smoke_only(tmp_path):
    """If the registry row's `adapter_status` were reverted to anything
    other than `gating_ready` (adapter_id unchanged), this same real
    50-seed data must still be refused (`ADAPTER_NOT_GATING_READY`), never
    silently accepted -- proving this driver goes through the real
    `check_adapter` gauntlet and cannot bypass it even with a fully valid,
    complete cohort in hand."""
    import yaml

    from scripts.l2_event.registry import REGISTRY_PATH

    raw = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    for row in raw["processes"]:
        if row["process"] == "RibosomeAssembly":
            row["adapter_status"] = "structural_smoke_only"
    stale_registry_path = tmp_path / "event_registry_stale.yaml"
    stale_registry_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises((RunnerRefusal, GateRunRefused)) as exc_info:
        run_real_n50_gate(registry_path=stale_registry_path)
    if isinstance(exc_info.value, RunnerRefusal):
        assert exc_info.value.reason == "ADAPTER_NOT_GATING_READY"
