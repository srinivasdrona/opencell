from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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

import opencell.vivarium.karr_host_interaction as host_interaction_module
from opencell.vivarium.karr_host_interaction import KarrHostInteractionProcess


def _ready_count_stores(
    process: KarrHostInteractionProcess,
) -> tuple[dict[str, float], dict[str, float]]:
    return (
        dict(process.fitted_monomer_counts_by_wid),
        dict(process.fitted_complex_counts_by_wid),
    )


def _base_state(
    protein_counts: dict[str, float],
    complex_counts: dict[str, float],
    cell_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "cell": dict(cell_state or {}),
        "protein": {"counts": dict(protein_counts)},
        "complex": {"counts": dict(complex_counts)},
    }


def _zero_wids(
    process: KarrHostInteractionProcess,
    protein_counts: dict[str, float],
    complex_counts: dict[str, float],
    wids: set[str],
) -> None:
    for wid in wids:
        store = process.enzyme_store_by_wid[wid]
        if store == "protein":
            protein_counts[wid] = 0.0
        else:
            complex_counts[wid] = 0.0


_ALL_HOST_FIELDS = (
    "host_attached",
    "host_tlr1_activated",
    "host_tlr2_activated",
    "host_tlr6_activated",
    "host_nfkb_activated",
    "host_inflammatory_response_activated",
)

_PREREGISTERED_CONDITIONS = (
    ("POSITIVE", set(), (True, True, True, True, True, True)),
    ("NEG_ADHERENCE", {"MG_218_MONOMER"}, (False, False, False, False, False, False)),
    (
        "PARTIAL_ADHERENT_NO_SIGNAL",
        {
            "MG_075_MONOMER",
            "MG_149_MONOMER",
            "MG_309_MONOMER",
            "MG_412_MONOMER",
            "MG_410_411_412_PENTAMER",
        },
        (True, False, False, False, False, False),
    ),
    ("TLR12_PATH", {"MG_309_MONOMER"}, (True, True, True, False, True, True)),
    (
        "TLR26_PATH",
        {
            "MG_149_MONOMER",
            "MG_412_MONOMER",
            "MG_410_411_412_PENTAMER",
        },
        (True, False, True, True, True, True),
    ),
    (
        "ANTIGEN_ONLY",
        {
            "MG_149_MONOMER",
            "MG_309_MONOMER",
            "MG_412_MONOMER",
            "MG_410_411_412_PENTAMER",
        },
        (True, False, False, False, False, True),
    ),
)


def test_process_instantiates_and_loads_fixture_index_sets() -> None:
    p = KarrHostInteractionProcess({})
    assert p.name == "karr_host_interaction"
    assert len(p.terminal_organelle_wids) == 8
    assert len(p.adhesin_wids) == 4
    assert set(p.adhesin_wids) <= set(p.terminal_organelle_wids)
    assert len(p.tlr12_ligand_wids) == 3
    assert len(p.tlr26_ligand_wids) == 1
    assert len(p.antigen_wids) == 5
    assert len(p.monomer_enzyme_wids) == 14
    assert p.complex_enzyme_wids == ["MG_410_411_412_PENTAMER"]
    assert p.fitted_monomer_counts_by_wid == {
        wid: float(p.enzyme_ref_counts[p.enzyme_wids.index(wid)])
        for wid in p.monomer_enzyme_wids
    }
    assert p.fitted_complex_counts_by_wid == {
        wid: float(p.enzyme_ref_counts[p.enzyme_wids.index(wid)])
        for wid in p.complex_enzyme_wids
    }

    schema = p.ports_schema()
    assert set(schema["cell"].keys()) == set(_ALL_HOST_FIELDS)
    assert set(schema["protein"]["counts"]) == set(p.monomer_enzyme_wids)
    assert set(schema["complex"]["counts"]) == set(p.complex_enzyme_wids)
    for field in _ALL_HOST_FIELDS:
        assert schema["cell"][field]["_updater"] == "set"
        assert schema["cell"][field]["_default"] is False


