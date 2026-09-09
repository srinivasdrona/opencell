"""Vivarium Process for Karr transcriptional regulation binding + fold-changes.

Genuine Karr port (site-level, strand-aware TF-promoter binding).
``TranscriptionalRegulation.m`` (``data/m1_sources/WholeCell/src/+edu/
+stanford/+covert/+cell/+sim/+process/TranscriptionalRegulation.m``) models
TF-promoter binding at the level of individual chromosome binding *sites*
(one row per (transcription factor, transcription unit) relationship, two
chromosome-copy columns each), not at the level of aggregated
transcription-unit occupancy. This module tracks that literal site-level
surface (``tf_bound_promoters``, ``bound_tfs``) as the authoritative
process state; the legacy TU-level ``tf_binding`` port is retained only as
a **derived compatibility view** (column-0/primary-copy projection) since
nothing downstream reads it (verified: ``tf_binding`` has zero consumers
outside this module -- see L2.1 STATUS for the grep evidence).

Karr-parity reductions / approximations (documented for L2 audit):

- **Single-copy downstream fold-change.** Karr's
  ``calcBindingProbabilityFoldChange`` produces a *per-chromosome-copy*
  ``[nTU, 2]`` fold-change matrix (copy 1 and copy 2 can diverge once
  replication has begun and the two copies have different TF occupancy).
  OC's downstream ``tx_rate_fold_change`` port (consumed by
  ``karr_transcription_v3``) is single-valued per TU. Column 0 (the
  always-present original chromosome copy) is used as the authoritative
  representative value; this is a disclosed reduction, not a silent one.
- **No cross-process chromosome-wide occupancy tracking.** Karr's
  ``bindProteinToChromosome`` writes the newly-bound TF into the shared,
  simulation-wide ``monomerBoundSites``/``complexBoundSites`` chromosome
  arrays (so other processes can detect steric occlusion by this TF's
  footprint). This port only tracks its own binding-site occupancy
  (``tf_bound_promoters``); it does not write back to a shared chromosome
  occupancy store. Given each TF's binding sites are process-specific,
  fixed genomic positions dedicated to TF-promoter relationships (distinct
  from other processes' footprints in the current L1b-complete process
  set), this is a bounded, disclosed simplification rather than a silent
  gap.
- **No explicit t=0 pre-binding.** Karr's MATLAB source initializes the
  TF-promoter binding occupancy at t=0 before any tick runs (see
  ``docs/karr_extracts/process/10_TranscriptionalRegulation.md`` lines
  96-99). This implementation seeds ``tf_bound_promoters``/``tf_binding``
  to zero in chassis initial state and performs the first binding sweep
  inside the first ``next_update`` call.
- TFs are partitioned into ``protein`` vs ``complex`` ports via
  ``_load_canonical_complex_wids`` from the MacromolecularComplexation
  fixture. There is **no silent fallback** between stores: a TF declared
  to live in ``complex`` will ``KeyError`` if absent from ``complex.counts``
  even if present in ``protein.counts``. See
  ``tests/unit/test_karr_transcriptional_regulation_strict_zero.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.state.chromosome_store import ChromosomeStore, sparse_triplet_schema
from opencell.util.txreg_mcg_rand import TxRegMcgRandStream

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/TranscriptionalRegulation_flat.mat"
_DEFAULT_COMPLEX_FIXTURE_PATH = "data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat"
_DEFAULT_CHROMOSOME_FIXTURE_PATH = "data/karr_fixtures/per_process/Chromosome_flat.mat"
_FLOAT_TOL = 1e-12




def _resolve_fixture_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    raise FileNotFoundError(f"Fixture not found: {path}")


def _extract_wids(cell_array: np.ndarray) -> list[str]:
    """Convert MATLAB cell-string arrays into plain Python string lists."""
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


def _as_field_matrix(fx: np.ndarray, field: str) -> np.ndarray:
    """Load a MATLAB fixture field and unwrap flat-mat nesting."""
    value = fx[field]
    arr = np.asarray(value)
    if arr.shape == (1, 1):
        arr = np.asarray(arr[0, 0])
    return arr


def _orient_matrix(mat: np.ndarray, n_tf: int, n_tu: int) -> np.ndarray:
    matrix = np.asarray(mat, dtype=np.float64)
    if matrix.shape == (n_tf, n_tu):
        return matrix
    if matrix.shape == (n_tu, n_tf):
        return matrix.T
    raise ValueError(f"Cannot orient matrix of shape {matrix.shape} to ({n_tf}, {n_tu})")


def _orient_other_activities(mat: np.ndarray, n_tu: int, n_tf: int) -> np.ndarray:
    matrix = np.asarray(mat, dtype=np.float64)
    if matrix.shape == (n_tu, n_tf):
        return matrix.T
    if matrix.shape == (n_tf, n_tu):
        return matrix
    raise ValueError(f"Cannot orient otherActivities of shape {matrix.shape} to ({n_tf}, {n_tu})")


def _load_site_table(
    fx: np.ndarray,
    names: set[str],
    *,
    n_tf: int,
    tu_all_wids: list[str],
    tu_keep: np.ndarray,
) -> dict[str, np.ndarray]:
    """Load the literal Karr per-site TF-promoter binding table.

    Mirrors ``TranscriptionalRegulation.m`` fixed constants ``tfIndexs``,
    ``tuIndexs``, ``tfAffinities``, ``tfActivities``, ``tfPositionStrands``
    (see class docstring "Affinity" section + ``initializeConstants``).
    Each of the ``m`` sites is exactly one (transcription factor,
    transcription unit) regulatory relationship with two chromosome-copy
    columns: column 0 is the pre-replication ("copy 1") binding site,
    column 1 is the post-replication ("copy 2") binding site at the same
    genome position on a different chromosome-copy strand. Karr's own
    ``tfPositionStrands`` duplicates columns 1/2 of ``tfIndexs``/
    ``tuIndexs``/``tfAffinities``/``tfActivities`` (verified against the
    fixture: both columns are always identical), so only one copy of each
    is kept here; the two strand values are kept separately since they
    genuinely differ (1-based strands 1 and 3; 0-based 0 and 2).
    """
    required = {"tfIndexs", "tuIndexs", "tfAffinities", "tfActivities", "tfPositionStrands"}
    missing = required - names
    if missing:
        raise KeyError(f"Missing site-level TranscriptionalRegulation fields: {sorted(missing)}")

    tf_idx_2col = np.asarray(_as_field_matrix(fx, "tfIndexs"), dtype=np.int64)
    tu_idx_2col = np.asarray(_as_field_matrix(fx, "tuIndexs"), dtype=np.int64)
    aff_2col = np.asarray(_as_field_matrix(fx, "tfAffinities"), dtype=np.float64)
    act_2col = np.asarray(_as_field_matrix(fx, "tfActivities"), dtype=np.float64)
    pos_strand = np.asarray(_as_field_matrix(fx, "tfPositionStrands"), dtype=np.int64)

    if tf_idx_2col.ndim != 2 or tf_idx_2col.shape[1] != 2:
        raise ValueError(f"tfIndexs must be [sites, 2]; got shape {tf_idx_2col.shape}")
    m = int(tf_idx_2col.shape[0])
    if pos_strand.shape != (2 * m, 2):
        raise ValueError(
            f"tfPositionStrands must be [2*sites, 2]; got shape {pos_strand.shape} for m={m}"
        )
    if not np.array_equal(tf_idx_2col[:, 0], tf_idx_2col[:, 1]):
        raise ValueError("tfIndexs columns are expected to be identical (Karr invariant)")
    if not np.array_equal(tu_idx_2col[:, 0], tu_idx_2col[:, 1]):
        raise ValueError("tuIndexs columns are expected to be identical (Karr invariant)")

    site_tf_index = tf_idx_2col[:, 0] - 1  # 0-based local TF index
    site_tu_index_all = tu_idx_2col[:, 0] - 1  # 0-based index into tu_all_wids
    site_affinity = aff_2col[:, 0].astype(np.float64)
    site_activity = act_2col[:, 0].astype(np.float64)

    if m > 0 and (np.any(site_tf_index < 0) or np.any(site_tf_index >= n_tf)):
        raise ValueError("tfIndexs out of range for enzymeWholeCellModelIDs")

    tu_all_to_kept = {int(orig): new for new, orig in enumerate(tu_keep.tolist())}
    site_tu_index = np.asarray(
        [tu_all_to_kept.get(int(idx), -1) for idx in site_tu_index_all.tolist()], dtype=np.int64
    )
    if m > 0 and np.any(site_tu_index < 0):
        bad_orig = site_tu_index_all[site_tu_index < 0].tolist()
        bad = [tu_all_wids[i] for i in bad_orig]
        raise ValueError(
            "Site-level TU index(es) missing from the regulated TU subset: " f"{bad}"
        )

    site_position = pos_strand[:m, 0] - 1  # 0-based genome position
    site_strand_col0 = pos_strand[:m, 1] - 1  # 0-based strand, chromosome copy 1
    site_strand_col1 = pos_strand[m:, 1] - 1  # 0-based strand, chromosome copy 2
    if m > 0 and not np.array_equal(pos_strand[m:, 0] - 1, site_position):
        raise ValueError(
            "tfPositionStrands copy-2 rows (m:2m) must mirror copy-1 positions (Karr invariant)"
        )

    return {
        "site_tf_index": site_tf_index,
        "site_tu_index": site_tu_index,
        "site_affinity": site_affinity,
        "site_activity": site_activity,
        "site_position": site_position,
        "site_strand_col0": site_strand_col0,
        "site_strand_col1": site_strand_col1,
    }


def _load_fixture(path: str | Path) -> dict[str, Any]:
    resolved = _resolve_fixture_path(path)
    mat = loadmat(str(resolved))
    fx = mat["data"]["fixture"][0, 0]
    names = set(fx.dtype.names or ())

    tf_field = (
        "transcriptionFactorWholeCellModelIDs"
        if "transcriptionFactorWholeCellModelIDs" in names
        else "enzymeWholeCellModelIDs"
    )
    if tf_field not in names:
        raise KeyError("Missing TF IDs field in TranscriptionalRegulation fixture")
    tf_wids = _extract_wids(_as_field_matrix(fx, tf_field))
    n_tf = len(tf_wids)
    substrate_wids = _extract_wids(_as_field_matrix(fx, "substrateWholeCellModelIDs")) if "substrateWholeCellModelIDs" in names else []

    if "transcriptionUnitWholeCellModelIDs" not in names:
        raise KeyError("Missing transcriptionUnitWholeCellModelIDs field in fixture")
    tu_all_wids = _extract_wids(_as_field_matrix(fx, "transcriptionUnitWholeCellModelIDs"))
    n_tu_all = len(tu_all_wids)

    if "tfPromoterAffinityMatrix" in names and "tfTuFoldChangeMatrix" in names:
        affinity_full = _orient_matrix(
            _as_field_matrix(fx, "tfPromoterAffinityMatrix"), n_tf=n_tf, n_tu=n_tu_all
        )
        fold_change_full = _orient_matrix(
            _as_field_matrix(fx, "tfTuFoldChangeMatrix"), n_tf=n_tf, n_tu=n_tu_all
        )
        other_activities_full = np.ones((n_tf, n_tu_all), dtype=np.float64)
        if "otherActivities" in names:
            other_activities_full = _orient_other_activities(
                _as_field_matrix(fx, "otherActivities"), n_tu=n_tu_all, n_tf=n_tf
            )
    else:
        required_sparse = {"tfIndexs", "tuIndexs", "tfAffinities", "tfActivities"}
        if not required_sparse.issubset(names):
            missing = sorted(required_sparse.difference(names))
            raise KeyError(f"Missing sparse TR fields: {missing}")

        tf_idx = np.asarray(_as_field_matrix(fx, "tfIndexs"), dtype=np.int64).reshape(-1)
        tu_idx = np.asarray(_as_field_matrix(fx, "tuIndexs"), dtype=np.int64).reshape(-1)
        tf_aff = np.asarray(_as_field_matrix(fx, "tfAffinities"), dtype=np.float64).reshape(-1)
        tf_act = np.asarray(_as_field_matrix(fx, "tfActivities"), dtype=np.float64).reshape(-1)
        if not (tf_idx.size == tu_idx.size == tf_aff.size == tf_act.size):
            raise ValueError("Sparse TF/TU arrays have mismatched lengths")

        affinity_full = np.zeros((n_tf, n_tu_all), dtype=np.float64)
        fold_change_full = np.ones((n_tf, n_tu_all), dtype=np.float64)
        for t_raw, u_raw, a_raw, c_raw in zip(tf_idx, tu_idx, tf_aff, tf_act, strict=False):
            tf_i = int(t_raw) - 1
            tu_i = int(u_raw) - 1
            if tf_i < 0 or tf_i >= n_tf or tu_i < 0 or tu_i >= n_tu_all:
                continue
            affinity_full[tf_i, tu_i] = max(affinity_full[tf_i, tu_i], float(a_raw))
            fold_change_full[tf_i, tu_i] = float(c_raw)

        other_activities_full = np.ones((n_tf, n_tu_all), dtype=np.float64)
        if "otherActivities" in names:
            other_activities_full = _orient_other_activities(
                _as_field_matrix(fx, "otherActivities"), n_tu=n_tu_all, n_tf=n_tf
            )

    overlap_mask = (affinity_full > 0.0) & (np.abs(other_activities_full - 1.0) > _FLOAT_TOL)
    if np.any(overlap_mask):
        overlap_indices = np.argwhere(overlap_mask)
        preview = ", ".join(
            f"(tf={int(tf_i)}, tu={int(tu_i)})"
            for tf_i, tu_i in overlap_indices[:10]
        )
        if overlap_indices.shape[0] > 10:
            preview = f"{preview}, ..."
        raise ValueError(
            "TranscriptionalRegulation fixture has overlapping binding and otherActivities entries; "
            f"expected disjoint matrices but found {overlap_indices.shape[0]} overlap(s): {preview}"
        )

    # Karr applies otherActivities for TF-presence effects that are distinct
    # from promoter-bound TF fold changes; keep this defensive zeroing as a belt-and-braces mask.
    other_activities_full = np.where(affinity_full > 0.0, 1.0, other_activities_full)

    relationship_mask = (
        (affinity_full > 0.0)
        | (np.abs(fold_change_full - 1.0) > _FLOAT_TOL)
        | (np.abs(other_activities_full - 1.0) > _FLOAT_TOL)
    )
    tu_keep = np.flatnonzero(np.any(relationship_mask, axis=0))
    if tu_keep.size == 0:
        raise ValueError("No regulated transcription units discovered in fixture")

    tu_wids = [tu_all_wids[idx] for idx in tu_keep.tolist()]
    affinity = affinity_full[:, tu_keep]
    fold_change = fold_change_full[:, tu_keep]
    other_activities = other_activities_full[:, tu_keep]

    if "tfPositionStrands" in names:
        site_table = _load_site_table(fx, names, n_tf=n_tf, tu_all_wids=tu_all_wids, tu_keep=tu_keep)
    else:
        # Synthetic/mocked fixtures that only carry the dense
        # tfPromoterAffinityMatrix/tfTuFoldChangeMatrix form (used by unit
        # tests exercising the loader's error paths) do not carry Karr's
        # site-level table at all. No genuine site-level binding is
        # possible without it; leave the site arrays empty rather than
        # fabricating positions.
        site_table = {
            "site_tf_index": np.zeros(0, dtype=np.int64),
            "site_tu_index": np.zeros(0, dtype=np.int64),
            "site_affinity": np.zeros(0, dtype=np.float64),
            "site_activity": np.zeros(0, dtype=np.float64),
            "site_position": np.zeros(0, dtype=np.int64),
            "site_strand_col0": np.zeros(0, dtype=np.int64),
            "site_strand_col1": np.zeros(0, dtype=np.int64),
        }

    return {
        "tf_wids": tf_wids,
        "substrate_wids": substrate_wids,
        "tu_wids": tu_wids,
        "tf_promoter_affinity": affinity,
        "tf_tu_fold_change": fold_change,
        "tf_other_activities": other_activities,
        "n_relationships": int(
            np.count_nonzero(
                (affinity > 0.0)
                | (np.abs(fold_change - 1.0) > _FLOAT_TOL)
                | (np.abs(other_activities - 1.0) > _FLOAT_TOL)
            )
        ),
        **site_table,
    }


def _load_dna_footprint_tables(path: str | Path) -> dict[str, np.ndarray]:
    """Load WholeCellKB monomer/complex DNA-footprint length arrays.

    Same fixture and 0-based (``value - 1``) indexing convention as
    ``KarrDNADamageProcess._load_footprint_fixture``: index i holds the
    footprint length (nt) for the global species index ``value`` stored as
    a ``monomerBoundSites``/``complexBoundSites`` sparse-triplet entry.
    Used to detect third-party steric occlusion of a TF binding site by
    ANY other currently-bound monomer/complex (Karr's
    ``sampleAccessibleRegions`` -> ``isRegionAccessible`` occupant-overlap
    check; see ``_third_party_site_occluded``). Fails closed (empty arrays,
    zero occlusion) if the fixture is unavailable, matching the DNADamage
    process's convention.
    """
    resolved = _resolve_fixture_path(path)
    if not resolved.exists():
        return {
            "monomer_dna_footprints": np.zeros(0, dtype=np.float64),
            "complex_dna_footprints": np.zeros(0, dtype=np.float64),
        }
    mat = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
    fixture = mat["data"].fixture
    monomer_footprints = getattr(fixture, "monomerDNAFootprints", None)
    complex_footprints = getattr(fixture, "complexDNAFootprints", None)
    return {
        "monomer_dna_footprints": (
            np.asarray(monomer_footprints, dtype=np.float64).reshape(-1)
            if monomer_footprints is not None
            else np.zeros(0, dtype=np.float64)
        ),
        "complex_dna_footprints": (
            np.asarray(complex_footprints, dtype=np.float64).reshape(-1)
            if complex_footprints is not None
            else np.zeros(0, dtype=np.float64)
        ),
    }


_DEFAULT_RELEASABLE_PROTEINS_PATH = (
    "data/karr_fixtures/per_process/TranscriptionalRegulation_releasable_proteins.json"
)

# Karr's `Chromosome.m::calcDamagedSites` (the fixed formula every
# `isRegionAccessible`/`isRegionUndamaged` caller in the whole model reads
# from, via the `damagedSites` getter -- never re-parameterized per
# caller): `getDamagedSites(true,true,true,true,false,true,false)`, i.e.
# damagedBases (excluding m6AD-methylation marks, which are tracked for
# other purposes and do not block protein binding) union gapSites,
# abasicSites, damagedSugarPhosphates, intrastrandCrossLinks, strandBreaks,
# hollidayJunctions -- PLUS position-shifted "adjacency" variants of the
# latter three (see `_DAMAGE_FIELD_SHIFTS` below). The one remaining
# disclosed simplification is the `damagedBases` m6AD-index exclusion
# filter (unmodeled -- no m6AD methylation tracking exists in this port,
# so every `damagedBases` entry is conservatively treated as
# damage-blocking; this is one-directional, only ever MORE conservative,
# never less). This does not affect the validated 4000/4000-tick
# bit-identity result for the genuine seed-0 trace (which has zero
# entries in every one of these 7 fields at every compared tick -- see
# `tests/vivarium/test_karr_transcriptional_regulation_ledger_and_damage.py`).
_DAMAGE_FIELDS: tuple[str, ...] = (
    "damagedBases",
    "gapSites",
    "abasicSites",
    "damagedSugarPhosphates",
    "intrastrandCrossLinks",
    "strandBreaks",
    "hollidayJunctions",
)

# 2026-09-08 (Opus re-review, second round): re-derived DIRECTLY from
# `Chromosome.m`'s ACTUAL property getters (lines ~3690-3910) and their
# underlying `shiftCircularSparseMatBase3Prime`/
# `unshiftCircularSparseMatBond5Prime`/`unshiftCircularSparseMatBond3Prime`/
# `shiftCircularSparseMatBond5Prime`/`shiftCircularSparseMatBond3Prime`
# helper functions (lines ~4105-4234) -- the prior version of this module
# had misattributed which shift/unshift function backs each of the three
# shifted fields Karr's fixed `calcDamagedSites` formula ORs in (see
# `_DAMAGE_FIELDS` comment above for the formula itself,
# `getDamagedSites(true,true,true,true,false,true,false)`:
# includeBase5Prime=true/includeBase3Prime=false for intrastrandCrossLinks,
# includeBond5Prime=includeBond3Prime=true for strandBreaks and
# hollidayJunctions). Each computed property is generated by ONE specific
# helper, verified line-by-line against the live `Chromosome.m` source
# (not inferred from naming convention -- MATLAB's "5Prime"/"3Prime"
# suffixes on the shift HELPER name do not always match the suffix on the
# COMPUTED PROPERTY that calls it):
#   - `intrastrandCrossLinks5` = `shiftCircularSparseMatBase3Prime(intrastrandCrossLinks)`
#     -> `shiftPositionsStrandsBase3Prime`: 1-based-odd (0-based-even)
#     strand -> position+lengths; 1-based-even (0-based-odd) -> position-lengths.
#     Shift kind "base3": 0-based-even +1, 0-based-odd -1.
#   - `strandBreaks5` = `unshiftCircularSparseMatBond5Prime(strandBreaks)`
#     -> `unshiftPositionsStrandsBond5Prime`: 1-based-odd (0-based-even)
#     strand -> position+lengths; 1-based-even (0-based-odd) -> unchanged.
#     Shift kind "unbond5": 0-based-even +1, 0-based-odd 0.
#   - `strandBreaks3` = `unshiftCircularSparseMatBond3Prime(strandBreaks)`
#     -> `unshiftPositionsStrandsBond3Prime`: 1-based-even (0-based-odd)
#     strand -> position+lengths; 1-based-odd (0-based-even) -> unchanged.
#     Shift kind "unbond3": 0-based-odd +1, 0-based-even 0.
#   - `hollidayJunctions5` = `shiftCircularSparseMatBond3Prime(hollidayJunctions)`
#     -> `shiftPositionsStrandsBond3Prime`: 1-based-even (0-based-odd)
#     strand -> position-lengths; 1-based-odd (0-based-even) -> unchanged.
#     Shift kind "bond3": 0-based-odd -1, 0-based-even 0 (kept, was
#     already correct).
#   - `hollidayJunctions3` = `shiftCircularSparseMatBond5Prime(hollidayJunctions)`
#     -> `shiftPositionsStrandsBond5Prime`: 1-based-odd (0-based-even)
#     strand -> position-lengths; 1-based-even (0-based-odd) -> unchanged.
#     Shift kind "bond5": 0-based-even -1, 0-based-odd 0 (kept, was
#     already correct).
# `calcDamagedSites` includes: `intrastrandCrossLinks` + its `5` variant
# (base3-shifted, NOT the `3` variant -- `includeBase3Prime=false`);
# `strandBreaks` + BOTH its `5` (unbond5) and `3` (unbond3) variants;
# `hollidayJunctions` + BOTH its `5` (bond3) and `3` (bond5) variants
# (`includeBond5Prime=includeBond3Prime=true`). `damagedBases`/
# `gapSites`/`abasicSites`/`damagedSugarPhosphates` carry no shift terms
# in the fixed formula. Each shifted virtual position is checked on the
# ENTRY's OWN (pre-shift) strand -- shifting changes only the position
# coordinate, not which physical strand (and therefore which
# chromosome-copy strand-pair) the entry belongs to.
_DAMAGE_FIELD_SHIFTS: dict[str, tuple[str, ...]] = {
    "damagedBases": (),
    "gapSites": (),
    "abasicSites": (),
    "damagedSugarPhosphates": (),
    "intrastrandCrossLinks": ("base3",),
    "strandBreaks": ("unbond5", "unbond3"),
    "hollidayJunctions": ("bond5", "bond3"),
}


def _shifted_damage_position(position: int, strand: int, shift_kind: str) -> int:
    """Re-derived, 0-based-strand form of ``Chromosome.m``'s
    ``shiftPositionsStrandsBase3Prime``/``unshiftPositionsStrandsBond5Prime``/
    ``unshiftPositionsStrandsBond3Prime``/``shiftPositionsStrandsBond5Prime``/
    ``shiftPositionsStrandsBond3Prime`` (lines ~4183-4234) -- see the
    ``_DAMAGE_FIELD_SHIFTS`` module comment for exactly which computed
    property each ``shift_kind`` reproduces and the per-kind,
    per-strand-parity sign convention verified line-by-line against that
    source."""
    even_strand = int(strand) % 2 == 0
    if shift_kind == "base3":
        return position + 1 if even_strand else position - 1
    if shift_kind == "unbond5":
        return position + 1 if even_strand else position
    if shift_kind == "unbond3":
        return position if even_strand else position + 1
    if shift_kind == "bond5":
        return position - 1 if even_strand else position
    if shift_kind == "bond3":
        return position if even_strand else position - 1
    raise ValueError(f"unknown shift_kind: {shift_kind!r}")


def _load_releasable_proteins(
    path: str | Path, n_tf: int
) -> tuple[list[set[int]], list[set[int]], list[float]]:
    """Load the per-TF "releasable protein" exemption sets AND each TF's own
    DNA-binding footprint, extracted live from ``Chromosome.m::
    getReleasableProteins``/``getDNAFootprint`` (see
    ``scripts/matlab/extract_txreg_releasable_proteins.m``).

    Karr's real ``isRegionAccessible`` occupant-overlap check
    (``Chromosome.m`` line ~651) does not treat every nearby bound
    monomer/complex as a blocker: ``getReleasableProteins(bindingMonomers,
    bindingComplexs)`` (line ~1575) computes, from static reaction-catalysis
    relationships, the set of complex/monomer GLOBAL indices the query
    protein (here, a specific TF) is allowed to displace -- those are
    excluded from the occlusion check entirely. This was previously
    unmodeled in ``_third_party_site_occluded``, causing a false-positive
    occlusion (empirically found: TF3/MG_236_MONOMER's site2 candidate at
    tick 11 of the genuine 4000-tick trace is 99nt from a 630nt-footprint
    bound complex (global index 82) -- global index 82 is on TF3's
    releasable-complex list, so real MATLAB reports the site accessible).

    Also loads each TF's own ``getDNAFootprint`` result (``own_footprint``):
    the QUERY protein's footprint is what actually sizes the occlusion
    interval-overlap test (see ``_third_party_site_occluded``'s corrected
    docstring) -- NOT the occupant's own footprint, which the pre-2026-09-05
    version of this method incorrectly used.

    Returns ``(releasable_monomer_global_idxs_by_tf,
    releasable_complex_global_idxs_by_tf, own_footprint_by_tf)``. The first
    two are length-``n_tf`` lists of sets of 1-based global indices
    (matching the same 1-based global-index convention already used by
    ``monomer_dna_footprints``/``complex_dna_footprints``); the third is a
    length-``n_tf`` list of footprint lengths (nt).

    **Fails closed** (raises, never silently defaults) on a missing
    fixture file, a missing/malformed ``per_tf`` array, or a TF local
    index in ``[1, n_tf]`` with no corresponding entry -- a silent empty
    exemption set / zero ``own_footprint`` fallback is dangerous, not
    merely conservative: ``_third_party_site_occluded`` treats a zero
    ``own_footprint`` as "this TF's own footprint can never occlude
    anything," which would silently DISABLE the tick-221/tick-684
    occlusion fixes (own-footprint interval-overlap, cross-strand-pair
    occlusion) for that TF with no visible test failure -- exactly the
    kind of safety-critical silent fallback Opus review point 6 flags.
    This fixture is committed, load-bearing evidence data (extracted once
    via ``scripts/matlab/extract_txreg_releasable_proteins.m``), not an
    optional/degraded-mode input; its absence or corruption must be a
    loud, immediate failure.
    """
    resolved = _resolve_fixture_path(path)
    if not resolved.exists():
        raise FileNotFoundError(
            f"TranscriptionalRegulation releasable-proteins fixture not found: {resolved} -- "
            "this fixture is load-bearing evidence data (own_footprint/releasable-exemption "
            "sets for the tick-221/tick-684 occlusion fixes), not an optional input; refusing "
            "to silently fall back to empty exemption sets/zero footprints"
        )
    with resolved.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    per_tf = payload.get("per_tf")
    if not isinstance(per_tf, list) or not per_tf:
        raise ValueError(
            f"TranscriptionalRegulation releasable-proteins fixture {resolved} is missing "
            f"a non-empty 'per_tf' array (got {per_tf!r}) -- refusing to silently fall back "
            "to empty exemption sets/zero footprints"
        )
    monomer_sets: list[set[int]] = [set() for _ in range(n_tf)]
    complex_sets: list[set[int]] = [set() for _ in range(n_tf)]
    own_footprints: list[float] = [0.0 for _ in range(n_tf)]
    seen_local_idxs: set[int] = set()
    for entry in per_tf:
        local_idx = int(entry.get("local_idx", 0)) - 1  # 1-based -> 0-based
        if not (0 <= local_idx < n_tf):
            raise ValueError(
                f"TranscriptionalRegulation releasable-proteins fixture {resolved} has an "
                f"entry with out-of-range local_idx={entry.get('local_idx')!r} "
                f"(expected 1..{n_tf}): {entry!r}"
            )
        if "own_footprint" not in entry:
            raise ValueError(
                f"TranscriptionalRegulation releasable-proteins fixture {resolved} entry "
                f"for local_idx={entry.get('local_idx')!r} is missing the required "
                "'own_footprint' field -- refusing to silently default it to 0.0 (which "
                "would disable this TF's occlusion checks entirely)"
            )
        monomer_idxs = entry.get("releasable_monomer_global_idxs", [])
        complex_idxs = entry.get("releasable_complex_global_idxs", [])
        if isinstance(monomer_idxs, (int, float)):
            monomer_idxs = [monomer_idxs]
        if isinstance(complex_idxs, (int, float)):
            complex_idxs = [complex_idxs]
        monomer_sets[local_idx] = {int(v) for v in monomer_idxs}
        complex_sets[local_idx] = {int(v) for v in complex_idxs}
        own_footprints[local_idx] = float(entry.get("own_footprint", 0.0))
        seen_local_idxs.add(local_idx)
    missing_idxs = sorted(set(range(n_tf)) - seen_local_idxs)
    if missing_idxs:
        raise ValueError(
            f"TranscriptionalRegulation releasable-proteins fixture {resolved} has no "
            f"entry for local TF index/indices (0-based) {missing_idxs} out of {n_tf} "
            "expected TFs -- refusing to silently default those TFs to empty exemption "
            "sets/zero footprint"
        )
    return monomer_sets, complex_sets, own_footprints


def _load_canonical_complex_wids(path: str | Path) -> set[str]:
    resolved = _resolve_fixture_path(path)
    mat = loadmat(str(resolved))
    if "data" not in mat:
        raise KeyError(f"Missing 'data' root in complex fixture: {resolved}")
    fx = mat["data"]["fixture"][0, 0]
    names = set(fx.dtype.names or ())
    if "complexWholeCellModelIDs" not in names:
        raise KeyError(
            "Missing complexWholeCellModelIDs in complex fixture used by "
            "karr_transcriptional_regulation"
        )
    complex_wids = set(_extract_wids(_as_field_matrix(fx, "complexWholeCellModelIDs")))
    if not complex_wids:
        raise ValueError(
            "No complex WIDs found in complex fixture used by karr_transcriptional_regulation"
        )
    return complex_wids


class KarrTranscriptionalRegulationProcess(Process):
    """TF-promoter binding and transcription-rate fold-change modulation."""

    name = "karr_transcriptional_regulation"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "complex_wids": None,
        "complex_fixture_path": _DEFAULT_COMPLEX_FIXTURE_PATH,
        "chromosome_fixture_path": _DEFAULT_CHROMOSOME_FIXTURE_PATH,
        "releasable_proteins_fixture_path": _DEFAULT_RELEASABLE_PROTEINS_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        fixture = _load_fixture(self.parameters["fixture_path"])
        self.tf_wids: list[str] = fixture["tf_wids"]
        self.enzyme_wids: list[str] = list(self.tf_wids)
        self.substrate_wids: list[str] = fixture["substrate_wids"]
        self.tu_wids: list[str] = fixture["tu_wids"]
        self.tf_promoter_affinity: np.ndarray = fixture["tf_promoter_affinity"]
        self.tf_tu_fold_change: np.ndarray = fixture["tf_tu_fold_change"]
        self.tf_other_activities: np.ndarray = fixture["tf_other_activities"]
        self.n_relationships: int = fixture["n_relationships"]

        self._n_tf = len(self.tf_wids)
        self._n_tu = len(self.tu_wids)

        # Site-level (Karr-native) TF-promoter binding table -- see module
        # docstring and `_load_site_table`. Column 0 = pre-replication
        # chromosome copy; column 1 = post-replication second copy.
        self.site_tf_index: np.ndarray = fixture["site_tf_index"]
        self.site_tu_index: np.ndarray = fixture["site_tu_index"]
        self.site_affinity: np.ndarray = fixture["site_affinity"]
        self.site_activity: np.ndarray = fixture["site_activity"]
        self.site_position: np.ndarray = fixture["site_position"]
        self.site_strand_col0: np.ndarray = fixture["site_strand_col0"]
        self.site_strand_col1: np.ndarray = fixture["site_strand_col1"]
        self._n_sites = int(self.site_tf_index.shape[0])

        # Flat WID surface for the (site, chromosome-copy) occupancy port.
        # Order is [col0 site0..siteN, col1 site0..siteN] to match Karr's
        # own `tfBoundPromoters = reshape(isDnaBound(...), [], 2)`
        # column-major layout -- verified positionally against the genuine
        # event trace (`TranscriptionalRegulation_4000ticks.mat`).
        self.tf_bound_promoters_wids: list[str] = [
            f"site{s:03d}_copy0" for s in range(self._n_sites)
        ] + [f"site{s:03d}_copy1" for s in range(self._n_sites)]

        self.chromosome_shape: tuple[int, int] = (
            int(ChromosomeStore.DEFAULT_SEQUENCE_LEN),
            int(ChromosomeStore.DEFAULT_N_COMPARTMENTS),
        )

        # Third-party steric-occlusion footprint tables (Karr
        # `sampleAccessibleRegions` -> `isRegionAccessible` occupant-overlap
        # check). See `_third_party_site_occluded`.
        footprint_tables = _load_dna_footprint_tables(
            self.parameters.get("chromosome_fixture_path", _DEFAULT_CHROMOSOME_FIXTURE_PATH)
        )
        self.monomer_dna_footprints: np.ndarray = footprint_tables["monomer_dna_footprints"]
        self.complex_dna_footprints: np.ndarray = footprint_tables["complex_dna_footprints"]

        # Per-TF "releasable protein" exemption sets (Karr
        # `Chromosome.m::getReleasableProteins`) and each TF's own DNA
        # footprint (`getDNAFootprint`) -- see `_load_releasable_proteins`
        # / `_third_party_site_occluded`.
        (
            self._releasable_monomer_global_idxs_by_tf,
            self._releasable_complex_global_idxs_by_tf,
            self._own_footprint_by_tf,
        ) = _load_releasable_proteins(
            self.parameters.get(
                "releasable_proteins_fixture_path", _DEFAULT_RELEASABLE_PROTEINS_PATH
            ),
            self._n_tf,
        )

        # Karr-persistent: this process's OWN `this.randStream`
        # (`edu.stanford.covert.cell.sim.Process.m:283`,
        # `this.randStream = edu.stanford.covert.util.RandStream('mcg16807')`).
        # TranscriptionalRegulation.m itself never calls
        # `this.randStream.*` directly -- every stochastic draw in
        # `bindTranscriptionFactors` goes through
        # `this.bindProteinToChromosome(...)` ->
        # `Chromosome.m::sampleAccessibleRegions`, which draws from `this.
        # randStream` where `this` is the CHROMOSOME STATE object (a
        # SEPARATE stream from this process's own -- confirmed live,
        # `isequal(chromosome.randStream, txreg.randStream) == false`; see
        # `scripts/matlab/probe_txreg_real_sample_accessible_regions.m` and
        # STATUS_L21_TXREG_ACTIVE_FIX.md's "shared-chromosome-RNG" finding).
        # `_rng` is retained, seeded identically, and left completely
        # unused by any current draw site -- exactly mirroring Karr's own
        # per-process `this.randStream`, which this process also
        # constructs/seeds but never reads -- so that a future fix
        # discovering a genuine process-owned draw has a ready, already-
        # correctly-seeded, already-isolated stream to attach to, without
        # disturbing `_chromosome_rng`'s replay wiring below.
        self._rng = TxRegMcgRandStream(int(self.parameters["rng_seed"]))

        # `_chromosome_rng` stands in for `this.chromosome.randStream`: the
        # stream `_sample_accessible_sites_batched` actually draws from.
        # In production this is a freshly-seeded, process-local
        # `TxRegMcgRandStream` (structurally faithful -- every formula it
        # implements is Karr's literal formula -- but NOT bit-identical to
        # Karr's real interleaved draw sequence, since that stream is
        # shared and advanced by every other Karr process that binds
        # anything to the chromosome each tick). An L2.1 replay harness
        # that has a genuine per-tick chromosome-randStream-state ledger
        # (`scripts/matlab/reconstruct_chromosome_draw_ledger.m`) may
        # swap this attribute, per tick, for a
        # `TxRegChromosomeLedgerRandStream` that replays Karr's own
        # recorded raw draws exactly -- see
        # `tests/vivarium/test_karr_transcriptional_regulation_l2_replay.py`.
        #
        # **Persistence contract (declared 2026-09-05, Opus review point
        # 6):** in PRODUCTION, this attribute is set exactly once here (in
        # `__init__`) and lives for the process instance's ENTIRE lifetime
        # -- it is a single, continuously-advancing stream across every
        # tick of a run, never replaced or reset. In an L2.1 REPLAY
        # harness with a chromosome-rand-stream ledger available, this
        # attribute MUST instead be REPLACED with a brand-new, freshly-
        # constructed `TxRegChromosomeLedgerRandStream` instance before
        # EVERY SINGLE `next_update` call, never reused/carried over from
        # the previous tick and never advanced across ticks by the harness
        # itself -- per `decisions/dec-006-shared-chromosome-randstream-
        # input-oracle.md`, Karr's real per-tick input position must be
        # restored exactly each tick (an unknown, tick-varying number of
        # OTHER processes' draws happen on the real shared stream between
        # any two ticks, so carrying a Python-side stream across ticks
        # cannot ever match). This attribute is NEVER permitted to be
        # `None` while an active tick needs a draw -- see the explicit
        # guard in `_sample_accessible_sites_batched`.
        self._chromosome_rng = TxRegMcgRandStream(int(self.parameters["rng_seed"]))



        configured_complex_wids = self.parameters.get("complex_wids")
        if configured_complex_wids is None:
            complex_wids = _load_canonical_complex_wids(self.parameters["complex_fixture_path"])
        else:
            complex_wids = {str(wid) for wid in configured_complex_wids}
        self._tf_wid_source: dict[str, str] = {
            tf_wid: ("complex" if tf_wid in complex_wids else "protein") for tf_wid in self.tf_wids
        }
        self._tf_is_complex = np.asarray(
            [self._tf_wid_source[tf_wid] == "complex" for tf_wid in self.tf_wids],
            dtype=bool,
        )
        self._protein_tf_wids = [
            tf_wid for tf_wid in self.tf_wids if self._tf_wid_source[tf_wid] == "protein"
        ]
        self._complex_tf_wids = [
            tf_wid for tf_wid in self.tf_wids if self._tf_wid_source[tf_wid] == "complex"
        ]

    def ports_schema(self) -> dict[str, Any]:
        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.substrate_wids
            },
            "enzymes": {
                tf_wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for tf_wid in self.tf_wids
            },
            "boundEnzymes": {
                tf_wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for tf_wid in self.tf_wids
            },
            "protein": {
                "counts": {
                    tf_wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for tf_wid in self._protein_tf_wids
                }
            },
            "complex": {
                "counts": {
                    tf_wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for tf_wid in self._complex_tf_wids
                }
            },
            # Read-only input: chromosome-wide polymerization status and
            # bound-protein occupancy (monomer/complex), used to gate which
            # chromosome-copy columns of each site are currently accessible
            # (Karr `isRegionPolymerized`) and to detect third-party
            # steric occlusion by a currently-bound OTHER protein whose
            # footprint overlaps a candidate site (Karr
            # `sampleAccessibleRegions` -> `isRegionAccessible`). This
            # process never writes to the shared chromosome store (see
            # module docstring "No cross-process chromosome-wide occupancy
            # tracking").
            "chromosome": {
                "polymerizedRegions": sparse_triplet_schema(self.chromosome_shape, emit=False),
                "monomerBoundSites": sparse_triplet_schema(self.chromosome_shape, emit=False),
                "complexBoundSites": sparse_triplet_schema(self.chromosome_shape, emit=False),
            },
            # Authoritative site-level occupancy surface (Karr
            # `tfBoundPromoters`): one boolean-valued entry per (site,
            # chromosome-copy) pair. Latched via `accumulate` -- a site is
            # bound at most once (Karr binding is stable/never released by
            # this process), so a +1 delta is emitted exactly once per
            # newly-bound (site, copy) pair.
            "tf_bound_promoters": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                for wid in self.tf_bound_promoters_wids
            },
            # Authoritative per-TF bound-copy count (Karr `boundTFs`): a
            # dependent/getter property in Karr (histc over column-0
            # occupancy only), recomputed fresh from `tf_bound_promoters`
            # each tick rather than accumulated.
            "bound_tfs": {
                tf_wid: {"_default": 0.0, "_updater": "set", "_emit": True}
                for tf_wid in self.tf_wids
            },
            # Legacy TU-level compatibility view -- DERIVED from
            # `tf_bound_promoters` each tick (column-0/primary-copy
            # projection), not authoritative state. No downstream consumer
            # reads this port (verified via repo-wide grep); kept only for
            # observability / backward compatibility.
            "tf_binding": {
                tf_wid: {
                    tu_wid: {"_default": 0.0, "_updater": "set", "_emit": True}
                    for tu_wid in self.tu_wids
                }
                for tf_wid in self.tf_wids
            },
            "tx_rate_fold_change": {
                tu_wid: {"_default": 1.0, "_updater": "set", "_emit": True}
                for tu_wid in self.tu_wids
            },
        }


    def _read_tf_counts(self, states: dict[str, Any]) -> np.ndarray:
        protein_counts = states.get("protein", {}).get("counts", {})
        if not isinstance(protein_counts, dict):
            protein_counts = {}
        complex_counts = states.get("complex", {}).get("counts", {})
        if not isinstance(complex_counts, dict):
            complex_counts = {}

        tf_counts = np.zeros(self._n_tf, dtype=np.float64)
        for tf_i, tf_wid in enumerate(self.tf_wids):
            source = self._tf_wid_source[tf_wid]
            source_counts = complex_counts if source == "complex" else protein_counts
            if tf_wid not in source_counts:
                raise KeyError(
                    f"Missing TF WID '{tf_wid}' in expected {source}.counts store "
                    "for karr_transcriptional_regulation"
                )
            tf_counts[tf_i] = max(0.0, float(source_counts[tf_wid]))
        return tf_counts

    def _read_site_occupancy(self, states: dict[str, Any]) -> np.ndarray:
        """Read the current (site, chromosome-copy) occupancy as an
        ``(n_sites, 2)`` boolean array from the ``tf_bound_promoters`` port.
        """
        occ = np.zeros((self._n_sites, 2), dtype=bool)
        store = states.get("tf_bound_promoters", {})
        if not isinstance(store, dict):
            store = {}
        for s in range(self._n_sites):
            if float(store.get(self.tf_bound_promoters_wids[s], 0.0)) > 0.5:
                occ[s, 0] = True
            if float(store.get(self.tf_bound_promoters_wids[self._n_sites + s], 0.0)) > 0.5:
                occ[s, 1] = True
        return occ

    def _resolve_chromosome_store(self, chrom_state: dict[str, Any]) -> ChromosomeStore:
        return ChromosomeStore.from_state_mapping(chrom_state, shape=self.chromosome_shape)

    def _polymerized_intervals_by_strand(
        self, chromosome_store: ChromosomeStore
    ) -> dict[int, list[tuple[int, int]]]:
        """Literal Karr ``Chromosome.m::isRegionPolymerized`` input, reduced
        to per-strand run-length intervals. Mirrors
        ``KarrDNADamageProcess._polymerized_intervals_by_strand``.
        """
        try:
            triplet = chromosome_store.get_field("polymerizedRegions")
        except KeyError:
            triplet = None
        by_strand: dict[int, list[tuple[int, int]]] = {}
        total = 0
        if triplet is not None:
            for position, strand, value in zip(
                triplet.positions.tolist(), triplet.strands.tolist(), triplet.values.tolist(), strict=False
            ):
                length = int(value)
                if length <= 0:
                    continue
                total += length
                by_strand.setdefault(int(strand), []).append((int(position), length))
        if total <= 0:
            # No polymerizedRegions data at all: an unreplicated chromosome
            # has strand 0 (Watson of copy 1) and strand 1 (Crick of copy
            # 1) fully polymerized; strands 2/3 (copy 2) do not exist yet.
            # This process only ever queries strands 0 and 2 (the two
            # chromosome-copy columns a TF binding site can occupy), so the
            # net effect is: copy-1 sites always accessible-by-polymerization,
            # copy-2 sites never accessible until real replication data
            # arrives.
            length = self.chromosome_shape[0]
            return {0: [(0, length)], 1: [(0, length)]}
        return by_strand

    def _is_polymerized(
        self,
        intervals_by_strand: dict[int, list[tuple[int, int]]],
        position: int,
        strand: int,
    ) -> bool:
        intervals = intervals_by_strand.get(int(strand))
        if not intervals:
            return False
        length = self.chromosome_shape[0]
        return any((int(position) - start) % length < region_len for start, region_len in intervals)

    def _third_party_site_occluded(
        self,
        chromosome_store: ChromosomeStore,
        position: int,
        strand: int,
        *,
        tf_i: int,
    ) -> bool:
        """Literal Karr ``sampleAccessibleRegions`` -> ``isRegionAccessible``
        -> ``isRegionProteinFree`` occupant-overlap check: is ``position``
        (on ``strand``) currently covered by the DNA footprint of any OTHER
        bound monomer/complex that ``tf_i`` is not itself allowed to
        displace?

        **Correction (2026-09-05, found via the tick-221 chromosome-RNG-
        ledger investigation):** the overlap test is a STANDARD INTERVAL
        OVERLAP between two START-ANCHORED spans, each sized by its OWN
        entity's footprint -- NOT a symmetric window centered on the
        occupant's position sized by the OCCUPANT's footprint (the
        previous, empirically-refuted approximation this method used).
        Real ``Chromosome.m``:

        - ``isRegionAccessible`` computes the QUERY's own footprint via
          ``getDNAFootprint(bindingMonomers, bindingComplexs)`` --
          ``bindingMonomers``/``bindingComplexs`` identify the TF ITSELF
          (the protein trying to bind), never the occupant -- then (since
          ``TranscriptionalRegulation`` always calls
          ``bindProteinToChromosome`` with
          ``isPositionsStrandFootprintCentroid=false`` and a positive
          ``lengths``) leaves the query position UNSHIFTED and sets
          ``queryLengths = lengths + (footprint - 1) = footprint`` -- i.e.
          the query span is ``[position, position + own_footprint - 1]``
          (start-anchored, extending toward increasing coordinates).
        - ``isRegionProteinFree`` computes each occupant's span directly
          from its STORED ``monomerBoundSites``/``complexBoundSites``
          position (already the bind-time start coordinate, per
          ``setSiteProteinBound``'s own ``bindPositionsStrands`` centroid
          shift at BIND time -- never re-shifted on read) as
          ``[entry_pos, entry_pos + occupant_footprint - 1]``, and reports
          occlusion iff these two spans overlap.

        Empirically found live (tick 221 of the genuine 4000-tick event
        trace, ``scripts/matlab/probe_txreg_tick221_site4_accessibility.m``):
        TF4 (``MG_428_DIMER``, own footprint 28nt) at ``site4`` is reported
        NOT accessible (``isRegionAccessible`` -> false) despite a
        75nt-footprint complex sitting 70nt away -- a distance the
        previous symmetric-occupant-footprint model (using the OCCUPANT's
        75nt footprint, radius ~37nt) judged clear, but the correct
        query-footprint-anchored interval-overlap test (query span
        ``[position, position+27]``, occupant span
        ``[entry_pos, entry_pos+74]``) correctly finds overlapping.

        Karr's real ``isRegionAccessible`` first computes
        ``getReleasableProteins(bindingMonomers, bindingComplexs)`` (see
        ``Chromosome.m`` line ~1575) and EXCLUDES any bound monomer/complex
        on that list from counting as a blocker at all -- a static,
        reaction-catalysis-derived per-TF exemption set, not a chromosome-
        state check. Empirically confirmed live (tick 11 of the genuine
        4000-tick event trace): TF3 (``MG_236_MONOMER``)'s ``site2``
        candidate sits 99nt from a 630nt-footprint bound complex (global
        index 82); real MATLAB's ``isRegionAccessible`` still reports it
        ACCESSIBLE because global complex index 82 is on TF3's
        ``releasableComplexIndexs`` list (extracted once, statically, via
        ``scripts/matlab/extract_txreg_releasable_proteins.m`` -- see
        ``_load_releasable_proteins``). Without this exemption, this method
        raised a false-positive occlusion that silently desynchronized the
        RNG stream from Karr's real one starting at this exact tick.

        **Correction #2 (2026-09-05, tick 684):** a dsDNA-bound occupant
        occludes BOTH strands of its own chromosome copy, not just the
        exact strand its ``monomerBoundSites``/``complexBoundSites`` entry
        happens to be recorded on. Real ``isRegionProteinFree`` (see
        ``Chromosome.m`` ~line 1179) mirrors every dsDNA-binding-stranded
        occupant entry onto BOTH strands of its chromosome-copy pair
        before the interval-overlap test
        (``dsTfs = monomerDNAFootprintBindingStrandedness(vals) ==
        dnaStrandedness_dsDNA; subs = [subs(~dsTfs,:); subs(dsTfs,1)
        2*ceil(subs(dsTfs,2)/2)-1; subs(dsTfs,1) 2*ceil(subs(dsTfs,2)/2)]``).
        Every TF this process binds is itself dsDNA-stranded
        (``getDNAFootprint``'s ``bindingStrandedness`` result for both
        TF3/MG_236_MONOMER and TF4/MG_428_DIMER is
        ``dnaStrandedness_dsDNA = 2``, ``Chromosome.m:136``) -- the
        dominant/near-universal case for structural chromosome-binding
        proteins in this model -- so this method now compares STRAND
        PAIRS (``strand // 2``: 0/1 -> chromosome copy 1, 2/3 -> copy 2)
        rather than exact strand equality. Empirically confirmed live
        (``scripts/matlab/probe_txreg_real_tick_candidates.m`` tick 684):
        TF3's ``site13`` (strand 0, chromosome copy 1) candidate is
        occluded by complex global index 201 recorded on strand 1 (the
        OTHER strand of copy 1) -- real ``isRegionAccessible`` reports it
        inaccessible; the previous exact-strand-only check missed this
        cross-strand occlusion entirely.
        """
        length = self.chromosome_shape[0]
        releasable_monomers = self._releasable_monomer_global_idxs_by_tf[tf_i]
        releasable_complexes = self._releasable_complex_global_idxs_by_tf[tf_i]
        own_footprint = int(self._own_footprint_by_tf[tf_i])
        if own_footprint <= 0:
            return False
        strand_pair = int(strand) // 2
        for field_name, footprint_table, releasable_idxs in (
            ("monomerBoundSites", self.monomer_dna_footprints, releasable_monomers),
            ("complexBoundSites", self.complex_dna_footprints, releasable_complexes),
        ):
            if footprint_table.size == 0:
                continue
            try:
                triplet = chromosome_store.get_field(field_name)
            except KeyError:
                continue
            n = int(footprint_table.size)
            for entry_pos, entry_strand, value in zip(
                triplet.positions.tolist(), triplet.strands.tolist(), triplet.values.tolist(), strict=False
            ):
                if int(entry_strand) // 2 != strand_pair:
                    continue
                global_idx = int(value)
                if global_idx in releasable_idxs:
                    continue
                idx = global_idx - 1
                if not (0 <= idx < n):
                    continue
                occupant_footprint = int(footprint_table[idx])
                if occupant_footprint <= 0:
                    continue
                # Circular interval overlap between the query span
                # [position, position + own_footprint - 1] and the
                # occupant span [entry_pos, entry_pos + occupant_footprint
                # - 1], both start-anchored (see docstring above).
                delta = (int(entry_pos) - int(position)) % length
                if delta <= own_footprint - 1 or delta + occupant_footprint - 1 >= length:
                    return True
        return False

    def _site_damaged(
        self,
        chromosome_store: ChromosomeStore,
        position: int,
        strand: int,
        *,
        tf_i: int,
    ) -> bool:
        """Real ``isRegionAccessible`` ANDs its protein-occupancy check
        (``_third_party_site_occluded``) with ``isRegionUndamaged`` --
        Karr's real ``TranscriptionalRegulation.m::bindTranscriptionFactors``
        calls ``bindProteinToChromosome`` with ``ignoreDamageFilter=[]``
        (default: ignore NO damage types), so a candidate site covered by
        ANY entry in Karr's fixed ``damagedSites`` union (see
        ``_DAMAGE_FIELDS``/``_DAMAGE_FIELD_SHIFTS`` module constants for
        the exact composition, including the position-shifted adjacency
        variants) is NOT accessible, exactly like a third-party-occupied
        site. Uses the SAME dsDNA strand-pair mirroring as
        ``_third_party_site_occluded`` (every TF this process binds is
        itself dsDNA-stranded, so real ``isRegionUndamaged`` is called
        with ``isEitherStrandDamaged=true``, checking damage on EITHER
        strand of the query's own chromosome copy, not just the exact
        query strand) and the query's own start-anchored span
        (``[position, position + own_footprint - 1]``).
        """
        length = self.chromosome_shape[0]
        own_footprint = int(self._own_footprint_by_tf[tf_i])
        if own_footprint <= 0:
            return False
        strand_pair = int(strand) // 2
        for field_name in _DAMAGE_FIELDS:
            try:
                triplet = chromosome_store.get_field(field_name)
            except KeyError:
                continue
            if triplet.positions.size == 0:
                continue
            shift_kinds = _DAMAGE_FIELD_SHIFTS[field_name]
            for entry_pos, entry_strand in zip(
                triplet.positions.tolist(), triplet.strands.tolist(), strict=False
            ):
                if int(entry_strand) // 2 != strand_pair:
                    continue
                # The raw entry itself, plus every disclosed
                # position-shifted adjacency variant for this field (see
                # _DAMAGE_FIELD_SHIFTS) -- all checked on the entry's OWN
                # (pre-shift) strand, since shifting moves only the
                # position, never which physical strand the damage
                # belongs to.
                candidate_positions = [int(entry_pos)] + [
                    _shifted_damage_position(int(entry_pos), int(entry_strand), kind)
                    for kind in shift_kinds
                ]
                for candidate_pos in candidate_positions:
                    # Circular membership of the (effectively single-point)
                    # damage entry/adjacency variant within the query's own
                    # start-anchored span.
                    delta = (candidate_pos - int(position)) % length
                    if delta <= own_footprint - 1:
                        return True
        return False

    def _footprint_double_stranded_polymerized(
        self,
        intervals_by_strand: dict[int, list[tuple[int, int]]],
        position: int,
        strand: int,
        *,
        tf_i: int,
    ) -> bool:
        """Real ``isRegionAccessible`` computes its ``polymerized`` term via
        ``isRegionDoubleStranded(queryPositionsStrands, queryLengths, ...)``
        (``Chromosome.m`` ~line 720), where ``queryLengths`` is the QUERY's
        own FULL FOOTPRINT length (``footprint``, not ``1``) -- a
        materially richer check than ``TranscriptionalRegulation.m::
        bindTranscriptionFactors``'s own coarse candidate-set filter
        (``chromosome.isRegionPolymerized(this.tfPositionStrands, 1,
        false)``, a SINGLE-POINT, SINGLE-STRAND check, already ported
        verbatim as this class's coarse ``_is_polymerized``/``accessible``
        mask). ``isRegionDoubleStranded`` requires the ENTIRE query span to
        be polymerized on BOTH sub-strands of the chromosome copy (real
        double-strandedness, not merely single-strand polymerization) --
        internally, via ``isRegionPolymerized(..., checkRegionStrandedness
        = dnaStrandedness_dsDNA)``, which reads ``this.doubleStrandedRegions``
        (the class-level intersection of the copy's two sub-strands'
        polymerized coverage), with a documented fast path for "only
        one/all chromosome copies, each fully polymerized end-to-end"
        (``Chromosome.m`` ~lines 816-844) that is definitionally correct
        (trivially double-stranded) once a copy has ever been fully
        polymerized. This method implements the general, non-fast-path
        case directly from the same ``polymerizedRegions`` run-length
        interval data ``_is_polymerized`` already reads (no separate
        ``doubleStrandedRegions`` field is stored in this port's
        chromosome fixtures/traces): the query span is double-stranded iff
        EVERY point in ``[position, position + own_footprint - 1]`` is
        covered by a polymerized run on BOTH sub-strands
        (``2*strand_pair``, ``2*strand_pair + 1``) of the query's
        chromosome copy -- the literal physical definition of
        "double-stranded", computed correctly regardless of whether the
        genome happens to be in the pre-replication (single-copy,
        fully-polymerized) fast-path regime or mid-replication with a
        partial fork.
        """
        own_footprint = int(self._own_footprint_by_tf[tf_i])
        if own_footprint <= 0:
            return False
        length = self.chromosome_shape[0]
        strand_pair = int(strand) // 2
        for sub_strand in (2 * strand_pair, 2 * strand_pair + 1):
            if not self._span_fully_polymerized(
                intervals_by_strand, position, own_footprint, sub_strand, length
            ):
                return False
        return True

    @staticmethod
    def _span_fully_polymerized(
        intervals_by_strand: dict[int, list[tuple[int, int]]],
        position: int,
        span_len: int,
        strand: int,
        length: int,
    ) -> bool:
        """Is ``[position, position + span_len - 1]`` (circular) entirely
        covered by ``polymerizedRegions`` runs on ``strand``? Each run
        ``(start, run_len)`` (guaranteed non-wrapping in absolute
        coordinates by ``chromosome_store``'s own invariant) is remapped
        to the query's relative frame (``rel_start = (start - position) %
        length``, matching the same circular convention ``_is_polymerized``
        already uses for single-point membership). A run can still WRAP in
        this *relative* frame even though it never wraps absolutely (e.g.
        a single run spanning the entire chromosome, or any run whose
        absolute end passes the point ``length`` positions ahead of
        ``position``) -- such a run is split into its two relative
        sub-windows (``[rel_start, length)`` and ``[0, rel_end - length)``)
        before clipping to the query window ``[0, span_len)``, so a huge
        or awkwardly-positioned run is never silently dropped just because
        its naive relative start falls outside the query window."""
        intervals = intervals_by_strand.get(int(strand))
        if not intervals:
            return False
        windows: list[tuple[int, int]] = []
        for start, run_len in intervals:
            rel_start = (int(start) - int(position)) % length
            rel_end = rel_start + int(run_len)
            if rel_end <= length:
                if rel_start < span_len:
                    windows.append((rel_start, min(span_len, rel_end)))
            else:
                if rel_start < span_len:
                    windows.append((rel_start, min(span_len, length)))
                wrapped_end = rel_end - length
                if wrapped_end > 0:
                    windows.append((0, min(span_len, wrapped_end)))
        if not windows:
            return False
        windows.sort()
        covered_to = 0
        for win_start, win_end in windows:
            if win_start > covered_to:
                return False
            covered_to = max(covered_to, win_end)
            if covered_to >= span_len:
                return True
        return covered_to >= span_len

    def _sites_overlap(
        self,
        *,
        position_a: int,
        strand_a: int,
        position_b: int,
        strand_b: int,
        footprint: int,
    ) -> bool:
        """Real ``Chromosome.m::excludeOverlappingRegions`` (called from
        ``sampleAccessibleRegions`` whenever ``returnOverlappingRegions``
        is false -- the case for TranscriptionalRegulation's stable binds,
        since ``bindProteinToChromosome`` is called with
        ``isBindingStable=true`` and ``setSiteProteinBound`` passes
        ``~isBindingStable`` as ``sampleAccessibleRegions``'s
        ``returnOverlappingRegions`` argument): two candidate sites for
        the SAME TF species (same ``own_footprint``, since it is the same
        protein binding at both) sterically overlap iff their
        start-anchored spans ``[position, position + footprint - 1]``
        intersect on the same dsDNA chromosome-copy pair (``strand // 2``
        -- every TF this process binds is dsDNA-stranded, matching
        ``_third_party_site_occluded``'s / ``_site_damaged``'s mirroring).
        A batch draw that selects two of a TF's own candidate promoter
        sites close enough to overlap must not bind both in the same
        tick -- exactly like it must not bind onto a site already
        occupied by another (third-party) protein.
        """
        if int(strand_a) // 2 != int(strand_b) // 2:
            return False
        length = self.chromosome_shape[0]
        delta = (int(position_b) - int(position_a)) % length
        if delta == 0:
            return True
        return delta <= footprint - 1 or (length - delta) <= footprint - 1

    def _sample_accessible_sites_batched(
        self,
        *,
        n_needed: int,
        weights: np.ndarray,
        is_accessible: list[bool] | None = None,
        positions: list[int] | None = None,
        strands: list[int] | None = None,
        own_footprint: int = 0,
    ) -> list[int]:
        """Literal port of ``Chromosome.m::sampleAccessibleRegions``'s main
        selection loop (the batching behaviour ``bindProteinToChromosome``
        actually uses, distinct from a naive direct
        ``randsample(n, n_needed, false, w)`` call):

        .. code-block:: matlab

            idxs = [];
            while any(weights) && numel(idxs) < nSites
                nMoreSites = min(max(2 * (nSites - numel(idxs)), 10), nnz(weights));
                selectedSites = this.randStream.randsample(numel(weights), nMoreSites, false, weights);
                weights(selectedSites) = 0;
                [tmpTfs, ~, ~, extents] = this.isRegionAccessible(...);
                newIdxs = selectedSites(tmpTfs);
                if numel(newIdxs) > nSites - numel(idxs)
                    newIdxs = newIdxs(1:nSites - numel(idxs));
                end
                idxs = [idxs; newIdxs];
            end

        Critically, ``nMoreSites`` is a **batch size** (at least 10, or all
        remaining candidates, whichever is smaller) -- NOT simply
        ``n_needed``. Even a single-copy bind (``n_needed == 1``) draws a
        full weighted-without-replacement *ordering* of up to
        ``min(max(2, 10), n_candidates)`` candidates and takes only the
        first pick; it does **not** call the RandStream weighted-draw
        primitive with ``k = 1`` directly.

        ``bindTranscriptionFactors``'s own coarse ``accessible`` mask
        (``~tfBoundPromoters & isRegionPolymerized``) determines
        ``weights``' shape/values here -- exactly as many entries as the
        coarse candidate set, INCLUDING any site that will later fail the
        richer ``isRegionAccessible`` occupant-overlap/damage check inside
        this loop. A site that gets drawn (``selectedSites``) but fails
        that richer check still has its weight zeroed (consumed) and does
        NOT count toward ``n_needed`` -- the loop simply draws another
        batch. Pre-filtering such sites out of ``weights`` entirely
        (instead of passing ``is_accessible`` and filtering post-draw)
        changes both the weight distribution (renormalizes over fewer
        items) and the RNG draw count whenever any candidate is
        transiently occluded/damaged -- this was a real, empirically-found
        bug (see module docstring first-divergence ledger in
        ``STATUS_L21_TXREG_ACTIVE_FIX.md``).

        **``excludeOverlapping`` (2026-09-08):** real
        ``sampleAccessibleRegions`` additionally calls
        ``excludeOverlappingRegions(idxs, newIdxs, ...)`` after each
        batch's ``isRegionAccessible`` filter whenever
        ``returnOverlappingRegions`` is false -- the case here, since
        ``TranscriptionalRegulation``'s binds are stable
        (``bindProteinToChromosome``'s ``isBindingStable`` default,
        propagated through ``setSiteProteinBound`` as
        ``sampleAccessibleRegions``'s ``returnOverlappingRegions =
        ~isBindingStable = false``). This excludes any newly-drawn
        candidate site whose own-footprint span overlaps (on the same
        dsDNA chromosome-copy pair) a site already accepted earlier in
        this same binding call -- either from a prior while-loop
        iteration (``idxs``) or an earlier-processed member of the SAME
        batch draw (first-come-first-served, matching Karr's ``for i =
        numel(tmpIdxs):-1:2`` / ``startCoors(1:i-1)`` "only check against
        EARLIER entries" ordering exactly, see
        ``Chromosome.m::excludeOverlappingRegions``). Only active when
        ``positions``/``strands``/``own_footprint`` are supplied (every
        production call site supplies them; omitting them -- as no
        current call site does -- degrades to the pre-2026-09-08
        occlusion/damage-only behavior, never silently mis-applied to an
        unrelated caller).
        """
        weights = np.asarray(weights, dtype=np.float64).copy()
        n = int(weights.shape[0])
        accessible_mask = [True] * n if is_accessible is None else list(is_accessible)
        has_geometry = positions is not None and strands is not None and own_footprint > 0
        idxs: list[int] = []
        while np.any(weights) and len(idxs) < n_needed:
            n_more = min(max(2 * (n_needed - len(idxs)), 10), int(np.count_nonzero(weights)))
            if self._chromosome_rng is None:
                raise RuntimeError(
                    "KarrTranscriptionalRegulationProcess._chromosome_rng is None on an "
                    "active tick that genuinely needs a weighted site draw -- this violates "
                    "the persistence contract documented in __init__ (a fresh, tick-scoped "
                    "TxRegMcgRandStream/TxRegChromosomeLedgerRandStream must always be "
                    "present; production never sets this to None, and a replay harness must "
                    "inject a fresh per-tick instance, never leave it unset)."
                )
            selected_1based = self._chromosome_rng.randsample(n, n_more, False, weights)
            selected0 = [int(v) - 1 for v in selected_1based.tolist()]
            weights[selected0] = 0.0
            candidate_new = [idx0 for idx0 in selected0 if accessible_mask[idx0]]
            if has_geometry:
                # Literal excludeOverlappingRegions quirk (2026-09-08,
                # Opus re-review): MATLAB's exclusion loop is
                # ``for i = numel(tmpIdxs):-1:2; if tmpIdxs(i) <=
                # numel(idxs): continue; end; ...`` where ``tmpIdxs`` is 0
                # for every OLD (``idxs``) entry and 1..numel(newIdxs) for
                # this batch's NEW entries, in combined-list order (old
                # first, then new in draw order). Since old entries always
                # have ``tmpIdxs<=numel(idxs)`` (0 <= anything), they are
                # NEVER rechecked (correct -- already accepted). The SAME
                # condition, applied to a NEW entry's OWN within-batch
                # 1-based index, means: if ``numel(idxs)==k`` (the old
                # accepted count BEFORE this batch), the FIRST k NEW
                # candidates are unconditionally kept -- the overlap check
                # is skipped for them entirely, a genuine quirk/bug in
                # Karr's real algorithm (only ever triggers on a batch
                # AFTER the very first, when idxs is already non-empty).
                # Every later new candidate (index > k) IS checked, against
                # ALL earlier entries in the combined list in order --
                # including earlier NEW candidates that will themselves
                # end up excluded (a candidate rejected for overlapping an
                # even-earlier one still occupies its position/strand in
                # the comparison list and still blocks anything checked
                # after it; "combined" below is built from candidate_new,
                # not the accepted subset, so a not-yet-decided/rejected
                # earlier candidate is never removed from later checks).
                k = len(idxs)
                n_new = len(candidate_new)
                keep = [True] * n_new
                combined = idxs + candidate_new
                for local_i in range(n_new, 0, -1):
                    if local_i <= k:
                        continue
                    idx0 = candidate_new[local_i - 1]
                    global_pos = k + local_i
                    overlaps_earlier = any(
                        self._sites_overlap(
                            position_a=positions[idx0],
                            strand_a=strands[idx0],
                            position_b=positions[combined[j]],
                            strand_b=strands[combined[j]],
                            footprint=own_footprint,
                        )
                        for j in range(global_pos - 1)
                    )
                    if overlaps_earlier:
                        keep[local_i - 1] = False
                new_idxs = [candidate_new[i] for i in range(n_new) if keep[i]]
            else:
                new_idxs = candidate_new
            remaining_need = n_needed - len(idxs)
            if len(new_idxs) > remaining_need:
                new_idxs = new_idxs[:remaining_need]
            idxs.extend(new_idxs)
        return idxs

    def candidate_sites_for_tf(
        self,
        tf_i: int,
        *,
        occ: np.ndarray,
        intervals_by_strand: dict[int, list[tuple[int, int]]],
        chromosome_store: ChromosomeStore,
    ) -> tuple[list[tuple[int, int]], list[float], list[bool], list[int], list[int]]:
        """Extracted (2026-09-08, Opus re-review point: L2.2 gate must
        score Karr's REAL trace winner under OC's actual pre-tick
        candidate/weight/accessibility computation, not a re-simulated
        one) from ``_bind_transcription_factors``'s per-TF candidate-set
        construction loop -- the SAME code ``next_update`` itself calls,
        not a parallel re-derivation, so an L2.2 analysis consumer (see
        ``scripts/l22_evidence``) and production replay can never silently
        drift apart.

        Returns ``(candidates, weights, accessible_mask, positions,
        strands)`` for TF ``tf_i``, given the SAME per-tick inputs
        ``next_update`` itself would use (occupancy, polymerized-interval
        map, and chromosome store) -- everything needed to reconstruct
        the exact weighted-categorical/Plackett-Luce candidate
        distribution ``_sample_accessible_sites_batched`` would draw from,
        without needing to also draw from any RNG.
        """
        candidates: list[tuple[int, int]] = []
        weights: list[float] = []
        accessible_mask: list[bool] = []
        candidate_positions: list[int] = []
        candidate_strands: list[int] = []
        for col, strand_col in ((0, self.site_strand_col0), (1, self.site_strand_col1)):
            for s in range(self._n_sites):
                if int(self.site_tf_index[s]) != tf_i:
                    continue
                if occ[s, col]:
                    continue
                if self.site_affinity[s] <= 0.0:
                    continue
                if not self._is_polymerized(
                    intervals_by_strand, int(self.site_position[s]), int(strand_col[s])
                ):
                    continue
                candidates.append((s, col))
                weights.append(float(self.site_affinity[s]))
                position = int(self.site_position[s])
                strand = int(strand_col[s])
                candidate_positions.append(position)
                candidate_strands.append(strand)
                accessible_mask.append(
                    not self._third_party_site_occluded(chromosome_store, position, strand, tf_i=tf_i)
                    and not self._site_damaged(chromosome_store, position, strand, tf_i=tf_i)
                    and self._footprint_double_stranded_polymerized(
                        intervals_by_strand, position, strand, tf_i=tf_i
                    )
                )
        return candidates, weights, accessible_mask, candidate_positions, candidate_strands

    def _bind_transcription_factors(
        self,
        *,
        tf_counts: np.ndarray,
        occ: np.ndarray,
        intervals_by_strand: dict[int, list[tuple[int, int]]],
        chromosome_store: ChromosomeStore,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Literal port of ``TranscriptionalRegulation.m::bindTranscriptionFactors``.

        For each TF species (in ascending local-index order, matching
        Karr's ``for i = 1:size(this.enzymes,1)``), stochastically binds
        free copies to accessible sites (not already bound, chromosome
        region polymerized, not sterically occluded by another bound
        protein) weighted by site affinity, using the literal WholeCell
        weighted-without-replacement algorithm
        (``RandStream.randsample(n,k,false,w)``, see
        ``TxRegMcgRandStream.randsample``). Binding is stable and
        never reversed by this process (Karr never unbinds a TF from a
        promoter in this method).

        Returns ``(new_binds_col0, new_binds_col1, n_bound_delta)``:
        boolean ``(n_sites,)`` arrays flagging newly-bound sites per
        chromosome copy, and an integer ``(n_tf,)`` array of total new
        binds (both copies) per TF species.
        """
        new_binds_col0 = np.zeros(self._n_sites, dtype=bool)
        new_binds_col1 = np.zeros(self._n_sites, dtype=bool)
        n_bound_delta = np.zeros(self._n_tf, dtype=np.int64)
        free_copies = np.maximum(0, np.floor(tf_counts)).astype(np.int64)

        for tf_i in range(self._n_tf):
            if free_copies[tf_i] <= 0:
                continue

            # Column-major candidate order (all col0 sites first, then all
            # col1 sites) to match Karr's `find((tfIndexs==i)&accessible)`
            # linear-index order over the [sites, 2] matrix -- this order
            # feeds directly into the weighted RNG draw, so it must match
            # exactly for bit-identical replay. Karr's `bindTranscriptionFactors`
            # coarse `accessible` mask is `~tfBoundPromoters & isRegionPolymerized`
            # ONLY -- third-party occlusion is a richer, separate check applied
            # INSIDE the sampling loop (`isRegionAccessible`, see
            # `_sample_accessible_sites_batched`'s docstring), not folded into
            # this coarse candidate list.
            candidates, weights, accessible_mask, candidate_positions, candidate_strands = (
                self.candidate_sites_for_tf(
                    tf_i,
                    occ=occ,
                    intervals_by_strand=intervals_by_strand,
                    chromosome_store=chromosome_store,
                )
            )

            if not candidates:
                continue

            max_bindings = int(min(free_copies[tf_i], len(candidates)))
            if max_bindings <= 0:
                continue

            chosen0 = self._sample_accessible_sites_batched(
                n_needed=max_bindings,
                weights=np.asarray(weights, dtype=np.float64),
                is_accessible=accessible_mask,
                positions=candidate_positions,
                strands=candidate_strands,
                own_footprint=int(self._own_footprint_by_tf[tf_i]),
            )
            for idx0 in chosen0:
                s, col = candidates[idx0]
                if col == 0:
                    new_binds_col0[s] = True
                else:
                    new_binds_col1[s] = True
                n_bound_delta[tf_i] += 1

        return new_binds_col0, new_binds_col1, n_bound_delta

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep
        tf_counts = self._read_tf_counts(states)
        occ = self._read_site_occupancy(states)

        chrom_state = states.get("chromosome", {})
        if not isinstance(chrom_state, dict):
            chrom_state = {}
        chromosome_store = self._resolve_chromosome_store(chrom_state)
        intervals_by_strand = self._polymerized_intervals_by_strand(chromosome_store)

        new_binds_col0, new_binds_col1, n_bound_delta = self._bind_transcription_factors(
            tf_counts=tf_counts,
            occ=occ,
            intervals_by_strand=intervals_by_strand,
            chromosome_store=chromosome_store,
        )

        occ_after_col0 = occ[:, 0] | new_binds_col0
        occ_after_col1 = occ[:, 1] | new_binds_col1

        # Karr `boundTFs = histc(tfIndexs(logical(tfBoundPromoters(:,1))), 1:numel(enzymes))`
        # -- column 0 (primary copy) occupancy only, NOT both columns.
        bound_tfs = np.zeros(self._n_tf, dtype=np.int64)
        for s in range(self._n_sites):
            if occ_after_col0[s]:
                bound_tfs[int(self.site_tf_index[s])] += 1

        # Karr `calcBindingProbabilityFoldChange`: per-chromosome-copy fold
        # change product over bound sites. Column 0 only is projected to
        # the single-valued downstream `tx_rate_fold_change` port (see
        # module docstring "Single-copy downstream fold-change").
        fold_change_col0 = np.ones(self._n_tu, dtype=np.float64)
        tf_binding_state = np.zeros((self._n_tf, self._n_tu), dtype=bool)
        for s in range(self._n_sites):
            tu_i = int(self.site_tu_index[s])
            tf_i = int(self.site_tf_index[s])
            if occ_after_col0[s]:
                fold_change_col0[tu_i] *= self.site_activity[s]
                tf_binding_state[tf_i, tu_i] = True
            if occ_after_col1[s]:
                tf_binding_state[tf_i, tu_i] = True

        float64_max = np.finfo(np.float64).max
        fold_change_col0 = np.clip(fold_change_col0, a_min=0.0, a_max=float64_max)

        # otherActivities (TF-presence effect) uses Karr's post-bind free
        # copy count (`this.enzymes` at the time `calcBindingProbabilityFoldChange`
        # runs, i.e. after `bindTranscriptionFactors` already consumed
        # copies this tick).
        tf_counts_after = tf_counts - n_bound_delta.astype(np.float64)
        tf_present = tf_counts_after > 0.0
        if np.any(tf_present):
            other_effects = np.where(tf_present[:, np.newaxis], self.tf_other_activities, 1.0)
            # TODO(L4): TranscriptionalRegulation_flat.mat currently has 5 TFs, so
            # direct float64 products are stable; revisit log-space accumulation if
            # future fixtures materially increase TF cardinality.
            other_multiplier = np.clip(
                np.prod(other_effects, axis=0, dtype=np.float64), a_min=0.0, a_max=float64_max
            )
            fold_change_col0 = np.clip(
                fold_change_col0 * other_multiplier, a_min=0.0, a_max=float64_max
            )

        update: dict[str, Any] = {}

        tf_bound_promoters_update: dict[str, float] = {}
        for s in range(self._n_sites):
            if new_binds_col0[s]:
                tf_bound_promoters_update[self.tf_bound_promoters_wids[s]] = 1.0
            if new_binds_col1[s]:
                tf_bound_promoters_update[self.tf_bound_promoters_wids[self._n_sites + s]] = 1.0
        if tf_bound_promoters_update:
            update["tf_bound_promoters"] = tf_bound_promoters_update

        update["bound_tfs"] = {
            tf_wid: float(bound_tfs[tf_i]) for tf_i, tf_wid in enumerate(self.tf_wids)
        }

        update["tf_binding"] = {
            tf_wid: {
                tu_wid: (1.0 if tf_binding_state[tf_i, tu_i] else 0.0)
                for tu_i, tu_wid in enumerate(self.tu_wids)
            }
            for tf_i, tf_wid in enumerate(self.tf_wids)
        }

        update["tx_rate_fold_change"] = {
            tu_wid: float(fold_change_col0[tu_i]) for tu_i, tu_wid in enumerate(self.tu_wids)
        }

        if np.any(n_bound_delta != 0):
            update["enzymes"] = {
                tf_wid: -float(n_bound_delta[tf_i])
                for tf_i, tf_wid in enumerate(self.tf_wids)
                if n_bound_delta[tf_i] != 0
            }
            update["boundEnzymes"] = {
                tf_wid: float(n_bound_delta[tf_i])
                for tf_i, tf_wid in enumerate(self.tf_wids)
                if n_bound_delta[tf_i] != 0
            }

        return update


__all__ = ["KarrTranscriptionalRegulationProcess", "_load_fixture"]
