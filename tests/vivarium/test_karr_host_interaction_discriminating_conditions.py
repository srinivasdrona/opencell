"""Discriminating-condition closure for HostInteraction's L2.1 evidence.

Opus review (2026-09-05) correctly rejected the fitted-seed-0-only
positive-control window as degenerate evidence: a trace where every one of
the 6 host booleans is constant-True for the entire window cannot, by
itself, distinguish a literal, source-faithful boolean cascade from a
hardcoded ``return all-True`` stub. This module closes that gap against the
5 genuine, source-legal, INPUT-SIDE enzyme-knockout conditions preregistered
in ``docs/phase_f/l2_1/HOSTINTERACTION_CONDITION_PREREGISTRATION.md``
(predictions written BEFORE the MATLAB extraction; see
``docs/phase_f/l2_1/HOSTINTERACTION_ACTIVE_WINDOW_DECISION.md`` section 11
for the after-the-fact results comparison) and extracted via
``scripts/matlab/extract_host_interaction_active_window.m``.

Two properties are verified per condition:

1. The literal port (``KarrHostInteractionProcess``) reproduces the genuine
   MATLAB result bit-exact on all 6 host booleans, not just the ones that
   happen to be True.
2. A constant-True stub (the exact degenerate alternative Opus flagged)
   FAILS every negative/partial condition on at least one field -- proving
   these conditions actually discriminate a literal port from a stub,
   which the positive-control-only evidence could not.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import h5py
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

from l2_replay_common import cell_vector, load_fixture_channel_wids  # noqa: E402

from opencell.vivarium.karr_host_interaction import KarrHostInteractionProcess  # noqa: E402

_HOST_FIELDS = (
    "host_attached",
    "host_tlr1_activated",
    "host_tlr2_activated",
    "host_tlr6_activated",
    "host_nfkb_activated",
    "host_inflammatory_response_activated",
)
_HOST_OBSERVABLES = (
    "isBacteriumAdherent",
    "isTLRActivated_1",
    "isTLRActivated_2",
    "isTLRActivated_3",
    "isNFkBActivated",
    "isInflammatoryResponseActivated",
)

# Preregistered predictions (see module docstring). Never edit these
# retroactively to match a wrong extraction result -- a disagreement means
# re-deriving the prediction from source and documenting a dated
# correction in the decision doc, not silently changing the table here.
_PREREGISTERED_PREDICTIONS: dict[str, dict[str, bool]] = {
    "neg_adherence": dict(
        zip(_HOST_FIELDS, (False, False, False, False, False, False), strict=True)
    ),
    "partial_adherent_no_signal": dict(
        zip(_HOST_FIELDS, (True, False, False, False, False, False), strict=True)
    ),
    "tlr12_path": dict(
        zip(_HOST_FIELDS, (True, True, True, False, True, True), strict=True)
    ),
    "tlr26_path": dict(
        zip(_HOST_FIELDS, (True, False, True, True, True, True), strict=True)
    ),
    "antigen_only": dict(
        zip(_HOST_FIELDS, (True, False, False, False, False, True), strict=True)
    ),
}


def _condition_trace_path(condition_id: str) -> Path:
    rel = Path(
        "data/m1_sources/karr_native/"
        f"per_process_traces_v2_host_condition_{condition_id}_s000/HostInteraction_5ticks.mat"
    )
    for candidate in (_REPO_ROOT / rel, Path("E:/opencell") / rel, Path("/mnt/e/opencell") / rel):
        if candidate.exists():
            return candidate
    return _REPO_ROOT / rel


def _load_condition(condition_id: str) -> tuple[np.ndarray, dict[str, bool]]:
    """Return (states_before enzyme-count vector at tick 0, states_after
    host booleans at tick 0), read directly from the genuine MATLAB trace."""
    path = _condition_trace_path(condition_id)
    if not path.exists():
        pytest.skip(
            f"Discriminating condition trace not found: {path}. Regenerate via "
            "scripts/matlab/extract_host_interaction_active_window.m (MATLAB required; "
            "gitignored data artifact, not committed)."
        )
    with h5py.File(path, "r") as trace:
        enzymes_before = cell_vector(trace, "states_before", "enzymes", 0)
        after = {
            field: bool(float(cell_vector(trace, "states_after", observable, 0)[0]))
            for field, observable in zip(_HOST_FIELDS, _HOST_OBSERVABLES, strict=True)
        }
    return enzymes_before, after


@pytest.fixture(scope="module")
def process() -> KarrHostInteractionProcess:
    return KarrHostInteractionProcess({})


@pytest.mark.parametrize("condition_id", sorted(_PREREGISTERED_PREDICTIONS))
def test_genuine_condition_matches_preregistered_prediction(condition_id: str) -> None:
    """The MATLAB extraction itself must match what was predicted BEFORE it
    ran (docs/phase_f/l2_1/HOSTINTERACTION_CONDITION_PREREGISTRATION.md). A
    disagreement here means the prediction (source reading) was wrong, not
    the trace -- see that document's preregistered acceptance rule."""
    _, karr_after = _load_condition(condition_id)
    assert karr_after == _PREREGISTERED_PREDICTIONS[condition_id]