def test_construction_rejects_canonical_complex_count_projection_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_fixture = KarrHostInteractionProcess._fixture_struct
    host_fx = load_fixture(host_interaction_module._DEFAULT_FIXTURE_PATH)
    complex_fx = load_fixture(host_interaction_module._DEFAULT_COMPLEX_FIXTURE_PATH)

    local_i = int(np.asarray(host_fx.enzymeComplexLocalIndexs).reshape(-1)[0])
    global_i = int(np.asarray(host_fx.enzymeComplexGlobalIndexs).reshape(-1)[0])
    compartment_i = int(
        np.asarray(host_fx.enzymeComplexCompartmentIndexs).reshape(-1)[0]
    )
    mature_i = int(np.asarray(complex_fx.matureIndexs).reshape(-1)[global_i - 1])
    canonical_counts = np.asarray(complex_fx.counts).copy()
    host_projection = float(np.asarray(host_fx.enzymes).reshape(-1)[local_i - 1])
    assert canonical_counts[mature_i - 1, compartment_i - 1] == host_projection
    canonical_counts[mature_i - 1, compartment_i - 1] = host_projection + 1.0
    complex_fx.counts = canonical_counts

    def fixture_with_independent_canonical_mismatch(path: str | Path) -> object:
        if str(path) == host_interaction_module._DEFAULT_COMPLEX_FIXTURE_PATH:
            return complex_fx
        return load_fixture(path)

    monkeypatch.setattr(
        KarrHostInteractionProcess,
        "_fixture_struct",
        staticmethod(fixture_with_independent_canonical_mismatch),
    )

    with pytest.raises(
        ValueError,
        match="HostInteraction canonical fixture projection mismatch",
    ):
        KarrHostInteractionProcess({})


@pytest.mark.parametrize(
    ("condition_id", "zero_wids", "expected"),
    _PREREGISTERED_CONDITIONS,
)
def test_preregistered_condition_vectors(
    condition_id: str,
    zero_wids: set[str],
    expected: tuple[bool, ...],
) -> None:
    del condition_id
    p = KarrHostInteractionProcess({})
    protein_counts, complex_counts = _ready_count_stores(p)
    _zero_wids(p, protein_counts, complex_counts, zero_wids)

    computed = p.calculate_host_state(protein_counts, complex_counts)
    update = p.next_update(1.0, _base_state(protein_counts, complex_counts))
    observed_update = {
        field: bool(update.get("cell", {}).get(field, False))
        for field in _ALL_HOST_FIELDS
    }
    expected_map = dict(zip(_ALL_HOST_FIELDS, expected, strict=True))

    assert computed == expected_map
    assert observed_update == expected_map


def test_pentamer_is_read_only_from_live_complex_store() -> None:
    p = KarrHostInteractionProcess({})
    protein_counts, complex_counts = _ready_count_stores(p)
    _zero_wids(
        p,
        protein_counts,
        complex_counts,
        {
            "MG_075_MONOMER",
            "MG_149_MONOMER",
            "MG_309_MONOMER",
            "MG_412_MONOMER",
        },
    )

    with_pentamer = p.calculate_host_state(protein_counts, complex_counts)
    complex_counts["MG_410_411_412_PENTAMER"] = 0.0
    without_pentamer = p.calculate_host_state(protein_counts, complex_counts)

    assert tuple(with_pentamer[field] for field in _ALL_HOST_FIELDS) == (
        True,
        True,
        True,
        False,
        True,
        True,
    )
    assert tuple(without_pentamer[field] for field in _ALL_HOST_FIELDS) == (
        True,
        False,
        False,
        False,
        False,
        False,
    )


@pytest.mark.parametrize(
    ("store_name", "wid"),
    (
        ("protein", "MG_075_MONOMER"),
        ("complex", "MG_410_411_412_PENTAMER"),
    ),
)
def test_missing_canonical_enzyme_key_fails_explicitly(
    store_name: str,
    wid: str,
) -> None:
    p = KarrHostInteractionProcess({})
    protein_counts, complex_counts = _ready_count_stores(p)
    target = protein_counts if store_name == "protein" else complex_counts
    wrong_store = complex_counts if store_name == "protein" else protein_counts
    wrong_store[wid] = target[wid]
    target.pop(wid)

    with pytest.raises(KeyError, match=wid):
        p.calculate_host_state(protein_counts, complex_counts)


