from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure pytest imports from this worktree even if another editable install exists.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from vivarium.core import process as vivarium_process_module

if not hasattr(vivarium_process_module, "Step"):
    class Step(vivarium_process_module.Process):
        pass

    vivarium_process_module.Step = Step

from opencell.vivarium.karr_request_calculators import RequestCalculatorTRNA
from opencell.vivarium.karr_trna_aminoacylation import KarrTRNAAminoacylationProcess


def test_request_calculator_trna_atp_request_scales_with_availability() -> None:
    """Karr-parity formula: ATP request = avail * 25.0 (no NGAM floor)."""
    trna_proc = KarrTRNAAminoacylationProcess({"time_step": 1.0})
    calc = RequestCalculatorTRNA({"trna_proc": trna_proc})

    substrate_state = {wid: 0.0 for wid in trna_proc.substrate_wids}
    substrate_state["ATP"] = 0.2
    non_atp_consumed = next((wid for wid in calc._consumed_substrate_wids if wid != "ATP"), None)
    if non_atp_consumed is not None:
        substrate_state[non_atp_consumed] = 7.0

    rna_counts = {wid: 0.0 for wid in trna_proc.free_rna_wids}
    rna_counts[trna_proc.free_rna_wids[0]] = 1.0

    update = calc.next_update(
        1.0,
        {
            "substrates": substrate_state,
            "rna": {"counts": rna_counts},
        },
    )
    requests = update["requests"][trna_proc.name]

    assert requests["ATP"] == pytest.approx(5.0, rel=0.0, abs=1e-12)
    if non_atp_consumed is not None:
        assert requests[non_atp_consumed] == pytest.approx(7.0, rel=0.0, abs=1e-12)
