"""Compartmental ProteinMonomer authority: schema, projection, and lint helpers.

Primary source: `docs/design/compartmental_protein_state_migration.md`,
sections 1 (contract), 4.1 (ProteinMonomer state shape), and decisions
D1-D8. Karr's ONLY protein-monomer state is `ProteinMonomer.counts`, a
(4820, 6) matrix: 10 form blocks of 482 monomer WIDs each (rows), by 6 KB
compartments (columns) -- see `ProteinMonomer.m:27-40, 95-104, 129-130`.
This module is the single source of truth for that (form, WID, compartment)
authority and for the mechanism that keeps the legacy flat `protein.counts`
view an exact, unwritable derived projection of it.

Stage 1a (this commit): `MIGRATED_WIDS` is the empty tuple. Every builder
below is a pure function of `MIGRATED_WIDS`, so an empty migrated set makes
every schema contribution, projection write, and rejecting-updater
attachment empty as well -- the module is loaded and exercised, but it
changes nothing observable (see `protein_flat_projection_step.py`).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

# Karr's 10 protein-monomer form blocks, in `ProteinMonomer.m:95-104` order.
FORMS: tuple[str, ...] = (
    "nascent",
    "processed_i",
    "processed_ii",
    "signal_sequence",
    "folded",
    "mature",
    "inactivated",
    "bound",
    "misfolded",
    "damaged",
)

# Karr's 6 KB compartment ids (design 4.1 table): cytosol, DNA/chromosome,
# extracellular, membrane, terminal-organelle-cytosol, terminal-organelle-
# membrane. `d` is the one inferred entry (never populated by monomers; see
# design 4.1 Beat-4 inversion); no arithmetic in this module depends on it.
COMPARTMENTS: tuple[str, ...] = ("c", "d", "e", "m", "tc", "tm")

# Stage-1a authoritative migration set: EMPTY. Every builder in this module
# takes `migrated_wids` as an explicit parameter defaulting to this constant,
# so "no WID is migrated yet" is enforced structurally, not by convention.
MIGRATED_WIDS: tuple[str, ...] = ()

# NON-AUTHORITATIVE. This is documentation of the Stage-1b target (design
# 9.3), not a schema input. No builder in this module reads this constant;
# only Stage-1b code may set `MIGRATED_WIDS` to (an equivalent of) it.
PENDING_STAGE_1B_TERMINAL_ORGANELLE_WIDS: tuple[str, ...] = (
    "MG_191_MONOMER",
    "MG_192_MONOMER",
    "MG_217_MONOMER",
    "MG_218_MONOMER",
    "MG_312_MONOMER",
    "MG_317_MONOMER",
    "MG_318_MONOMER",
    "MG_386_MONOMER",
)


class ProteinFlatProjectionWriteError(Exception):
    """Raised when production code attempts to write the derived flat
    `protein.counts` leaf directly instead of through the projection Step.

    Design D3: the flat view is `Pi(authority)`, recomputed and overwritten
    every tick by `ProteinFlatProjectionStep`. It is not a second authority;
    any other writer of this leaf is, by definition, a dual-write bug.
    """


class ProteinStateMigrationInconsistent(Exception):  # noqa: N818 -- name fixed by design 9.7 item 3
    """Raised when the migrated-WID set disagrees across the authority
    schema, the rejecting-updater attachment set, and the projection Step's
    key set (design 9.7 item 3: the partial-migration detector).
    """


class _ProteinProjectionSentinel:
    """Private write token for the flat-projection Step's privileged write.

    Ordinary production process updates return plain numeric deltas (float/
    int); they cannot accidentally construct an instance of this class, so
    the rejecting updater below can distinguish "the projection Step wrote
    this" from "any other caller wrote this" purely by `isinstance`, with no
    reliance on a forgeable string/dict-key sentinel. Only
    `make_privileged_projection_write` (below) constructs one, and only
    `protein_flat_projection_step.py` calls that function.
    """

    __slots__ = ("value",)

    def __init__(self, value: float) -> None:
        self.value = float(value)


def make_privileged_projection_write(value: float) -> _ProteinProjectionSentinel:
    """Construct the privileged write token for one flat `protein.counts`
    leaf. Exclusively for use by `ProteinFlatProjectionStep.next_update`; no
    other production code may call this.
    """
    return _ProteinProjectionSentinel(value)


def _rejecting_flat_counts_updater(wid: str) -> Callable[[Any, Any], float]:
    """Build the per-WID rejecting updater callable described by design D3.

    Vivarium calls `updater(current_value, update_value)` for every update
    reaching this leaf (`store.py:1636-1660`). Any `update_value` that is not
    the privileged sentinel raises `ProteinFlatProjectionWriteError` naming
    the store path; the sentinel path returns its wrapped absolute value
    (the projection Step always overwrites the full flat map, never
    accumulates -- design D3 rationale).
    """

    def _updater(current_value: Any, update_value: Any) -> float:
        del current_value
        if isinstance(update_value, _ProteinProjectionSentinel):
            return float(update_value.value)
        raise ProteinFlatProjectionWriteError(
            "Direct writes to the derived flat protein.counts leaf are "
            f"forbidden: path=('protein', 'counts', {wid!r}). This leaf is "
            "produced exclusively by ProteinFlatProjectionStep from the "
            "protein.compartment_counts authority (design D3)."
        )

    return _updater


def flat_counts_schema(
    migrated_wids: Sequence[str] = MIGRATED_WIDS,
) -> dict[str, dict[str, Any]]:
    """Vivarium schema patch for the flat `protein.counts` leaves of every
    migrated WID: default 0.0, rejecting callable updater, emitted.

    With `migrated_wids` empty (Stage 1a) this returns `{}`: no leaf gets the
    rejecting updater attached anywhere (design 9.2: "the rejecting updater
    is attached to nothing").
    """
    return {
        wid: {
            "_default": 0.0,
            "_updater": _rejecting_flat_counts_updater(wid),
            "_emit": True,
        }
        for wid in migrated_wids
    }


def compartment_counts_schema(
    migrated_wids: Sequence[str] = MIGRATED_WIDS,
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    """Vivarium schema for the `protein.compartment_counts` authority:
    `{form: {wid: {compartment: leaf_schema}}}` for every migrated WID.

    Leaves use the standard `accumulate` updater (ordinary process deltas
    merge additively; D2 rationale) and are not emitted by default (`_emit:
    False`) -- the flat view remains the emitted compatibility surface.

    With `migrated_wids` empty (Stage 1a) every form maps to `{}`: zero
    leaves, matching "480 leaves at Stage 1b, 0 at Stage 1a" (design D1/D2).
    """
    return {
        form: {
            wid: {
                comp: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for comp in COMPARTMENTS
            }
            for wid in migrated_wids
        }
        for form in FORMS
    }


def initial_compartment_counts(
    migrated_wids: Sequence[str] = MIGRATED_WIDS,
    seed_mature: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, dict[str, dict[str, float]]]:
    """Initial-state values for `protein.compartment_counts`: `{form: {wid:
    {compartment: count}}}` for every migrated WID, all forms zero except an
    optional caller-supplied seed for the `mature` row (design 4.2/9.3).

    With `migrated_wids` empty (Stage 1a) every form maps to `{}` -- the
    branch exists (satisfying C13's `"compartment_counts" in
    state["protein"]` precondition) but holds no WIDs.
    """
    seed_mature = seed_mature or {}
    result: dict[str, dict[str, dict[str, float]]] = {form: {} for form in FORMS}
    for wid in migrated_wids:
        mature_row = seed_mature.get(wid, {})
        for form in FORMS:
            row = mature_row if form == "mature" else {}
            result[form][wid] = {comp: float(row.get(comp, 0.0)) for comp in COMPARTMENTS}
    return result


def project_mature_row(mature_row: Mapping[str, float]) -> float:
    """Pi: the flat-view projection of one WID's mature row -- the sum over
    all 6 compartments (design D6: "flat = sum over all 6 compartments of the
    MATURE row").
    """
    return float(sum(mature_row.get(comp, 0.0) for comp in COMPARTMENTS))


def compartment_delta(form: str, wid: str, compartment: str, n: float) -> dict[str, Any]:
    """The only sanctioned constructor for an authority update dict (design
    D2 Beat-4 guard): validates `form`/`wid`/`compartment` and raises
    `ValueError` otherwise, so a typo'd key cannot silently establish a new
    store path.

    `wid` must be a currently-migrated WID: Stage 1a has none, so this
    function always raises for any WID in this commit -- there is no caller
    yet, which is the correct, behavior-neutral state.
    """
    if form not in FORMS:
        raise ValueError(f"Unknown protein form {form!r}; must be one of {FORMS}")
    if wid not in MIGRATED_WIDS:
        raise ValueError(
            f"WID {wid!r} is not in MIGRATED_WIDS ({MIGRATED_WIDS!r}); cannot "
            "construct an authority delta for an unmigrated WID"
        )
    if compartment not in COMPARTMENTS:
        raise ValueError(
            f"Unknown compartment {compartment!r}; must be one of {COMPARTMENTS}"
        )
    return {
        "protein": {
            "compartment_counts": {
                form: {wid: {compartment: float(n)}},
            }
        }
    }


def _migration_wid_sets() -> dict[str, frozenset[str]]:
    """The four WID sets the partial-migration detector (design 9.7 item 3)
    must agree on: the authority schema's `mature`-row key set, the
    rejecting-updater's key set, the projection Step's target key set
    (`MIGRATED_WIDS` itself), and this module's declared legacy-exclusion
    set (the set of WIDs every legacy branch must NOT contain -- by
    definition, exactly `MIGRATED_WIDS`).
    """
    return {
        "authority_schema": frozenset(compartment_counts_schema(MIGRATED_WIDS)["mature"]),
        "rejecting_updater": frozenset(flat_counts_schema(MIGRATED_WIDS)),
        "projection_step": frozenset(MIGRATED_WIDS),
        "legacy_exclusion": frozenset(MIGRATED_WIDS),
    }


def assert_migration_consistency() -> None:
    """Raise `ProteinStateMigrationInconsistent` if the four WID sets in
    `_migration_wid_sets` disagree. Called at import time below so a
    half-applied migration stage fails loudly at build time (design 9.7
    item 3), not silently at some later tick.
    """
    sets = _migration_wid_sets()
    reference = frozenset(MIGRATED_WIDS)
    mismatched = {name: sorted(s) for name, s in sets.items() if s != reference}
    if mismatched:
        raise ProteinStateMigrationInconsistent(
            "protein_state subsystems disagree on the migrated-WID set "
            f"(expected {sorted(reference)}): {mismatched}"
        )


assert_migration_consistency()


__all__ = [
    "COMPARTMENTS",
    "FORMS",
    "MIGRATED_WIDS",
    "PENDING_STAGE_1B_TERMINAL_ORGANELLE_WIDS",
    "ProteinFlatProjectionWriteError",
    "ProteinStateMigrationInconsistent",
    "assert_migration_consistency",
    "compartment_counts_schema",
    "compartment_delta",
    "flat_counts_schema",
    "initial_compartment_counts",
    "make_privileged_projection_write",
    "project_mature_row",
]
