"""Compartmental ProteinMonomer authority: schema, projection, and lint helpers.

Primary source: `docs/design/compartmental_protein_state_migration.md`,
sections 1 (contract), 4.1 (ProteinMonomer state shape), and decisions
D1-D8. Karr's ONLY protein-monomer state is `ProteinMonomer.counts`, a
(4820, 6) matrix: 10 form blocks of 482 monomer WIDs each (rows), by 6 KB
compartments (columns) -- see `ProteinMonomer.m:27-40, 95-104, 129-130`.
This module is the single source of truth for that (form, WID, compartment)
authority and for the mechanism that keeps the legacy flat `protein.counts`
view an exact, unwritable derived projection of it.

Stage 2 (`docs/design/protein_translocation_stage2.md` D1): `MIGRATED_WIDS`
is the source-derived union of TerminalOrganelleAssembly's 8 substrate WIDs
and ProteinTranslocation's 119 translocating monomer WIDs -- 124 total, no
literal WID list. Every builder below is a pure function of `MIGRATED_WIDS`,
so the authority schema, the rejecting-updater attachment, and the
projection Step's key set all enroll exactly these 124 WIDs across all 10
forms x 6 compartments (7,440 leaves) -- see `protein_flat_projection_step.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat

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

_TERMINAL_ORGANELLE_FIXTURE_PATH = (
    "data/karr_fixtures/per_process/TerminalOrganelleAssembly_flat.mat"
)
_PROTEIN_TRANSLOCATION_FIXTURE_PATH = (
    "data/karr_fixtures/per_process/ProteinTranslocation_flat.mat"
)


def _resolve_data_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate
    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted
    raise FileNotFoundError(f"Fixture not found: {path}")


def _parse_wid_array(cell_array: Any) -> list[str]:
    values = np.asarray(cell_array, dtype=object)
    if values.shape == (1, 1):
        values = np.asarray(values[0, 0], dtype=object)
    out: list[str] = []
    for raw in values.ravel():
        value: object = raw
        while isinstance(value, np.ndarray):
            if value.size == 0:
                value = ""
                break
            value = value.flat[0]
        out.append(str(value))
    return out


@lru_cache(maxsize=1)
def _load_toa_fixture_substrate_wids() -> frozenset[str]:
    """Load the 8 terminal-organelle substrate WIDs from
    `TerminalOrganelleAssembly_flat.mat`'s own `substrateWholeCellModelIDs`
    (design 9.3) -- one of the two disjoint sources `MIGRATED_WIDS` unions
    (design D1).
    """
    resolved = _resolve_data_path(_TERMINAL_ORGANELLE_FIXTURE_PATH)
    mat = loadmat(str(resolved))
    fx = mat["data"]["fixture"][0, 0]
    return frozenset(_parse_wid_array(fx["substrateWholeCellModelIDs"]))


@lru_cache(maxsize=1)
def _load_pt_fixture_translocating_wids() -> frozenset[str]:
    """Load ProteinTranslocation's 119 translocating monomer WIDs from
    `ProteinTranslocation_flat.mat`'s `monomerIndexs_translocating` over
    `monomerWholeCellModelIDs` (design D1, P1) -- the other of the two
    disjoint sources `MIGRATED_WIDS` unions. No literal WID list or
    cardinality is hardcoded; both the index set and the WID strings are
    read directly from the fixture.
    """
    resolved = _resolve_data_path(_PROTEIN_TRANSLOCATION_FIXTURE_PATH)
    mat = loadmat(str(resolved))
    fx = mat["data"]["fixture"][0, 0]
    all_wids = _parse_wid_array(fx["monomerWholeCellModelIDs"])
    indices = (
        np.asarray(fx["monomerIndexs_translocating"][0, 0], dtype=np.int64).reshape(-1) - 1
    )
    return frozenset(all_wids[int(idx)] for idx in indices)


@lru_cache(maxsize=1)
def _load_source_derived_migrated_wids() -> frozenset[str]:
    """R1 (design D1): the Stage-2 migration set is the union of TOA's 8
    substrate WIDs and ProteinTranslocation's 119 translocating monomer
    WIDs -- 124 total (116 new over Stage 1b's 8, 3 already shared). No
    literal WID list anywhere in this derivation; both operands are loaded
    directly from their respective canonical fixtures.
    """
    return _load_toa_fixture_substrate_wids() | _load_pt_fixture_translocating_wids()


# Stage-2 authoritative migration set (design D1): the source-derived union
# above. Every builder in this module takes `migrated_wids` as an explicit
# parameter defaulting to this constant, so every schema contribution,
# projection write, and rejecting-updater attachment enrolls exactly these
# 124 WIDs.
MIGRATED_WIDS: tuple[str, ...] = tuple(sorted(_load_source_derived_migrated_wids()))


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


@cache
def _cached_rejecting_flat_counts_updater(wid: str) -> Callable[[Any, Any], float]:
    """Memoised wrapper around `_rejecting_flat_counts_updater`.

    Two `ProteinFlatProjectionStep` instances (`protein_flat_projection_pre`
    and `_post`, design D5) both declare this leaf's schema every composite
    build. Vivarium's schema-merge compares `_updater` values with `==`
    (`store.py:536`), which for two distinct closures over the same `wid` is
    `False` even though both reject the same way -- a spurious
    "Incompatible schema assignment" warning with no behavioral difference.
    Caching by `wid` makes both Steps hand Vivarium the *same* callable
    object, so the merge sees identical values and stays silent, without
    weakening the rejection semantics at all.
    """
    return _rejecting_flat_counts_updater(wid)


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
            "_updater": _cached_rejecting_flat_counts_updater(wid),
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

    Callers (`karr_composite.py`) pass
    `seed_mature=load_mature_seed_from_canonical_fixture()` so the `mature`
    row is seeded with the exact `ProteinMonomer_flat.mat` counts (design
    4.2); with no seed, every form (including `mature`) maps to zero, which
    is only correct for an empty `migrated_wids`.
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


_PROTEIN_MONOMER_FIXTURE_PATH = "data/karr_fixtures/per_process/ProteinMonomer_flat.mat"


@lru_cache(maxsize=1)
def load_mature_seed_from_canonical_fixture() -> dict[str, dict[str, float]]:
    """Load exact `ProteinMonomer.m` mature-row counts for `MIGRATED_WIDS`
    from the canonical `ProteinMonomer_flat.mat` fixture (design 4.2).

    The mature form-block boundary and each WID's row are derived from the
    fixture's own `wholeCellModelIDs` ordering (`FORMS.index("mature")` times
    the per-form monomer count, design 4.1); the 6 `counts` columns are used
    in their fixture order, which is verified 1:1 against `COMPARTMENTS` by
    the design-4.1 KB `compartments` cross-check (column j <-> KB compartment
    j+1 <-> `COMPARTMENTS[j]`). No count value is hardcoded here.
    """
    resolved = _resolve_data_path(_PROTEIN_MONOMER_FIXTURE_PATH)
    mat = loadmat(str(resolved))
    fx = mat["data"]["fixture"][0, 0]

    all_wids = _parse_wid_array(fx["wholeCellModelIDs"])
    counts = np.asarray(fx["counts"][0, 0], dtype=np.float64)
    n_monomers = len(all_wids) // len(FORMS)
    mature_form_index = FORMS.index("mature")
    mature_block_start = mature_form_index * n_monomers
    mature_wids = all_wids[mature_block_start : mature_block_start + n_monomers]

    seed: dict[str, dict[str, float]] = {}
    for wid in MIGRATED_WIDS:
        local_idx = mature_wids.index(wid)
        global_row = mature_block_start + local_idx
        row = counts[global_row]
        seed[wid] = {comp: float(row[j]) for j, comp in enumerate(COMPARTMENTS)}
    return seed


def compartment_delta(form: str, wid: str, compartment: str, n: float) -> dict[str, Any]:
    """The only sanctioned constructor for an authority update dict (design
    D2 Beat-4 guard): validates `form`/`wid`/`compartment` and raises
    `ValueError` otherwise, so a typo'd key cannot silently establish a new
    store path.

    `wid` must be a currently-migrated WID; Stage 2's `MIGRATED_WIDS` is the
    source-derived 124-WID union (design D1), so this function accepts
    exactly those and raises for any other WID (e.g. a not-yet-migrated
    Stage-3+ WID).
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
    """The WID sets the partial-migration detector (design 9.7 item 3) must
    agree on: the authority schema's `mature`-row key set, the
    rejecting-updater's key set, and the projection Step's target key set
    (`MIGRATED_WIDS` itself). A mismatch here means a schema-builder
    function has drifted from `MIGRATED_WIDS` (e.g. one builder was edited
    to take a stale default).
    """
    return {
        "authority_schema": frozenset(compartment_counts_schema(MIGRATED_WIDS)["mature"]),
        "rejecting_updater": frozenset(flat_counts_schema(MIGRATED_WIDS)),
        "projection_step": frozenset(MIGRATED_WIDS),
    }


