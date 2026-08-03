"""L2.5 allocator smoke test — ProteinProcessingI + ProteinProcessingII pair.

Per `docs/phase_f/L2_2_STOCHASTIC_AUDIT.md` CRITIQUE ADDENDUM (commit `bb5716c`),
PPI+PPII replaces Translation+RNAProcessing as the first L2.5 pair because:

- Both are TRIVIAL-RNG (no DEEP L2.2 prerequisite).
- Both are L2.1-GREEN (per-process bit-identity established).
- They share a water-limited cleavage path (substrates pool), so a broken
  shared-pool allocator would surface as one of: double-spend, negative
  substrates, or asymmetric starvation across the two processes.

This is explicitly an **allocator smoke test**, NOT biology validation. The
GPT-5.5 critique flagged that PPI+PPII is "low coupling complexity" — failures
here localize to the harness, not the biology.

Coverage:
- `test_l2_5_ppi_ppii_oracle_replay_v2` — full oracle replay via
  `run_integrated_replay_v2`. If GREEN, demonstrates the allocator routes water
  correctly across the two trivially-stochastic processes.
- `test_l2_5_ppi_ppii_allocator_invariants` — three hard assertions on the
  in-tick state without going through the oracle: total water consumed by
  PPI+PPII <= pre-tick water; no negative substrate counts; namespace
  separation of request keys.

DEFERRED (audit assertion #4, "symmetric starvation under constrained water"):
needs a calibrated water-budget setpoint. Tracked in plan.md item 6c.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
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

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

import h5py
from l2_2_replay_common_v2 import _COMPOSITION_ORDER_V2, run_integrated_replay_v2
from l2_replay_common import (
    apply_count_update,
    build_state_template,
    cell_vector,
    collect_count_delta_dicts,
    infer_wids_for_observable,
    overlay_observable_into_state,
    refresh_allocator_views,
    resolve_trace_path,
)

from opencell.vivarium.karr_protein_processing_i import KarrProteinProcessingIProcess
from opencell.vivarium.karr_protein_processing_ii import KarrProteinProcessingIIProcess

_PAIR = ["ProteinProcessingI", "ProteinProcessingII"]


@pytest.mark.parametrize("rng_seed", [0], ids=["rng_seed_0"])
def test_l2_5_ppi_ppii_oracle_replay_v2(rng_seed: int) -> None:
    """Full L2.5 v2 oracle replay for the PPI+PPII pair.

    First execution of this pair. The audit predicts smoke-clean (both processes
    are TRIVIAL-RNG and L2.1-GREEN). If it fails, the harness emits a structured
    cause code (CAUSE_1..CAUSE_7) that localizes the bug.
    """
    # Sanity-check that the composition order registry includes both processes
    # in the expected canonical order (PPI before PPII).
    pp_pair_in_order = [name for name in _COMPOSITION_ORDER_V2 if name in set(_PAIR)]
    assert pp_pair_in_order == _PAIR, (
        f"composition order must place PPI before PPII; got {pp_pair_in_order}"
    )

    run_integrated_replay_v2(under_test_processes=_PAIR, rng_seed=rng_seed)


def _build_pair_state_template() -> tuple[
    KarrProteinProcessingIProcess,
    KarrProteinProcessingIIProcess,
    dict,
]:
    ppi = KarrProteinProcessingIProcess({"rng_seed": 0})
    ppii = KarrProteinProcessingIIProcess({"rng_seed": 0})
    state = build_state_template(ppi)
    # Overlay PPII's schema fields on top so both processes can read the state.
    ppii_template = build_state_template(ppii)
    for port, port_state in ppii_template.items():
        if port not in state:
            state[port] = port_state
        else:
            for key, value in port_state.items():
                state[port].setdefault(key, value)
    return ppi, ppii, state


def _seed_state_from_trace(
    state: dict,
    process: KarrProteinProcessingIProcess | KarrProteinProcessingIIProcess,
    process_name: str,
    tick: int = 0,
) -> dict[str, list[str]]:
    observables = ("substrates", "enzymes", "boundEnzymes", "processedMonomers", "unprocessedMonomers")
    attr_map = {
        "substrates": "substrate_wids",
        "enzymes": "enzyme_wids",
        "boundEnzymes": "enzyme_wids",
        "processedMonomers": "processed_monomer_wids",
        "unprocessedMonomers": "unprocessed_monomer_wids",
    }
    template = build_state_template(process)
    wids_by_observable: dict[str, list[str]] = {}
    with h5py.File(resolve_trace_path(process_name), "r") as trace:
        for observable in observables:
            karr_before = cell_vector(trace, "states_before", observable, tick)
            wids = infer_wids_for_observable(
                process,
                template,
                observable,
                karr_len=int(karr_before.shape[0]),
                explicit_attr=attr_map[observable],
            )
            wids_by_observable[observable] = wids
            overlay_observable_into_state(
                process=process,
                state=state,
                observable=observable,
                vector=karr_before,
                wids=wids,
            )
    refresh_allocator_views(process, state)
    return wids_by_observable


def _total_water(state: dict, wids: list[str]) -> float:
    substrate_state = state.get("substrate_counts", {})
    h2o_wid = next((w for w in wids if w.upper() in {"H2O", "H2O[C]"}), None)
    if h2o_wid is None:
        # Fall back: look for any wid containing 'H2O' substring.
        h2o_wid = next((w for w in wids if "H2O" in w.upper()), None)
    if h2o_wid is None:
        return float("nan")
    return float(substrate_state.get(h2o_wid, 0.0))


def test_l2_5_ppi_ppii_allocator_invariants() -> None:
    """Allocator smoke: 3 of the 4 audit assertions.

    Asserts on the shared state after one tick of PPI then PPII (sequential,
    same composition order as the oracle-replay test):

    1. No negative substrate counts after either process runs.
    2. Total water never goes negative; cumulative water consumption equals
       sum of per-process H2O deltas (no double-spend).
    3. Namespace separation: PPI and PPII deltas address the same substrate
       pool via the same WID keys (the shared pool IS the test target), but
       per-process update dicts must not silently overwrite or alias each
       other's monomer namespaces.

    DEFERRED #4: symmetric starvation under constrained water — requires a
    calibrated low-water setpoint; tracked in plan.md item 6c.
    """
    ppi, ppii, state = _build_pair_state_template()

    wids_ppi = _seed_state_from_trace(state, ppi, "ProteinProcessingI", tick=0)
    wids_ppii = _seed_state_from_trace(state, ppii, "ProteinProcessingII", tick=0)

    substrate_wids_ppi = wids_ppi["substrates"]
    substrate_wids_ppii = wids_ppii["substrates"]

    water_before = _total_water(state, substrate_wids_ppi)

    # Tick PPI then PPII against the shared state (canonical order from the harness).
    refresh_allocator_views(ppi, state)
    update_ppi = ppi.next_update(1.0, state)
    apply_count_update(state, update_ppi)
    water_after_ppi = _total_water(state, substrate_wids_ppi)

    refresh_allocator_views(ppii, state)
    update_ppii = ppii.next_update(1.0, state)
    apply_count_update(state, update_ppii)
    water_after_ppii = _total_water(state, substrate_wids_ppii)

    # ASSERTION 1: no negative substrate counts after either process.
    substrate_counts = state.get("substrate_counts", {})
    negative_wids = {
        wid: count
        for wid, count in substrate_counts.items()
        if float(count) < 0.0
    }
    assert not negative_wids, (
        f"L2.5 allocator invariant violated: negative substrate counts after "
        f"PPI+PPII tick: {negative_wids}"
    )

    # ASSERTION 2 (water budget): no double-spend.
    # The water level after each process must be <= water level before that process.
    # And the cumulative drop must equal PPI's H2O delta + PPII's H2O delta
    # (not less — would mean a process credited itself water it didn't have).
    if not np.isnan(water_before):
        assert water_after_ppi <= water_before + 1e-9, (
            f"PPI returned more water than was available: "
            f"before={water_before}, after_ppi={water_after_ppi}"
        )
        assert water_after_ppii <= water_after_ppi + 1e-9, (
            f"PPII returned more water than was available after PPI: "
            f"after_ppi={water_after_ppi}, after_ppii={water_after_ppii}"
        )
        # Sum-of-deltas reconciliation.
        ppi_water_delta = _extract_water_delta(update_ppi, substrate_wids_ppi)
        ppii_water_delta = _extract_water_delta(update_ppii, substrate_wids_ppii)
        observed_drop = water_before - water_after_ppii
        accounted_drop = -(ppi_water_delta + ppii_water_delta)
        assert abs(observed_drop - accounted_drop) <= 1e-6, (
            f"Water double-spend detected: observed drop {observed_drop}, "
            f"sum of process deltas {accounted_drop} (PPI={ppi_water_delta}, "
            f"PPII={ppii_water_delta})"
        )

    # ASSERTION 4 (namespace separation): PPI and PPII may both address the
    # substrate pool by WID (that's the whole point of the shared pool), but
    # their *monomer* deltas must address distinct namespaces. PPI cleaves
    # unprocessedMonomers -> processedMonomers (deformylase + MAP). PPII does
    # signal-sequence cleavage on a SUBSET of already-processed monomers. The
    # subset overlap is expected at the WID level (PPII consumes some of what
    # PPI produces) but per-tick the same delta must not appear twice from
    # both processes (would mean PPI's emitted delta got double-counted).
    ppi_monomer_keys = _monomer_delta_keys(update_ppi)
    ppii_monomer_keys = _monomer_delta_keys(update_ppii)
    # Per-tick double-counting check: if the same (port, wid) appears in both
    # updates, the deltas must be independent allocations, not the same
    # allocation surfaced twice. We can't detect "same allocation" without
    # provenance plumbing, so this assertion is a structural guardrail: PPI
    # and PPII must not BOTH emit identical (port, wid, value) triples in the
    # same tick (would indicate cloned-update bug).
    identical_triples = ppi_monomer_keys.intersection(ppii_monomer_keys)
    # Note: WID overlap is allowed (both processes legitimately write to
    # `monomer_counts.<some_wid>`); we only flag *value-identical* overlaps.
    if identical_triples:
        ppi_values = _collect_delta_values(update_ppi, identical_triples)
        ppii_values = _collect_delta_values(update_ppii, identical_triples)
        suspicious = {
            triple
            for triple in identical_triples
            if ppi_values.get(triple) == ppii_values.get(triple)
            and ppi_values.get(triple, 0.0) != 0.0
        }
        assert not suspicious, (
            f"L2.5 allocator namespace check: PPI and PPII emitted identical "
            f"(port, wid, value) triples in same tick (possible cloned-update "
            f"bug): {suspicious}"
        )


def _extract_water_delta(update: dict, substrate_wids: list[str]) -> float:
    """Sum of water deltas across all count-delta dicts in this update."""
    h2o_wid = next((w for w in substrate_wids if w.upper() in {"H2O", "H2O[C]"}), None)
    if h2o_wid is None:
        h2o_wid = next((w for w in substrate_wids if "H2O" in w.upper()), None)
    if h2o_wid is None:
        return 0.0
    total = 0.0
    for _label, deltas in collect_count_delta_dicts(update):
        if h2o_wid in deltas:
            total += float(deltas[h2o_wid])
    return total


def _monomer_delta_keys(update: dict) -> set[tuple[str, str]]:
    """Return (label, wid) keys for every monomer-touching delta in this update."""
    keys: set[tuple[str, str]] = set()
    for label, deltas in collect_count_delta_dicts(update):
        if "monomer" not in label.lower() and "protein" not in label.lower():
            continue
        for wid in deltas:
            keys.add((label, wid))
    return keys


def _collect_delta_values(
    update: dict, keys: set[tuple[str, str]]
) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    for label, deltas in collect_count_delta_dicts(update):
        for wid, value in deltas.items():
            if (label, wid) in keys:
                out[(label, wid)] = float(value)
    return out
