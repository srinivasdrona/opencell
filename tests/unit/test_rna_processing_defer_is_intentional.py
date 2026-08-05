from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from vivarium.core.engine import Engine

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

from opencell.vivarium.karr_composite import build_karr_chassis_v6


def _run_five_tick_canary_probe() -> dict[str, Any]:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    engine = Engine(composite=composite, emit_step=1.0, display_info=False)

    tx_proc = engine.processes["karr_transcription"]
    rna_proc = engine.processes["karr_rna_processing"]

    snapshots: list[dict[str, Any]] = []
    for _ in range(5):
        state = engine.state.get_value()
        tx_live_ids = {
            wid for wid in tx_proc.gene_ids if float(state["rna"]["counts"].get(wid, 0.0)) > 0.0
        }
        snapshots.append({"state": state, "tx_live_ids": tx_live_ids})
        engine.update(1.0)

    return {
        "rna_proc": rna_proc,
        "snapshots": snapshots,
    }


def test_defer_id_space_intersection_is_zero_in_wave2_canary() -> None:
    """Wave2 defer gate per docs/processes/rna_processing_defer.md: TX-vs-TU intersection stays 0."""
    probe = _run_five_tick_canary_probe()
    rna_proc = probe["rna_proc"]
    snapshots = probe["snapshots"]

    unprocessed_tu_ids = set(rna_proc.unprocessed_rna_wids)
    tx_live_count = 0
    for snap in snapshots:
        tx_live_ids = snap["tx_live_ids"]
        tx_live_count += len(tx_live_ids)
        assert len(tx_live_ids & unprocessed_tu_ids) == 0

    assert tx_live_count > 0


def test_defer_gate_returns_empty_update_in_wave2_canary() -> None:
    """Wave2 defer gate per docs/processes/rna_processing_defer.md: RNAProcessing emits no deltas."""
    probe = _run_five_tick_canary_probe()
    rna_proc = probe["rna_proc"]
    snapshots = probe["snapshots"]

    for snap in snapshots:
        update = rna_proc.next_update(1.0, snap["state"])
        assert update == {}
