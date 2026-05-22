from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

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

from opencell.vivarium.karr_protein_folding import KarrProteinFoldingProcess


def _build_state(
    process: KarrProteinFoldingProcess,
    unfolded_overrides: dict[str, float] | None = None,
    substrate_overrides: dict[str, float] | None = None,
    enzyme_overrides: dict[str, float] | None = None,
    allocated_overrides: dict[str, float] | None = None,
) -> dict[str, Any]:
    unfolded_overrides = unfolded_overrides or {}
    substrate_overrides = substrate_overrides or {}
    enzyme_overrides = enzyme_overrides or {}
    allocated_overrides = allocated_overrides or {}

    count_wids = list(dict.fromkeys([*process.folded_monomer_wids, *process.enzyme_wids]))
    protein_counts = {wid: 0.0 for wid in count_wids}
    for wid in process.enzyme_wids:
        protein_counts[wid] = 100.0
    for wid, value in enzyme_overrides.items():
        protein_counts[wid] = float(value)

    state = {
        "substrates": {wid: 1_000.0 for wid in process.substrate_wids},
        "protein": {
            "counts": protein_counts,
            "unfolded_counts": {wid: 0.0 for wid in process.unfolded_monomer_wids},
        },
        "substrates_allocated": {process.name: {wid: 0.0 for wid in process.substrate_wids}},
    }
    for wid, value in substrate_overrides.items():
        state["substrates"][wid] = float(value)
    for wid, value in unfolded_overrides.items():
        state["protein"]["unfolded_counts"][wid] = float(value)
    for wid, value in allocated_overrides.items():
        state["substrates_allocated"][process.name][wid] = float(value)
    return state


def _row_requirements(process: KarrProteinFoldingProcess, monomer_idx: int) -> dict[str, int]:
    row = process.protein_prosthetic_matrix[monomer_idx]
    return {
        process.substrate_wids[sidx]: int(coeff)
        for sidx, coeff in enumerate(row.tolist())
        if coeff > 0
    }


def test_fixture_loads() -> None:
    p = KarrProteinFoldingProcess({})
    assert p.name == "karr_protein_folding"
    assert len(p.substrate_wids) == 11
    assert len(p.enzyme_wids) == 5
    assert len(p.unfolded_monomer_wids) == 482
    assert len(p.folded_monomer_wids) == 482

    assert p.protein_prosthetic_matrix.shape == (482, 11)
    assert p.protein_chaperone_matrix.shape == (482, 5)

    assert int(np.sum(p.ion_required_mask)) >= 80
    assert int(np.sum(p.chaperone_dependent_mask)) == 64
    assert {"FE2", "MG", "ZN"}.issubset(set(p.substrate_wids))
    assert "MG_238_MONOMER" in set(p.enzyme_wids)


def test_no_unfolded_no_action() -> None:
    p = KarrProteinFoldingProcess({})
    update = p.next_update(1.0, _build_state(p))
    assert update == {}


def test_ion_binding_first_then_chaperone() -> None:
    p = KarrProteinFoldingProcess({"rng_seed": 0})
    both = np.flatnonzero(p.ion_required_mask & p.chaperone_dependent_mask)
    idx = int(both[0])
    wid = p.unfolded_monomer_wids[idx]
    ion_needs = _row_requirements(p, idx)

    substrates = {"ATP": 10.0}
    substrates.update({ion_wid: float(stoich) for ion_wid, stoich in ion_needs.items()})
    enzymes = {wid_: 2.0 for wid_ in p.enzyme_wids}
    state = _build_state(
        p,
        unfolded_overrides={wid: 1.0},
        substrate_overrides=substrates,
        enzyme_overrides=enzymes,
    )
    update = p.next_update(1.0, state)
    assert update["protein"]["unfolded_counts"][wid] == -1.0
    assert update["protein"]["counts"][wid] == 1.0
    assert update["substrates"]["ATP"] == -4.0
    for ion_wid, stoich in ion_needs.items():
        assert update["substrates"][ion_wid] == float(-stoich)

    missing = dict(substrates)
    first_ion = next(iter(ion_needs))
    missing[first_ion] = 0.0
    blocked_state = _build_state(
        p,
        unfolded_overrides={wid: 1.0},
        substrate_overrides=missing,
        enzyme_overrides=enzymes,
    )
    blocked_update = p.next_update(1.0, blocked_state)
    assert wid not in blocked_update.get("protein", {}).get("counts", {})
    assert blocked_update.get("substrates", {}).get("ATP", 0.0) == 0.0