def test_all_enzymes_present_activates_full_cascade() -> None:
    """Literal Karr formula: all(terminalOrganelle) && all(adhesin) -> adherent;
    ligands present -> TLR1/2/6; NFkB from TLR combination; inflammatory from
    NFkB or antigen. With every required WID present (>0), every output is True
    -- this mirrors the genuine MATLAB seed-0 canary
    (tmp/probe_host_interaction_canary.m), which showed ALL FOUR Host booleans
    are True from tick 1 onward given Karr's fitted initial protein counts."""
    p = KarrHostInteractionProcess({})
    protein_counts, complex_counts = _ready_count_stores(p)
    state = _base_state(protein_counts, complex_counts)
    update = p.next_update(1.0, state)

    assert update["cell"] == {field: True for field in _ALL_HOST_FIELDS}


def test_missing_single_terminal_organelle_protein_deactivates_everything() -> None:
    """Zeroing exactly ONE terminalOrganelle protein (MG_218, present in
    neither the adhesin, tlr12/26Ligand, nor antigen index sets) must flip
    isBacteriumAdherent (all(...) is no longer satisfied) and therefore
    every downstream boolean, matching HostInteraction.m's `all(...)`
    short-circuit semantics exactly (not a fractional/partial-credit
    threshold, as the prior Karr-light v1 approximation used)."""
    p = KarrHostInteractionProcess({})
    protein_counts, complex_counts = _ready_count_stores(p)
    protein_counts["MG_218_MONOMER"] = 0.0
    cell_state = {field: True for field in _ALL_HOST_FIELDS}
    state = _base_state(protein_counts, complex_counts, cell_state)
    update = p.next_update(1.0, state)

    assert update["cell"] == {field: False for field in _ALL_HOST_FIELDS}


def test_adherent_without_any_ligand_leaves_tlr_and_downstream_false() -> None:
    """Adherence alone does not activate TLR/NF-kB/inflammatory response --
    HostInteraction.m gates each TLR on `isBacteriumAdherent && any(ligand)`,
    so zeroing every ligand/antigen WID (while keeping the structural
    terminalOrganelle/adhesin set nonzero) must leave TLR1/2/6, NF-kB, and
    inflammatory response all False even though adherence itself is True."""
    p = KarrHostInteractionProcess({})
    protein_counts, complex_counts = _ready_count_stores(p)
    _zero_wids(
        p,
        protein_counts,
        complex_counts,
        set(p.tlr12_ligand_wids)
        | set(p.tlr26_ligand_wids)
        | set(p.antigen_wids),
    )
    state = _base_state(protein_counts, complex_counts)
    update = p.next_update(1.0, state)

    assert update["cell"]["host_attached"] is True
    assert update["cell"].get("host_tlr1_activated", False) is False
    assert update["cell"].get("host_tlr2_activated", False) is False
    assert update["cell"].get("host_tlr6_activated", False) is False
    assert update["cell"].get("host_nfkb_activated", False) is False
    assert update["cell"].get("host_inflammatory_response_activated", False) is False


def test_nfkb_requires_tlr2_plus_tlr1_or_tlr6_not_tlr1_and_tlr6_alone() -> None:
    """Literal formula: isNFkBActivated = (TLR2 && TLR1) || (TLR2 && TLR6).
    TLR1 alone (tlr12Ligand present, tlr26Ligand absent) activates TLR1 AND
    TLR2 (tlr12/26Ligand is an inclusive-or gate for TLR2) but never TLR6,
    so NF-kB fires via the (TLR2 && TLR1) disjunct. This is the anti-cheat
    check: a process that fabricated NF-kB as `TLR1 or TLR6` (dropping the
    TLR2 conjunct entirely) would ALSO pass here, so the companion test
    below exercises TLR1-absent/TLR6-present to rule that out."""
    p = KarrHostInteractionProcess({})
    protein_counts, complex_counts = _ready_count_stores(p)
    _zero_wids(
        p,
        protein_counts,
        complex_counts,
        set(p.tlr26_ligand_wids),
    )
    state = _base_state(protein_counts, complex_counts)
    update = p.next_update(1.0, state)

    assert update["cell"]["host_tlr1_activated"] is True
    assert update["cell"]["host_tlr2_activated"] is True
    assert update["cell"].get("host_tlr6_activated", False) is False
    assert update["cell"]["host_nfkb_activated"] is True


