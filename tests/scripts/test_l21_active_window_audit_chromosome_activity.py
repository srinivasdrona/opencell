"""Regression tests for the l21_active_window_audit chromosome-activity fix.

Prior to this fix, `_honest_replay` determined OC "activity" for
CHROMOSOME_ACTIVITY_TOKENS processes (DNARepair, Replication, DNADamage) by
checking whether the raw ``process.next_update()`` return dict was
non-trivial (``_recursive_update_nontrivial``), including whenever the
process emitted a chromosome sparse-field replacement payload -- even one
whose values were byte-identical to the field's existing (before-tick)
value, or whose only "nonzero" content was the field's unconditional,
never-empty ``shape`` tuple. That produced impossibly high OC "active tick"
counts (e.g. 20/20 for DNADamage, versus an accepted ~92-events/1000-ticks
reference rate) that did not reflect any real biological event.

The fix computes activity from the declared chromosome projection tokens'
before->after *values* (via `_chromosome_projection_component`, the same
authoritative projection used for the bit-identity comparison itself),
after first applying the chromosome update with REPLACE (not
recursive-merge) semantics -- matching each process's own authoritative
replay harness (e.g. `test_karr_dna_damage_l2_replay.py::_apply_update`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
if str(REPO_ROOT / "tests" / "vivarium") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tests" / "vivarium"))

import l21_active_window_audit as active_windows  # noqa: E402

from opencell.state.chromosome_store import ChromosomeStore, SparseTriplet  # noqa: E402

_SHAPE = (100, 2)


def _store_with_field(field: str, positions: list[int], strands: list[int], values: list[int]) -> ChromosomeStore:
    triplet = SparseTriplet(
        positions=np.asarray(positions, dtype="int64"),
        strands=np.asarray(strands, dtype="int64"),
        values=np.asarray(values, dtype="int64"),
        shape=_SHAPE,
    )
    return ChromosomeStore(shape=_SHAPE, fields={field: triplet})


def test_unchanged_nonempty_sparse_replacement_is_not_flagged_active():
    # Same single edge on both sides: this is what a process replaying its
    # *current* (carried-over, no new damage) sparse state every tick looks
    # like. A naive update-dict-truthiness check would flag this as active
    # merely because the replacement payload is non-empty; the corrected,
    # value-based check must not.
    before = _store_with_field("intrastrandCrossLinks", [10], [0], [1])
    after = _store_with_field("intrastrandCrossLinks", [10], [0], [1])

    assert (
        active_windows._chromosome_tokens_active(  # type: ignore[attr-defined]
            "DNADamage", before, after
        )
        is False
    )


def test_one_edge_addition_is_flagged_active():
    before = _store_with_field("intrastrandCrossLinks", [10], [0], [1])
    after = _store_with_field("intrastrandCrossLinks", [10, 20], [0, 1], [1, 1])

    assert (
        active_windows._chromosome_tokens_active(  # type: ignore[attr-defined]
            "DNADamage", before, after
        )
        is True
    )


def test_no_stores_is_not_flagged_active():
    assert (
        active_windows._chromosome_tokens_active(  # type: ignore[attr-defined]
            "DNADamage", None, None
        )
        is False
    )


def test_apply_chromosome_sparse_replace_overwrites_not_merges_stale_entries():
    # A field's prior (stale) state has an edge at position 5 that is NOT
    # present in this tick's replacement payload (position 10 only) -- the
    # process's own authoritative semantics is REPLACE, so position 5 must
    # not survive.
    state: dict[str, object] = {
        "chromosome": {
            "intrastrandCrossLinks": SparseTriplet(
                positions=np.asarray([5], dtype="int64"),
                strands=np.asarray([0], dtype="int64"),
                values=np.asarray([1], dtype="int64"),
                shape=_SHAPE,
            ).to_state()
        }
    }
    chromosome_update = {
        "intrastrandCrossLinks": SparseTriplet(
            positions=np.asarray([10], dtype="int64"),
            strands=np.asarray([0], dtype="int64"),
            values=np.asarray([1], dtype="int64"),
            shape=_SHAPE,
        ).to_state()
    }

    active_windows._apply_chromosome_sparse_replace(  # type: ignore[attr-defined]
        state, chromosome_update, shape=_SHAPE
    )

    result_store = ChromosomeStore.from_state_mapping(state["chromosome"], shape=_SHAPE)
    triplet = result_store.get_field("intrastrandCrossLinks")
    assert triplet.positions.tolist() == [10]


def test_apply_chromosome_sparse_replace_accepts_raw_sparsetriplet_payload():
    # Guards the edge case that motivated this fix: a process that emits a
    # raw SparseTriplet instance (not already `.to_state()`-flattened) for a
    # chromosome field. `_deep_merge_replace`'s generic dict-merge silently
    # drops such a field (ChromosomeStore.from_state_mapping only accepts
    # Mapping payloads); the dedicated replace path must handle it via
    # SparseTriplet.from_state's native SparseTriplet passthrough.
    state: dict[str, object] = {"chromosome": {}}
    chromosome_update = {
        "intrastrandCrossLinks": SparseTriplet(
            positions=np.asarray([7], dtype="int64"),
            strands=np.asarray([1], dtype="int64"),
            values=np.asarray([1], dtype="int64"),
            shape=_SHAPE,
        )
    }

    active_windows._apply_chromosome_sparse_replace(  # type: ignore[attr-defined]
        state, chromosome_update, shape=_SHAPE
    )

    result_store = ChromosomeStore.from_state_mapping(state["chromosome"], shape=_SHAPE)
    triplet = result_store.get_field("intrastrandCrossLinks")
    assert triplet.positions.tolist() == [7]