@pytest.mark.parametrize("condition_id", sorted(_PREREGISTERED_PREDICTIONS))
def test_literal_port_reproduces_genuine_condition_bit_exact(
    process: KarrHostInteractionProcess, condition_id: str
) -> None:
    """Feed the REAL extracted MATLAB enzyme counts (states_before/enzymes,
    the genuine `this.enzymes` values under the preregistered knockout) into
    the literal OC port and assert bit-exact agreement with the genuine
    MATLAB states_after result on ALL SIX host booleans -- not just the
    ones happening to be True."""
    enzymes_before, karr_after = _load_condition(condition_id)
    wids = load_fixture_channel_wids("HostInteraction", "enzymes")
    assert len(wids) == enzymes_before.shape[0], (
        "Fixture enzyme WID count must match the trace's enzyme vector length "
        "(same enzymeWholeCellModelIDs ordering used by both)."
    )
    protein_counts = {wid: float(value) for wid, value in zip(wids, enzymes_before, strict=True)}

    state = {"cell": {}, "protein": {"counts": protein_counts}}
    update = process.next_update(1.0, state)
    cell_update = update.get("cell", {})
    computed = {field: cell_update.get(field, False) for field in _HOST_FIELDS}

    assert computed == karr_after


class _ConstantTrueStub:
    """The exact degenerate alternative Opus flagged: a process that always
    reports every host boolean True regardless of input. Used only to
    prove the discriminating conditions below actually discriminate --
    never used as a stand-in for the real process anywhere else."""

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep, states
        return {"cell": dict.fromkeys(_HOST_FIELDS, True)}


@pytest.mark.parametrize("condition_id", sorted(_PREREGISTERED_PREDICTIONS))
def test_constant_true_stub_fails_every_negative_or_partial_condition(condition_id: str) -> None:
    """Preregistered acceptance rule (see
    docs/phase_f/l2_1/HOSTINTERACTION_CONDITION_PREREGISTRATION.md
    'Acceptance rule'): a trivial always-True stub MUST fail
    NEG_ADHERENCE, PARTIAL_ADHERENT_NO_SIGNAL, TLR12_PATH (on
    host_tlr6_activated), TLR26_PATH (on host_tlr1_activated), and
    ANTIGEN_ONLY (on host_nfkb_activated) -- i.e. every non-POSITIVE
    condition must diverge from constant-True on at least one field. This
    is what makes this evidence non-degenerate: the positive-control trace
    alone (all 6 booleans constant-True) cannot distinguish the real
    literal port from this stub, but these 5 conditions can."""
    _, karr_after = _load_condition(condition_id)
    stub_update = _ConstantTrueStub().next_update(1.0, {})["cell"]

    mismatches = {field for field in _HOST_FIELDS if stub_update[field] != karr_after[field]}
    assert mismatches, (
        f"Constant-True stub unexpectedly matched genuine condition {condition_id!r} "
        "on every field -- this condition has lost its discriminating power."
    )
