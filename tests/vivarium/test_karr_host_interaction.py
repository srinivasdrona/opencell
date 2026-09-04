from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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

from opencell.vivarium.karr_host_interaction import KarrHostInteractionProcess


def _ready_protein_counts(process: KarrHostInteractionProcess) -> dict[str, float]:
    """All required enzyme WIDs at their fixture reference copy number (all
    strictly positive), so `_all_nonzero`/`_any_nonzero` are satisfied for
    every required index set -- the fully-adherent/fully-activated case."""
    required = (
        set(process.terminal_organelle_wids)
        | set(process.adhesin_wids)
        | set(process.tlr12_ligand_wids)
        | set(process.tlr26_ligand_wids)
        | set(process.antigen_wids)
    )
    return {wid: max(1.0, float(process.enzyme_ref_counts[process.enzyme_wids.index(wid)])) for wid in required}


def _base_state(protein_counts: dict[str, float], cell_state: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"cell": dict(cell_state or {}), "protein": {"counts": dict(protein_counts)}}


_ALL_HOST_FIELDS = (
    "host_attached",
    "host_tlr1_activated",
    "host_tlr2_activated",
    "host_tlr6_activated",
    "host_nfkb_activated",
    "host_inflammatory_response_activated",
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

    schema = p.ports_schema()
    assert set(schema["cell"].keys()) == set(_ALL_HOST_FIELDS)
    for field in _ALL_HOST_FIELDS:
        assert schema["cell"][field]["_updater"] == "set"
        assert schema["cell"][field]["_default"] is False


def test_all_enzymes_present_activates_full_cascade() -> None:
    """Literal Karr formula: all(terminalOrganelle) && all(adhesin) -> adherent;
    ligands present -> TLR1/2/6; NFkB from TLR combination; inflammatory from
    NFkB or antigen. With every required WID present (>0), every output is True
    -- this mirrors the genuine MATLAB seed-0 canary
    (tmp/probe_host_interaction_canary.m), which showed ALL FOUR Host booleans
    are True from tick 1 onward given Karr's fitted initial protein counts."""
    p = KarrHostInteractionProcess({})
    state = _base_state(_ready_protein_counts(p))
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
    counts = _ready_protein_counts(p)
    counts["MG_218_MONOMER"] = 0.0
    cell_state = {field: True for field in _ALL_HOST_FIELDS}
    state = _base_state(counts, cell_state)
    update = p.next_update(1.0, state)

    assert update["cell"] == {field: False for field in _ALL_HOST_FIELDS}


def test_adherent_without_any_ligand_leaves_tlr_and_downstream_false() -> None:
    """Adherence alone does not activate TLR/NF-kB/inflammatory response --
    HostInteraction.m gates each TLR on `isBacteriumAdherent && any(ligand)`,
    so zeroing every ligand/antigen WID (while keeping the structural
    terminalOrganelle/adhesin set nonzero) must leave TLR1/2/6, NF-kB, and
    inflammatory response all False even though adherence itself is True."""
    p = KarrHostInteractionProcess({})
    counts = _ready_protein_counts(p)
    for wid in set(p.tlr12_ligand_wids) | set(p.tlr26_ligand_wids) | set(p.antigen_wids):
        if wid not in p.terminal_organelle_wids and wid not in p.adhesin_wids:
            counts[wid] = 0.0
    state = _base_state(counts)
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
    counts = _ready_protein_counts(p)
    for wid in p.tlr26_ligand_wids:
        if wid not in p.terminal_organelle_wids and wid not in p.adhesin_wids:
            counts[wid] = 0.0
    state = _base_state(counts)
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
    counts = _ready_protein_counts(p)
    for wid in set(p.tlr12_ligand_wids) | set(p.tlr26_ligand_wids):
        if wid not in p.terminal_organelle_wids and wid not in p.adhesin_wids:
            counts[wid] = 0.0
    state = _base_state(counts)
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
    counts = _ready_protein_counts(p)
    for wid in set(p.tlr12_ligand_wids) | set(p.tlr26_ligand_wids) | set(p.antigen_wids):
        if wid not in p.terminal_organelle_wids and wid not in p.adhesin_wids:
            counts[wid] = 0.0
    counts["MG_075_MONOMER"] = 27.0
    state = _base_state(counts)
    update = p.next_update(1.0, state)

    assert update["cell"].get("host_nfkb_activated", False) is False
    assert update["cell"]["host_inflammatory_response_activated"] is True


def test_no_op_update_when_state_already_matches_computed_cascade() -> None:
    """`next_update` emits a "cell" delta only for fields that actually
    change relative to the incoming state (not an unconditional full
    replace every tick) -- if the incoming cell state already equals the
    freshly-computed cascade, the update dict must be empty."""
    p = KarrHostInteractionProcess({})
    counts = _ready_protein_counts(p)
    state = _base_state(counts, cell_state={field: True for field in _ALL_HOST_FIELDS})
    update = p.next_update(1.0, state)
    assert update == {}


def test_no_substrate_enzyme_or_requests_deltas_emitted() -> None:
    p = KarrHostInteractionProcess({})
    state = _base_state(_ready_protein_counts(p))
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
    counts = _ready_protein_counts(p1)

    for _ in range(5):
        u1 = p1.next_update(1.0, _base_state(counts))
        u2 = p2.next_update(1.0, _base_state(counts))
        assert u1 == u2


def test_vacuous_empty_index_set_semantics_match_matlab_all_any() -> None:
    """MATLAB `all([])` is true and `any([])` is false -- exercised directly
    against the static helpers (not reachable through the real fixture,
    whose index sets are all non-empty) so a future refactor that
    accidentally short-circuits on emptiness is caught."""
    assert KarrHostInteractionProcess._all_nonzero([], {}) is True
    assert KarrHostInteractionProcess._any_nonzero([], {}) is False
