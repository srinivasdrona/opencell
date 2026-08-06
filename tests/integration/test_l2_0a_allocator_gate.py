from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from scripts.probe_l2_0a_allocator_input import (
    ORACLE_PATH,
    AllocatorOracle,
    evaluate_allocator_gate,
    load_allocator_oracle,
    load_process_substrate_wids,
    main,
    resolve_allocator_oracle_path,
)


def _make_oracle(
    *,
    process_names: tuple[str, ...],
    metabolite_wids: tuple[str, ...],
    compartment_wids: tuple[str, ...],
    pool_before: list[float],
    requirements: list[list[float]],
    allocations: list[list[float]],
) -> AllocatorOracle:
    counts_shape = (len(metabolite_wids), len(compartment_wids))
    return AllocatorOracle(
        process_names=process_names,
        metabolite_wids=metabolite_wids,
        compartment_wids=compartment_wids,
        counts_shape=counts_shape,
        pool_before=np.asarray(pool_before, dtype=np.float64),
        requirements=np.asarray(requirements, dtype=np.float64),
        allocations=np.asarray(allocations, dtype=np.float64),
    )


def test_gate_passes_matching_fixture() -> None:
    oracle = _make_oracle(
        process_names=("ProcA", "ProcB"),
        metabolite_wids=("ATP",),
        compartment_wids=("c",),
        pool_before=[10.0],
        requirements=[[30.0], [20.0]],
        allocations=[[6.0], [4.0]],
    )
    process_wids = {
        "ProcA": ("ATP",),
        "ProcB": ("ATP",),
    }

    result = evaluate_allocator_gate(oracle, process_wids)

    assert result.returncode == 0
    assert result.checked_count == 2
    assert result.failed_count == 0
    assert result.unmapped_count == 0


def test_gate_fails_planted_misallocation() -> None:
    oracle = _make_oracle(
        process_names=("ProcA", "ProcB"),
        metabolite_wids=("ATP",),
        compartment_wids=("c",),
        pool_before=[10.0],
        requirements=[[30.0], [20.0]],
        allocations=[[7.0], [4.0]],
    )
    process_wids = {
        "ProcA": ("ATP",),
        "ProcB": ("ATP",),
    }

    result = evaluate_allocator_gate(oracle, process_wids)

    assert result.returncode == 1
    assert result.failed_count == 1
    assert result.oversupply_fail_count == 0
    assert result.other_fail_count == 1
    failure = result.failures[0]
    assert failure.process_name == "ProcA"
    assert failure.wid == "ATP"
    assert failure.expected == 7
    assert failure.observed == 6


def test_gate_catches_compensating_cross_process_swap() -> None:
    oracle = _make_oracle(
        process_names=("ProcA", "ProcB"),
        metabolite_wids=("ATP",),
        compartment_wids=("c",),
        pool_before=[10.0],
        requirements=[[30.0], [20.0]],
        allocations=[[4.0], [6.0]],
    )
    process_wids = {
        "ProcA": ("ATP",),
        "ProcB": ("ATP",),
    }

    result = evaluate_allocator_gate(oracle, process_wids)

    assert result.returncode == 1
    assert result.failed_count == 2
    assert result.oversupply_fail_count == 0
    assert result.other_fail_count == 2
    assert sum(verdict.expected for verdict in result.verdicts) == sum(
        verdict.observed for verdict in result.verdicts
    )
    assert {failure.process_name for failure in result.failures} == {"ProcA", "ProcB"}


def test_main_skips_cleanly_when_oracle_absent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing_oracle = tmp_path / "missing_oracle.mat"

    code = main(["--oracle", str(missing_oracle)])
    captured = capsys.readouterr()

    assert code == 0
    assert "SKIPPED" in captured.out
    assert "oracle absent" in captured.out


@lru_cache(maxsize=1)
def _real_oracle_result():
    oracle = load_allocator_oracle(resolve_allocator_oracle_path())
    process_wids = load_process_substrate_wids()
    return evaluate_allocator_gate(oracle, process_wids)


@pytest.mark.skipif(resolve_allocator_oracle_path() is None, reason="allocator oracle absent")
def test_real_oracle_baseline_is_green_after_uncap() -> None:
    """OC's allocator is bit-identical to Karr's evolveState.m after removing the
    `min(1.0)` oversupply cap (karr_allocation_step.py). Previously this baseline
    was RED with every failure in the oversupply-cap fork; the fix flips it GREEN.

    The coverage assertions (checked_count, Metabolism/tRNAAminoacylation checked)
    guard against a vacuous green from the gate silently checking nothing.
    """
    result = _real_oracle_result()
    metabolism = next(summary for summary in result.process_summaries if summary.process_name == "Metabolism")
    trna = next(summary for summary in result.process_summaries if summary.process_name == "tRNAAminoacylation")

    assert result.returncode == 0
    assert result.failed_count == 0
    assert result.oversupply_fail_count == 0
    assert result.other_fail_count == 0
    # Real coverage must remain — a green with zero checks would be vacuous.
    assert result.checked_count > 0
    assert result.unmapped_count > 0
    assert metabolism.checked > 0
    assert metabolism.failed == 0
    # tRNAAminoacylation was the 2nd-largest divergence source pre-fix (23 cells).
    assert trna.checked > 0
    assert trna.failed == 0