def test_no_chaperones_no_folding_of_chaperone_dependent() -> None:
    p = KarrProteinFoldingProcess({"rng_seed": 1})
    ch_idx = np.flatnonzero(p.chaperone_dependent_mask)
    unfolded = {p.unfolded_monomer_wids[i]: 1.0 for i in ch_idx}
    enzymes = {wid: 100.0 for wid in p.enzyme_wids}
    enzymes[p.enzyme_wids[p.enzyme_idx_dnaK]] = 0.0

    state = _build_state(
        p,
        unfolded_overrides=unfolded,
        substrate_overrides={"ATP": 10_000.0},
        enzyme_overrides=enzymes,
    )
    update = p.next_update(1.0, state)
    folded = update.get("protein", {}).get("counts", {})
    for i in ch_idx:
        assert p.folded_monomer_wids[int(i)] not in folded
    assert update.get("substrates", {}).get("ATP", 0.0) == 0.0


def test_no_ions_no_binding() -> None:
    p = KarrProteinFoldingProcess({"rng_seed": 2})
    ion_idx = np.flatnonzero(p.ion_required_mask)
    unfolded = {p.unfolded_monomer_wids[i]: 1.0 for i in ion_idx}
    state = _build_state(
        p,
        unfolded_overrides=unfolded,
        substrate_overrides={
            "FE2": 0.0,
            "K": 0.0,
            "MG": 0.0,
            "MN": 0.0,
            "NA": 0.0,
            "ZN": 0.0,
            "ATP": 10_000.0,
        },
        enzyme_overrides={wid: 500.0 for wid in p.enzyme_wids},
    )
    update = p.next_update(1.0, state)
    folded = update.get("protein", {}).get("counts", {})
    for i in ion_idx:
        assert p.folded_monomer_wids[int(i)] not in folded
    assert update.get("substrates", {}).get("ATP", 0.0) == 0.0


def test_atp_consumption_per_chaperone_cycle() -> None:
    p = KarrProteinFoldingProcess({"rng_seed": 3})
    idx = int(np.flatnonzero(p.chaperone_dependent_mask & ~p.ion_required_mask)[0])
    wid = p.unfolded_monomer_wids[idx]
    n_fold = 3

    state = _build_state(
        p,
        unfolded_overrides={wid: float(n_fold)},
        substrate_overrides={"ATP": float(n_fold * 4)},
        enzyme_overrides={wid_: 20.0 for wid_ in p.enzyme_wids},
    )
    update = p.next_update(1.0, state)
    assert update["protein"]["unfolded_counts"][wid] == float(-n_fold)
    assert update["protein"]["counts"][wid] == float(n_fold)
    assert update["substrates"]["ATP"] == float(-(n_fold * 4))


def test_trigger_factor_required_for_all() -> None:
    p = KarrProteinFoldingProcess({"rng_seed": 4})
    trigger_only = int(np.flatnonzero(~p.ion_required_mask & ~p.chaperone_dependent_mask)[0])
    ch_only = int(np.flatnonzero(~p.ion_required_mask & p.chaperone_dependent_mask)[0])

    unfolded = {
        p.unfolded_monomer_wids[trigger_only]: 1.0,
        p.unfolded_monomer_wids[ch_only]: 1.0,
    }
    enzymes = {wid: 10.0 for wid in p.enzyme_wids}
    enzymes[p.enzyme_wids[p.enzyme_idx_trigger_factor]] = 0.0

    state = _build_state(
        p,
        unfolded_overrides=unfolded,
        substrate_overrides={"ATP": 100.0},
        enzyme_overrides=enzymes,
    )
    update = p.next_update(1.0, state)
    folded = update.get("protein", {}).get("counts", {})
    assert p.folded_monomer_wids[trigger_only] not in folded
    assert p.folded_monomer_wids[ch_only] not in folded
    assert update.get("substrates", {}).get("ATP", 0.0) == 0.0


def test_deterministic_with_seed() -> None:
    p1 = KarrProteinFoldingProcess({"rng_seed": 42})
    p2 = KarrProteinFoldingProcess({"rng_seed": 42})

    ch_idx = np.flatnonzero(p1.chaperone_dependent_mask)[:12]
    trig_idx = np.flatnonzero(~p1.chaperone_dependent_mask)[:12]
    unfolded = {
        **{p1.unfolded_monomer_wids[int(i)]: 2.0 for i in ch_idx},
        **{p1.unfolded_monomer_wids[int(i)]: 2.0 for i in trig_idx},
    }
    enzymes = {wid: 6.0 for wid in p1.enzyme_wids}
    enzymes[p1.enzyme_wids[p1.enzyme_idx_trigger_factor]] = 10.0
    state = _build_state(
        p1,
        unfolded_overrides=unfolded,
        substrate_overrides={"ATP": 20.0, "FE2": 1_000.0, "MG": 1_000.0, "ZN": 1_000.0},
        enzyme_overrides=enzymes,
    )

    update_1 = p1.next_update(1.0, deepcopy(state))
    update_2 = p2.next_update(1.0, deepcopy(state))
    assert update_1 == update_2