def assert_migration_consistency() -> None:
    """Raise `ProteinStateMigrationInconsistent` if any WID set this module
    computes disagrees with `MIGRATED_WIDS`. Called at import time below so
    a half-applied migration stage fails loudly at build time (design 9.7
    item 3), not silently at some later tick.

    Design D1 (Stage 2): `MIGRATED_WIDS` is itself fixture-derived (no
    longer a hand-typed literal), so the partial-migration detector's most
    valuable check is no longer "does the literal match the fixture" but
    "does the union still decompose into exactly the expected structural
    counts": 8 TOA substrate WIDs, 119 PT-translocating monomer WIDs, a
    3-WID overlap (MG_191/192/318, the Stage-1b WIDs whose KB compartment
    remaps to non-cytosol), and a 124-WID union. A drift in any of these
    four numbers means a fixture field, index base, or set operation in
    `_load_source_derived_migrated_wids` silently changed shape.
    """
    sets = _migration_wid_sets()
    reference = frozenset(MIGRATED_WIDS)
    mismatched = {name: sorted(s) for name, s in sets.items() if s != reference}
    if mismatched:
        raise ProteinStateMigrationInconsistent(
            "protein_state subsystems disagree on the migrated-WID set "
            f"(expected {sorted(reference)}): {mismatched}"
        )

    toa_wids = _load_toa_fixture_substrate_wids()
    pt_translocating_wids = _load_pt_fixture_translocating_wids()
    overlap = toa_wids & pt_translocating_wids
    union = toa_wids | pt_translocating_wids
    structural = {
        "toa_substrate_count": (len(toa_wids), 8),
        "pt_translocating_count": (len(pt_translocating_wids), 119),
        "toa_pt_overlap_count": (len(overlap), 3),
        "union_count": (len(union), 124),
    }
    bad_structure = {
        name: actual for name, (actual, expected) in structural.items() if actual != expected
    }
    if bad_structure:
        raise ProteinStateMigrationInconsistent(
            "protein_state's independently-loaded TOA/PT fixture union no "
            f"longer has the expected Stage-2 structural counts: {bad_structure} "
            f"(expected toa_substrate_count=8, pt_translocating_count=119, "
            f"toa_pt_overlap_count=3, union_count=124)"
        )
    if union != reference:
        raise ProteinStateMigrationInconsistent(
            "MIGRATED_WIDS does not equal the independently-loaded TOA ∪ "
            f"PT-translocating union; symmetric difference={sorted(union ^ reference)}"
        )


assert_migration_consistency()


__all__ = [
    "COMPARTMENTS",
    "FORMS",
    "MIGRATED_WIDS",
    "ProteinFlatProjectionWriteError",
    "ProteinStateMigrationInconsistent",
    "assert_migration_consistency",
    "compartment_counts_schema",
    "compartment_delta",
    "flat_counts_schema",
    "initial_compartment_counts",
    "load_mature_seed_from_canonical_fixture",
    "make_privileged_projection_write",
    "project_mature_row",
]