def test_tlr2_alone_without_tlr1_or_tlr6_never_activates_nfkb() -> None:
    """Anti-cheat: NF-kB must genuinely require BOTH a TLR2 conjunct AND one
    of TLR1/TLR6 -- TLR2 can never fire without TLR1 or TLR6 also firing
    (isTLRActivated(2) = isBacteriumAdherent && (any(tlr12) || any(tlr26)),
    and TLR1/TLR6 are gated on the SAME two ligand sets individually), so
    this scenario should be structurally unreachable; asserting it here
    locks the exact gating in place against a future refactor that
    decouples TLR2 from TLR1/TLR6."""
    p = KarrHostInteractionProcess({})
    protein_counts, complex_counts = _ready_count_stores(p)
    _zero_wids(
        p,
        protein_counts,
        complex_counts,
        set(p.tlr12_ligand_wids) | set(p.tlr26_ligand_wids),
    )
    state = _base_state(protein_counts, complex_counts)
    update = p.next_update(1.0, state)

    assert update["cell"].get("host_tlr2_activated", False) is False
    assert update["cell"].get("host_nfkb_activated", False) is False


def test_inflammatory_response_fires_from_antigen_without_nfkb() -> None:
    """isInflammatoryResponseActivated = isNFkBActivated || (isBacteriumAdherent
    && any(antigen)). With NF-kB forced off (no ligands) but an antigen WID
    (MG_075, present in neither adhesin/ligand/terminalOrganelle sets)
    nonzero, inflammatory response must still activate via the antigen
    disjunct alone."""
    p = KarrHostInteractionProcess({})
    protein_counts, complex_counts = _ready_count_stores(p)
    _zero_wids(
        p,
        protein_counts,
        complex_counts,
        set(p.tlr12_ligand_wids)
        | set(p.tlr26_ligand_wids)
        | set(p.antigen_wids),
    )
    protein_counts["MG_075_MONOMER"] = 27.0
    state = _base_state(protein_counts, complex_counts)
    update = p.next_update(1.0, state)

    assert update["cell"].get("host_nfkb_activated", False) is False
    assert update["cell"]["host_inflammatory_response_activated"] is True


def test_no_op_update_when_state_already_matches_computed_cascade() -> None:
    """`next_update` emits a "cell" delta only for fields that actually
    change relative to the incoming state (not an unconditional full
    replace every tick) -- if the incoming cell state already equals the
    freshly-computed cascade, the update dict must be empty."""
    p = KarrHostInteractionProcess({})
    protein_counts, complex_counts = _ready_count_stores(p)
    state = _base_state(
        protein_counts,
        complex_counts,
        cell_state={field: True for field in _ALL_HOST_FIELDS},
    )
    update = p.next_update(1.0, state)
    assert update == {}


def test_no_substrate_enzyme_or_requests_deltas_emitted() -> None:
    p = KarrHostInteractionProcess({})
    protein_counts, complex_counts = _ready_count_stores(p)
    state = _base_state(protein_counts, complex_counts)
    update = p.next_update(1.0, state)

    assert "requests" not in update
    assert "substrates" not in update
    assert "enzymes" not in update
    assert "boundEnzymes" not in update


def test_deterministic_no_rng_same_inputs_same_outputs() -> None:
    """HostInteraction.m has no RNG (see PROCESS_CATALOG.yaml: bucket=
    DETERMINISTIC, rationale_M='no RNG'); two independently constructed
    processes given the same protein counts must produce byte-identical
    update dicts every time, with no seed parameter involved at all."""
    p1 = KarrHostInteractionProcess({})
    p2 = KarrHostInteractionProcess({})
    protein_counts, complex_counts = _ready_count_stores(p1)

    for _ in range(5):
        u1 = p1.next_update(1.0, _base_state(protein_counts, complex_counts))
        u2 = p2.next_update(1.0, _base_state(protein_counts, complex_counts))
        assert u1 == u2


def test_vacuous_empty_index_set_semantics_match_matlab_all_any() -> None:
    """MATLAB `all([])` is true and `any([])` is false -- exercised directly
    against the static helpers (not reachable through the real fixture,
    whose index sets are all non-empty) so a future refactor that
    accidentally short-circuits on emptiness is caught."""
    assert KarrHostInteractionProcess._all_nonzero([], {}) is True
    assert KarrHostInteractionProcess._any_nonzero([], {}) is False
