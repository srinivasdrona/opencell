"""Vivarium Process for Karr DNASupercoiling (Phase F chromosome-store port)."""

from __future__ import annotations

from functools import lru_cache
import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.m_gen_constants import GENOME_LENGTH_BP
from opencell.m1.protein_complexes import load_default as _load_protein_complex_composition
from opencell.state.chromosome_store import (
    CHROMOSOME_FIELDS,
    ChromosomeBindingResult,
    ChromosomeStore,
    SparseTriplet,
    sparse_triplet_schema,
)
from opencell.vivarium.dnas_chromosome_release_ledger import (
    ChromosomeReleaseLedger,
    ChromosomeReleaseReplayRng,
    default_ledger_path,
)
from opencell.vivarium.dnas_process_rng_ledger import (
    ProcessRngLedger,
    ProcessRngReplayRng,
    default_process_rng_ledger_path,
)
from opencell.vivarium.dnas_superhelical_density_ledger import (
    SuperhelicalDensityLedger,
    default_ledger_path as default_superhelical_density_ledger_path,
)

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/DNASupercoiling_flat.mat"
_DEFAULT_COMPLEXATION_FIXTURE_PATH = (
    "data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat"
)
_DEFAULT_CHROMOSOME_FIXTURE_PATH = "data/karr_fixtures/per_process/Chromosome.npz"
_DEFAULT_DNA_REPAIR_FIXTURE_PATH = "data/karr_fixtures/per_process/DNARepair_flat.mat"
_DAMAGE_FIELD_NAMES = (
    "gapSites",
    "abasicSites",
    "damagedSugarPhosphates",
    "damagedBases",
    "intrastrandCrossLinks",
    "strandBreaks",
    "hollidayJunctions",
)
_DNA_STRANDEDNESS_SSDNA = 1
_DNA_STRANDEDNESS_DSDNA = 2
_DNA_STRANDEDNESS_XSDNA = 3


def _resolve_fixture_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    raise FileNotFoundError(f"Fixture not found: {path}")


@lru_cache(maxsize=4)
def _load_m6ad_global_index(path: str) -> int:
    """The global metabolite/substrate index MATLAB uses to mark an
    N6-methyladenine (m6AD) methylation site in ``Chromosome.damagedBases``.

    ``Chromosome.getDamagedSites`` (``Chromosome.m:1707``) -- the real
    function behind ``get.damagedSites`` -- explicitly EXCLUDES m6AD-valued
    ``damagedBases`` entries by default (``includeM6AD=false`` in
    ``calcDamagedSites``, ``Chromosome.m:3626-3627``): m6AD is a routine,
    non-damaging epigenetic mark (near-universal at this organism's
    restriction-modification recognition motif), not a genuine DNA lesion,
    and real MATLAB's ``getAccessibleRegions`` binding-exclusion logic (via
    ``dmgPosStrnds = find(this.damagedSites)``, ``Chromosome.m:1651``) never
    treats it as something that blocks protein binding. opencell's own
    ``karr_dna_repair.py`` (``_m6ad_global_index``,
    ``_rm_m6ad_coords``/``_damaged_sites_value_map``) already implements
    this exact exclusion for its own damage-cause attribution; this
    function sources the SAME global index (never a hardcoded literal) for
    ``KarrDNASupercoilingProcess._damage_pairs``'s accessible-region
    exclusion, which independently needed but lacked this filter (see
    ``STATUS_L22_DNAS_SEPT2.md``'s audit-boundary-breach root-causing).

    DNARepair's own fixture (not DNASupercoiling's) is the source: it maps
    ``substrateIndexs_m6AD`` (DNARepair's local substrate-list index for
    the m6AD metabolite) through ``substrateGlobalIndexs`` (that process's
    local-to-global substrate index table) to the metabolite table's
    global index -- the same value MATLAB's ``metabolite.m6ADIndexs``
    resolves to, and the same value every process's ``damagedBases``
    triplet stores at an m6AD-methylated position, since ``damagedBases``
    values are global metabolite indices, not process-local ones.
    """
    resolved = _resolve_fixture_path(path)
    mat = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
    fx = mat["data"].fixture
    substrate_global_indices = np.asarray(fx.substrateGlobalIndexs, dtype=np.int64).reshape(-1)
    m6ad_local_idx = int(_coerce_scalar(fx.substrateIndexs_m6AD)) - 1
    return int(substrate_global_indices[m6ad_local_idx])


def _coerce_scalar(value: object) -> object:
    out = value
    while isinstance(out, np.ndarray):
        if out.size == 0:
            return 0
        out = out.flat[0]
    return out


def _parse_wid_array(value: object) -> list[str]:
    values = np.asarray(value, dtype=object)
    out: list[str] = []
    for raw in values.ravel():
        token = _coerce_scalar(raw)
        out.append(str(token))
    return out


def _to_finite(value: float, fallback: float) -> float:
    if not np.isfinite(value):
        return float(fallback)
    return float(value)


def _round_half_up(value: float) -> int:
    return int(math.floor(float(value) + 0.5))


def _round_half_down(value: float) -> int:
    value = float(value)
    floor = math.floor(value)
    return int(floor + ((value - floor) > 0.5))


def _load_d2_complex_wid_set(path: str | Path) -> set[str]:
    resolved = _resolve_fixture_path(path)
    mat = loadmat(str(resolved))
    fx = mat["data"]["fixture"][0, 0]
    values = np.asarray(fx["complexWholeCellModelIDs"], dtype=object)
    if values.shape == (1, 1):
        values = np.asarray(values[0, 0], dtype=object)

    out: set[str] = set()
    for raw in values.ravel():
        value: object = raw
        while isinstance(value, np.ndarray):
            if value.size == 0:
                value = ""
                break
            value = value.flat[0]
        out.add(str(value))
    return out


@lru_cache(maxsize=1)
def _load_complex_wids_by_global_index() -> dict[int, str]:
    model = _load_protein_complex_composition()
    return {
        int(complex_obj.idx_1based): str(wid)
        for wid, complex_obj in model.complexes.items()
    }


def _split_circular_region(start: int, length: int, sequence_len: int) -> list[tuple[int, int]]:
    if length <= 0:
        return []
    start = int(start) % sequence_len
    length = int(length)
    if length >= sequence_len:
        return [(0, sequence_len - 1)]
    end = start + length - 1
    if end < sequence_len:
        return [(start, end)]
    return [
        (start, sequence_len - 1),
        (0, (end % sequence_len)),
    ]


def _matlab_join_split_regions(
    regions: list[tuple[int, int, int]],
    *,
    chromosome_length: int,
) -> list[tuple[int, int, int]]:
    """Literal port of ``Chromosome.joinSplitRegions`` (``Chromosome.m:2790-2820``),
    INCLUDING its origin-wrap normalization step (``Chromosome.m:2811-2817``).

    This was previously (incorrectly) approximated by the shared
    ``_merge_linear_regions`` helper (adjacent/overlapping same-strand
    merge only), with a docstring claim that the origin-wrap merge "does
    not occur for the exclusion lists this function is used with" -- that
    claim was wrong and has been removed. Root cause C
    (``_binding_blocked_regions`` now passes RAW, potentially
    boundary-crossing ``(position, position+footprint)`` exclusion
    intervals, never pre-split at the chromosome boundary) makes this
    step directly reachable: a bound site whose footprint extends past
    ``chromosome_length`` produces an entry whose recorded end already
    exceeds the chromosome length BEFORE this function runs, and if
    another exclusion entry on the SAME pair-strand starts close enough
    to the origin, real MATLAB's origin-wrap step REWRITES that entry's
    length in place -- directly changing the value
    ``_matlab_exclude_regions``'s ``excLens(end)`` bug reads. Confirmed
    against live MATLAB via a standalone, hardcoded-input probe
    (``scripts/matlab/l22_dnas_join_split_regions_originwrap_probe.m``,
    calling the real, unmodified ``Chromosome.joinSplitRegions`` and
    ``Chromosome.excludeRegions`` directly): for exclusions (0-based)
    ``[(500, 0, 10), (580051, 0, 630)]`` on a 580076bp chromosome, real
    MATLAB's post-``joinSplitRegions`` lengths are ``[510, 25]`` -- NOT
    the raw ``[10, 630]`` a plain adjacent-merge would report -- and the
    real ``excludeRegions`` output for the fragment this determines the
    accessibility of (0-based ``[510, 604]``) is fully accessible,
    matching this port's own output exactly.

    Operates entirely in OC's 0-based coordinate convention. Every
    relational check in the real (1-based) algorithm
    (``ends(j)+1 >= starts(j+1)``, ``ends(idxs(end))+1 >= starts(idx)+L``)
    is translation-invariant under a uniform 0-based/1-based shift, so
    the SAME comparisons apply verbatim; only the two absolute-position
    normalizations (initial ``mod(pos-1,L)+1`` and the origin-wrap's
    ``starts(idx)=1``/``ends(idxs(end))=L``) need their 0-based
    equivalents (``pos % L``, ``starts[idx]=0``, ``ends[last]=L-1``).

    Critically, like the real function, this does NOT re-sort the
    output after applying the origin-wrap: `excludeRegions`'s later
    "leftmost"/"rightmost" matched-exclusion logic is itself applied to
    whatever array-index order `joinSplitRegions` returns (real MATLAB
    never re-sorts here either), so `_matlab_exclude_regions` must use
    this function's output positionally, not assume it is fully
    position-sorted.
    """
    if not regions:
        return []
    chrom_len = int(chromosome_length)

    # Normalize each entry's start into [0, chrom_len) -- 0-based
    # equivalent of MATLAB's `mod(pos-1, L) + 1`.
    normalized = [(int(start) % chrom_len, int(strand), int(length)) for start, strand, length in regions]
    # Sort by (strand, start) ascending -- MATLAB's column-major sort_subs order.
    normalized.sort(key=lambda item: (item[1], item[0]))

    starts = [item[0] for item in normalized]
    ends = [item[0] + item[2] - 1 for item in normalized]
    strands = [item[1] for item in normalized]
    tfs = [True] * len(normalized)

    for strand_value in sorted(set(strands)):
        idxs = [i for i, s in enumerate(strands) if s == strand_value]
        for pos in range(len(idxs) - 1):
            j, j1 = idxs[pos], idxs[pos + 1]
            if ends[j] + 1 >= starts[j1]:
                starts[j1] = starts[j]
                ends[j1] = max(ends[j], ends[j1])
                tfs[j] = False
        if len(idxs) >= 2:
            first_surviving = next(i for i in idxs if tfs[i])
            last_idx = idxs[-1]
            if ends[last_idx] + 1 >= starts[first_surviving] + chrom_len:
                ends[last_idx] = chrom_len - 1
                starts[first_surviving] = 0

    return [
        (starts[i], strands[i], ends[i] - starts[i] + 1)
        for i in range(len(normalized))
        if tfs[i]
    ]


def _matlab_join_split_over_oric_regions(
    regions: list[tuple[int, int, int]],
    *,
    chromosome_length: int,
) -> list[tuple[int, int, int]]:
    """Literal port of ``Chromosome.joinSplitOverOriCRegions``
    (``Chromosome.m:2767-2788``), in OC's 0-based coordinate convention.

    Real ``Chromosome.excludeRegions`` calls this at BOTH ends of its
    computation (``Chromosome.m:2606`` on ``incPosStrnds``, the included
    fragment list, BEFORE the main exclusion loop; and again
    (``Chromosome.m`` near ``2674-2677``) on the raw output fragment list,
    BEFORE the final ``mod(pos-1,L)+1`` position normalization and sort).
    A prior version of ``_matlab_exclude_regions`` omitted this entirely
    at both call sites, with a docstring claiming it was "not reachable
    for this function's callers" -- that claim was false (Opus's review
    found it): a real, decisive live-MATLAB cross-check
    (``scripts/matlab/l22_dnas_join_split_regions_originwrap_probe.m``'s
    ``excludeRegions([1 1], 580076, [100 1; 580000 1], [50; 50])`` case)
    shows real MATLAB returns exactly TWO accessible regions -- this join
    step is what collapses what would otherwise be three separate
    fragments (one of which straddles the origin, position 1 and
    position ``sequenceLen`` in the SAME call) into two.

    For each strand value present, if one region starts at position 0
    (0-based; ``pos==1`` 1-based) and a DIFFERENT region ends at
    ``chromosome_length-1`` (0-based; ``ends==sequenceLen`` 1-based) on
    that SAME strand, the origin-ending region's length is extended to
    absorb the position-0 region's full span, and the position-0 region
    is DELETED from the list entirely (not merely marked non-surviving,
    unlike ``joinSplitRegions``'s per-strand merge) -- real MATLAB does
    this via in-place row deletion (``pos(idx1,:) = []``), which this
    port replicates with an actual list deletion so index bookkeeping
    for subsequent strand iterations matches exactly (deleting a row
    shifts every later row's index down by one, exactly as MATLAB's
    array deletion does).

    Iterates ``strand in 0..max(strand)`` (the 0-based equivalent of
    MATLAB's 1-based ``for i = 1:max(strnds)`` -- NOT merely the strand
    values actually present), finding the FIRST matching region for each
    of ``pos==0``/``ends==chromosome_length-1`` in CURRENT array order via
    ``find(...,1,'first')`` semantics -- never a full sort -- because
    real MATLAB never sorts this list before or during this operation
    either.
    """
    if not regions:
        return []
    chrom_len = int(chromosome_length)
    positions = [int(r[0]) for r in regions]
    strands = [int(r[1]) for r in regions]
    ends = [int(r[0]) + int(r[2]) - 1 for r in regions]

    max_strand = max(strands)
    for strand_value in range(0, max_strand + 1):
        idx1 = next(
            (k for k in range(len(positions)) if positions[k] == 0 and strands[k] == strand_value),
            None,
        )
        idx2 = next(
            (k for k in range(len(positions)) if ends[k] == chrom_len - 1 and strands[k] == strand_value),
            None,
        )
        if idx1 is None or idx2 is None or idx1 == idx2:
            continue

        ends[idx2] = ends[idx2] + (ends[idx1] - positions[idx1] + 1)
        del positions[idx1]
        del strands[idx1]
        del ends[idx1]

    return [
        (positions[k], strands[k], ends[k] - positions[k] + 1)
        for k in range(len(positions))
    ]


def _merge_linear_regions(regions: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    if not regions:
        return []
    regions = sorted(regions, key=lambda item: (item[1], item[0]))
    merged: list[list[int]] = [[regions[0][0], regions[0][1], regions[0][2]]]
    for start, strand, length in regions[1:]:
        last = merged[-1]
        last_end = last[0] + last[2] - 1
        if strand == last[1] and start <= last_end + 1:
            last[2] = max(last_end, start + length - 1) - last[0] + 1
            continue
        merged.append([start, strand, length])
    return [(start, strand, length) for start, strand, length in merged]


def _matlab_exclude_regions(
    included: list[tuple[int, int, int]],
    excluded: list[tuple[int, int, int]],
    *,
    chromosome_length: int,
) -> list[tuple[int, int, int]]:
    """Literal, bug-compatible port of ``Chromosome.excludeRegions``
    (``Chromosome.m:2597-2670``), used to compute the real, live
    accessible-space fragments for stable protein binding.

    This is deliberately NOT a "textbook" interval-subtraction routine.
    Real MATLAB's ``excludeRegions`` has a genuine indexing bug at
    ``Chromosome.m:2632`` (and its mirror at ``Chromosome.m:2639``): the
    "does the matched exclusion reach past this fragment's end?" check
    reads ``excLens(end)`` -- the length of the LAST entry in the entire
    (sorted, wraparound-tripled) exclusion array passed to the function --
    instead of ``excLens(excIdxs(end))``, the length of the actual matched
    exclusion entry. Since this is what Karr et al.'s actual, validated
    2012 simulation code executes for every real run this project treats
    as ground truth (independently confirmed via
    ``scripts/matlab/l22_dnas_full_bind_activity_probe.m``'s isolated,
    hardcoded-input cross-check against live MATLAB: the real function
    returns empty for a fragment a correct implementation would find
    ~375bp of genuinely free space in, and reproducing the bug is the
    only way to match that), opencell must replicate this exact behavior
    bit-for-bit rather than "fix" it -- fidelity to what actually ran is
    this project's mandate, not fidelity to what the algorithm's comment
    or docstring claims it does.

    Also replicates ``Chromosome.joinSplitOverOriCRegions``
    (``Chromosome.m:2767-2788``, via ``_matlab_join_split_over_oric_regions``)
    at BOTH real call sites: on ``included`` before the main exclusion
    loop (``Chromosome.m:2606``), and on the raw output fragment list
    before the final position normalization and sort
    (``Chromosome.m`` near ``2674-2677``). A prior version of this
    function omitted this entirely, with a docstring claiming it was
    unreachable for this module's callers -- that claim was false (Opus's
    review found it, and a decisive live-MATLAB cross-check confirms it:
    ``excludeRegions([1 1], 580076, [100 1; 580000 1], [50; 50])`` returns
    exactly TWO accessible regions in real MATLAB, not three -- see
    ``scripts/matlab/l22_dnas_join_split_regions_originwrap_probe.m``'s
    ``opus_review2_full_chromosome_included``/``oric_join_real_footprints``
    cases and this module's
    ``test_matlab_join_split_over_oric_regions_reproduces_real_matlab_wrap_join``/
    ``test_accessible_binding_regions_join_split_over_oric_wrapped_fragment``
    regression tests).

    ``included``/``excluded`` are ``(start, strand, length)`` triples in
    OC's 0-based, already-pair-collapsed strand-index space (matching
    ``positive_regions``/``_binding_blocked_regions``'s existing
    convention). Positions are 0-based, half-open-equivalent via
    ``length`` (matching this module's existing convention elsewhere).

    Returns the accessible fragment list, sorted by ``(strand, start)``
    ascending -- matching MATLAB's final ``SparseMat.sort_subs`` output
    order, which the subsequent ``randStream.randsample`` call is
    order-sensitive to for exact RNG replay.
    """
    if not included:
        return []
    chrom_len = int(chromosome_length)

    # Chromosome.m:2606 -- joinSplitOverOriCRegions on the included
    # fragment list, BEFORE any exclusion is applied.
    included = _matlab_join_split_over_oric_regions(included, chromosome_length=chrom_len)

    if not excluded:
        results = [(int(s), int(st), int(s) + int(le) - 1) for s, st, le in included]
    else:
        # joinSplitRegions (Chromosome.m:2790-2820): sort by (strand,
        # position) ascending [MATLAB's column-major sort_subs order],
        # merge overlapping/adjacent same-strand exclusions, INCLUDING the
        # origin-wrap normalization (`_matlab_join_split_regions`'s
        # docstring has the full rationale + a worked example matching a
        # live-MATLAB cross-check).
        excluded_merged = _matlab_join_split_regions(excluded, chromosome_length=chrom_len)

        # excLens(end): the length of the LAST entry in the merged/sorted
        # exclusion list -- a single, call-global value. This is the buggy
        # substitute for "the matched exclusion's own length" that real
        # MATLAB's excludeRegions actually uses; replicated verbatim.
        last_len = excluded_merged[-1][2]

        exc_starts = np.array([item[0] for item in excluded_merged], dtype=np.int64)
        exc_strands = np.array([item[1] for item in excluded_merged], dtype=np.int64)
        exc_lens = np.array([item[2] for item in excluded_merged], dtype=np.int64)

        # Triple for circular wraparound (excPos = [pos-L; pos; pos+L]).
        tri_starts = np.concatenate([exc_starts - chrom_len, exc_starts, exc_starts + chrom_len])
        tri_strands = np.concatenate([exc_strands, exc_strands, exc_strands])
        tri_lens = np.concatenate([exc_lens, exc_lens, exc_lens])
        tri_ends_incl = tri_starts + tri_lens - 1

        results = []
        for start, strand, length in included:
            start_coor = int(start)
            end_coor = start_coor + int(length) - 1
            strnd = int(strand)

            strand_mask = tri_strands == strnd
            overlap_mask = strand_mask & (
                ((tri_starts <= start_coor) & (tri_ends_incl >= start_coor))
                | ((tri_starts <= end_coor) & (tri_ends_incl >= end_coor))
                | ((tri_starts >= start_coor) & (tri_ends_incl <= end_coor))
            )
            exc_idxs = np.flatnonzero(overlap_mask)

            if exc_idxs.size == 0:
                addtl_starts = np.array([start_coor], dtype=np.int64)
                addtl_ends = np.array([end_coor], dtype=np.int64)
            else:
                matched_starts = tri_starts[exc_idxs]
                matched_lens = tri_lens[exc_idxs]
                if matched_starts[0] <= start_coor:
                    # BUG-COMPATIBLE: `last_len` (global), not
                    # `matched_lens[-1]` (the actual matched entry).
                    if matched_starts[-1] + last_len - 1 >= end_coor:
                        addtl_starts = matched_starts[:-1] + matched_lens[:-1]
                        addtl_ends = matched_starts[1:] - 1
                    else:
                        addtl_starts = matched_starts + matched_lens
                        addtl_ends = np.concatenate([matched_starts[1:] - 1, [end_coor]])
                else:
                    if matched_starts[-1] + last_len - 1 >= end_coor:
                        addtl_starts = np.concatenate([[start_coor], matched_starts[:-1] + matched_lens[:-1]])
                        addtl_ends = matched_starts - 1
                    else:
                        addtl_starts = np.concatenate([[start_coor], matched_starts + matched_lens])
                        addtl_ends = np.concatenate([matched_starts - 1, [end_coor]])

            for frag_start, frag_end in zip(addtl_starts.tolist(), addtl_ends.tolist(), strict=False):
                results.append((frag_start, strnd, frag_end))

    # Un-shift any fragment derived from a "+L"-wraparound-shifted match,
    # then drop any degenerate/invalid (start > end) fragment.
    unshifted: list[tuple[int, int, int]] = []
    for frag_start, strnd, frag_end in results:
        if frag_start > chrom_len:
            frag_start -= chrom_len
            frag_end -= chrom_len
        if frag_start > frag_end:
            continue
        unshifted.append((frag_start, strnd, frag_end - frag_start + 1))

    # Chromosome.m near 2674-2677 -- joinSplitOverOriCRegions AGAIN, on the
    # raw output fragment list, BEFORE the final position normalization.
    joined_output = _matlab_join_split_over_oric_regions(unshifted, chromosome_length=chrom_len)

    # Final position normalization (`mod(pos-1,L)+1` in 1-based ==
    # `pos % L` in 0-based) and sort by (strand, start) ascending --
    # matching MATLAB's final `SparseMat.sort_subs` output order.
    final = [(start % chrom_len, strand, length) for start, strand, length in joined_output]
    final.sort(key=lambda item: (item[1], item[0]))
    return final


class KarrDNASupercoilingProcess(Process):
    """Chromosome-sparse Karr DNASupercoiling with legacy sigma compatibility."""

    name = "karr_dna_supercoiling"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "complexation_fixture_path": _DEFAULT_COMPLEXATION_FIXTURE_PATH,
        "chromosome_fixture_path": _DEFAULT_CHROMOSOME_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "chromosome_length_bp": float(GENOME_LENGTH_BP),
        "bp_per_turn": 10.5,
        "equilibrium_supercoil_density": -0.06,
        "supercoil_density_min": -0.2,
        "supercoil_density_max": 0.2,
        "sigma_deadband": 0.001,
        "gyrase_activity_rate": None,
        "topoi_activity_rate": None,
        "topoiv_activity_rate": None,
        "gyrase_logistic_const": None,
        "topoi_logistic_const": None,
        "topoiv_logistic_const": None,
        "gyrase_sigma_limit": None,
        "topoi_sigma_limit": None,
        "topoiv_sigma_limit": None,
        "gyrase_atp_cost": None,
        "topoi_atp_cost": None,
        "topoiv_atp_cost": None,
        "gyrase_link_delta": -2.0,
        "topoi_link_delta": 1.0,
        "topoiv_link_delta": -2.0,
        "replication_supercoil_load_rate": 4.0,
        "reference_gyrase_count": 3.0,
        "reference_topoiv_count": 12.0,
        "request_safety_factor": 1.2,
        "request_max_atp": 10_000.0,
        "replay_positive_supercoil_load": 44.0,
        "replay_rng_warmup_draws": None,
        "replay_topoiv_sigma_bias": 3.0,
        "chromosome_release_rng_warmup_draws": 3,
        "chromosome_release_rng_ledger_path": None,
        "process_rng_ledger_path": None,
        "dna_repair_fixture_path": _DEFAULT_DNA_REPAIR_FIXTURE_PATH,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._load_chromosome_fixture(self.parameters["chromosome_fixture_path"])
        self._m6ad_global_index = _load_m6ad_global_index(
            self.parameters["dna_repair_fixture_path"]
        )
        self._canonical_complex_wids = _load_d2_complex_wid_set(
            self.parameters["complexation_fixture_path"]
        )
        self.complex_enzyme_wids = [
            wid for wid in self.enzyme_wids if wid in self._canonical_complex_wids
        ]
        self.protein_enzyme_wids = [
            wid for wid in self.enzyme_wids if wid not in self._canonical_complex_wids
        ]
        self.enzyme_store_by_wid = {
            wid: ("complex" if wid in self._canonical_complex_wids else "protein")
            for wid in self.enzyme_wids
        }
        self._rng_seed = int(self.parameters["rng_seed"])
        self._rng = np.random.default_rng(self._rng_seed)
        self._replay_rng_aligned = False
        warmup_cfg = self.parameters.get("replay_rng_warmup_draws")
        if warmup_cfg is None:
            warmup_cfg = int(round(sum(self.total_enzyme_seed.values())))
        self._replay_rng_warmup_draws = max(0, int(warmup_cfg))
        self._chromosome_release_rng_warmup_draws = max(
            0,
            int(self.parameters.get("chromosome_release_rng_warmup_draws", 3)),
        )
        self._chromosome_release_rng: Any | None = None
        self._tick_index = 0
        self._chromosome_release_ledger = self._load_chromosome_release_ledger()
        self._ensure_chromosome_release_rng()
        self._superhelical_density_ledger = self._load_superhelical_density_ledger()
        self._process_rng_ledger = self._load_process_rng_ledger()
        self._process_rng_replay_cache: tuple[int, ProcessRngReplayRng] | None = None

        self.chromosome_length = int(round(float(self.parameters["chromosome_length_bp"])))
        self.n_compartments = ChromosomeStore.DEFAULT_N_COMPARTMENTS
        self.chromosome_shape = (self.chromosome_length, self.n_compartments)
        self._complex_wid_by_global_index = _load_complex_wids_by_global_index()
        self._enzyme_idx_by_global_index = {
            int(global_index): idx
            for idx, global_index in enumerate(self.enzyme_global_indices.tolist())
        }
        self._stable_binding_main_effect_monomer_indices = np.asarray(
            [
                int(self.enzyme_global_indices[idx])
                for idx in range(len(self.enzyme_wids))
                if bool(self.enzyme_is_monomer[idx])
            ],
            dtype=np.int64,
        )
        self._stable_binding_main_effect_complex_indices = np.asarray(
            [
                int(self.enzyme_global_indices[idx])
                for idx in range(len(self.enzyme_wids))
                if bool(self.enzyme_is_complex[idx])
            ],
            dtype=np.int64,
        )
        stable_binding_enzyme_indices = [
            idx
            for idx in range(len(self.enzyme_wids))
            if float(self.enzyme_mean_dwell_times[idx]) != 0.0
        ]
        reachable_external_monomers: set[int] = set()
        reachable_external_complexes: set[int] = set()
        main_monomers = set(self._stable_binding_main_effect_monomer_indices.tolist())
        main_complexes = set(self._stable_binding_main_effect_complex_indices.tolist())
        for enzyme_idx in stable_binding_enzyme_indices:
            enzyme_global_idx = int(self.enzyme_global_indices[enzyme_idx])
            releasable_monomers, releasable_complexes = self._releasable_protein_indices(
                binding_monomers=(enzyme_global_idx,) if bool(self.enzyme_is_monomer[enzyme_idx]) else (),
                binding_complexes=(enzyme_global_idx,) if bool(self.enzyme_is_complex[enzyme_idx]) else (),
            )
            reachable_external_monomers.update(
                int(idx) for idx in releasable_monomers.tolist() if int(idx) not in main_monomers
            )
            reachable_external_complexes.update(
                int(idx) for idx in releasable_complexes.tolist() if int(idx) not in main_complexes
            )
        self._stable_binding_external_monomer_indices = tuple(sorted(reachable_external_monomers))
        if self._stable_binding_external_monomer_indices:
            raise NotImplementedError(
                "DNAS stable binding unexpectedly reaches external monomer side effects: "
                f"{self._stable_binding_external_monomer_indices!r}"
            )
        self._stable_binding_external_complex_indices = tuple(sorted(reachable_external_complexes))
        self._stable_binding_external_complex_wids = [
            self._complex_wid_by_global_index[int(global_index)]
            for global_index in self._stable_binding_external_complex_indices
        ]
        self._declared_protein_count_wids = list(self.protein_enzyme_wids)
        self._declared_complex_count_wids = list(
            dict.fromkeys((*self.complex_enzyme_wids, *self._stable_binding_external_complex_wids))
        )

    def _cfg(self, key: str, fixture_value: float) -> float:
        configured = self.parameters.get(key)
        if configured is None:
            return float(fixture_value)
        return float(configured)

    def _load_chromosome_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        with np.load(str(resolved), allow_pickle=False) as data:
            def _fixture_array(name: str) -> np.ndarray:
                for key in (f"fixture/{name}", f"fixture__{name}"):
                    if key in data:
                        return np.asarray(data[key], dtype=np.int64).reshape(-1)
                raise KeyError(f"Missing chromosome fixture array '{name}' in {resolved}")

            def _fixture_matrix(name: str) -> np.ndarray:
                for key in (f"fixture/{name}", f"fixture__{name}"):
                    if key in data:
                        return np.asarray(data[key], dtype=np.int64)
                raise KeyError(f"Missing chromosome fixture matrix '{name}' in {resolved}")

            self.all_monomer_dna_footprints = np.asarray(
                _fixture_array("monomerDNAFootprints"),
                dtype=np.int64,
            ).reshape(-1)
            self.all_complex_dna_footprints = np.asarray(
                _fixture_array("complexDNAFootprints"),
                dtype=np.int64,
            ).reshape(-1)
            self.all_monomer_binding_strandedness = np.asarray(
                _fixture_array("monomerDNAFootprintBindingStrandedness"),
                dtype=np.int64,
            ).reshape(-1)
            self.all_complex_binding_strandedness = np.asarray(
                _fixture_array("complexDNAFootprintBindingStrandedness"),
                dtype=np.int64,
            ).reshape(-1)
            self.all_monomer_region_strandedness = np.asarray(
                _fixture_array("monomerDNAFootprintRegionStrandedness"),
                dtype=np.int64,
            ).reshape(-1)
            self.all_complex_region_strandedness = np.asarray(
                _fixture_array("complexDNAFootprintRegionStrandedness"),
                dtype=np.int64,
            ).reshape(-1)
            self.reaction_bound_monomer = np.asarray(
                _fixture_array("reactionBoundMonomer"),
                dtype=np.int64,
            ).reshape(-1)
            self.reaction_bound_complex = np.asarray(
                _fixture_array("reactionBoundComplex"),
                dtype=np.int64,
            ).reshape(-1)
            self.reaction_monomer_catalysis_matrix = np.asarray(
                _fixture_matrix("reactionMonomerCatalysisMatrix"),
                dtype=np.int64,
            )
            self.reaction_complex_catalysis_matrix = np.asarray(
                _fixture_matrix("reactionComplexCatalysisMatrix"),
                dtype=np.int64,
            )
            self.reaction_thresholds = np.asarray(
                _fixture_array("reactionThresholds"),
                dtype=np.int64,
            ).reshape(-1)

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
        fx = mat["data"].fixture

        self.substrate_wids = _parse_wid_array(fx.substrateWholeCellModelIDs)
        self.enzyme_wids = _parse_wid_array(fx.enzymeWholeCellModelIDs)

        self.substrate_index_atp = int(_coerce_scalar(fx.substrateIndexs_atp)) - 1
        self.substrate_index_adp = int(_coerce_scalar(fx.substrateIndexs_adp)) - 1
        self.substrate_index_pi = int(_coerce_scalar(fx.substrateIndexs_phosphate)) - 1
        self.substrate_index_h2o = int(_coerce_scalar(fx.substrateIndexs_water)) - 1

        self.atp_wid = self.substrate_wids[self.substrate_index_atp]
        self.adp_wid = self.substrate_wids[self.substrate_index_adp]
        self.pi_wid = self.substrate_wids[self.substrate_index_pi]
        self.h2o_wid = self.substrate_wids[self.substrate_index_h2o]

        gyrase_idx = int(_coerce_scalar(fx.enzymeIndexs_gyrase)) - 1
        topoiv_idx = int(_coerce_scalar(fx.enzymeIndexs_topoIV)) - 1
        topoi_idx = int(_coerce_scalar(fx.enzymeIndexs_topoI)) - 1
        self.gyrase_idx = gyrase_idx
        self.topoiv_idx = topoiv_idx
        self.topoi_idx = topoi_idx
        self.gyrase_wid = self.enzyme_wids[gyrase_idx]
        self.topoiv_wid = self.enzyme_wids[topoiv_idx]
        self.topoi_wid = self.enzyme_wids[topoi_idx]
        self.h_wid = "H" if "H" in self.substrate_wids else None
        self.enzyme_global_indices = np.asarray(fx.enzymeGlobalIndexs, dtype=np.int64).reshape(-1)
        self.enzyme_dna_footprints = np.asarray(fx.enzymeDNAFootprints, dtype=np.int64).reshape(-1)
        self.enzyme_dna_footprints_3prime = np.asarray(
            fx.enzymeDNAFootprints3Prime,
            dtype=np.int64,
        ).reshape(-1)
        self.enzyme_dna_footprints_5prime = np.asarray(
            fx.enzymeDNAFootprints5Prime,
            dtype=np.int64,
        ).reshape(-1)
        monomer_local_indices = np.asarray(
            getattr(fx, "enzymeMonomerLocalIndexs", np.array([], dtype=np.int64)),
            dtype=np.int64,
        ).reshape(-1)
        complex_local_indices = np.asarray(
            getattr(fx, "enzymeComplexLocalIndexs", np.array([], dtype=np.int64)),
            dtype=np.int64,
        ).reshape(-1)
        self.enzyme_is_monomer = np.zeros(len(self.enzyme_wids), dtype=bool)
        if monomer_local_indices.size:
            self.enzyme_is_monomer[np.asarray(monomer_local_indices - 1, dtype=np.int64)] = True
        self.enzyme_is_complex = np.zeros(len(self.enzyme_wids), dtype=bool)
        if complex_local_indices.size:
            self.enzyme_is_complex[np.asarray(complex_local_indices - 1, dtype=np.int64)] = True
        enz_seed = np.asarray(fx.enzymes, dtype=float).reshape(-1)
        bnd_seed = np.asarray(
            getattr(fx, "boundEnzymes", np.zeros_like(enz_seed)),
            dtype=float,
        ).reshape(-1)
        self.total_enzyme_seed = {
            wid: float(enz_seed[i] + bnd_seed[i]) for i, wid in enumerate(self.enzyme_wids)
        }

        self.gyrase_activity_rate = self._cfg("gyrase_activity_rate", float(fx.gyraseActivityRate))
        self.topoi_activity_rate = self._cfg("topoi_activity_rate", float(fx.topoIActivityRate))
        self.topoiv_activity_rate = self._cfg("topoiv_activity_rate", float(fx.topoIVActivityRate))
        self.gyrase_mean_dwell_time = float(fx.gyraseMeanDwellTime)

        self.gyrase_logistic_const = self._cfg(
            "gyrase_logistic_const", float(fx.gyrLogisiticConst)
        )
        self.topoi_logistic_const = self._cfg(
            "topoi_logistic_const", float(fx.topoILogisiticConst)
        )
        self.topoiv_logistic_const = self._cfg(
            "topoiv_logistic_const",
            float(getattr(fx, "topoIVLogisiticConst", 0.0)),
        )

        self.gyrase_sigma_limit = self._cfg("gyrase_sigma_limit", float(fx.gyraseSigmaLimit))
        self.topoi_sigma_limit = self._cfg("topoi_sigma_limit", float(fx.topoISigmaLimit))
        self.topoiv_sigma_limit = self._cfg("topoiv_sigma_limit", float(fx.topoIVSigmaLimit))

        self.gyrase_atp_cost = self._cfg("gyrase_atp_cost", float(fx.gyraseATPCost))
        self.topoi_atp_cost = self._cfg("topoi_atp_cost", float(fx.topoIATPCost))
        self.topoiv_atp_cost = self._cfg("topoiv_atp_cost", float(fx.topoIVATPCost))
        self.enzyme_sigma_limits = np.zeros(len(self.enzyme_wids), dtype=np.float64)
        self.enzyme_sigma_limits[self.gyrase_idx] = float(self.gyrase_sigma_limit)
        self.enzyme_sigma_limits[self.topoiv_idx] = float(self.topoiv_sigma_limit)
        self.enzyme_sigma_limits[self.topoi_idx] = float(self.topoi_sigma_limit)
        self.enzyme_activity_rates = np.zeros(len(self.enzyme_wids), dtype=np.float64)
        self.enzyme_activity_rates[self.gyrase_idx] = float(self.gyrase_activity_rate)
        self.enzyme_activity_rates[self.topoiv_idx] = float(self.topoiv_activity_rate)
        self.enzyme_activity_rates[self.topoi_idx] = float(self.topoi_activity_rate)
        self.enzyme_atp_costs = np.zeros(len(self.enzyme_wids), dtype=np.float64)
        self.enzyme_atp_costs[self.gyrase_idx] = float(self.gyrase_atp_cost)
        self.enzyme_atp_costs[self.topoiv_idx] = float(self.topoiv_atp_cost)
        self.enzyme_atp_costs[self.topoi_idx] = float(self.topoi_atp_cost)
        self.enzyme_delta_lks = np.zeros(len(self.enzyme_wids), dtype=np.float64)
        self.enzyme_delta_lks[self.gyrase_idx] = float(self.parameters["gyrase_link_delta"])
        self.enzyme_delta_lks[self.topoiv_idx] = float(self.parameters["topoiv_link_delta"])
        self.enzyme_delta_lks[self.topoi_idx] = float(self.parameters["topoi_link_delta"])
        self.enzyme_mean_dwell_times = np.full(len(self.enzyme_wids), np.nan, dtype=np.float64)
        self.enzyme_mean_dwell_times[self.gyrase_idx] = float(self.gyrase_mean_dwell_time)
        self.enzyme_mean_dwell_times[self.topoi_idx] = 0.0

        self.equilibrium_sigma = self._load_equilibrium_sigma(
            fx,
            fallback=float(self.parameters["equilibrium_supercoil_density"]),
        )

        self.fold_change_slopes = np.asarray(
            getattr(fx, "foldChangeSlopes", np.array([], dtype=np.float64)),
            dtype=np.float64,
        ).reshape(-1)
        self.fold_change_intercepts = np.asarray(
            getattr(fx, "foldChangeIntercepts", np.array([], dtype=np.float64)),
            dtype=np.float64,
        ).reshape(-1)
        self.fold_change_lower_sigma_limit = float(
            getattr(fx, "foldChangeLowerSigmaLimit", self.parameters["supercoil_density_min"])
        )
        self.fold_change_upper_sigma_limit = float(
            getattr(fx, "foldChangeUpperSigmaLimit", self.parameters["supercoil_density_max"])
        )
        self.num_transcription_units = int(
            _coerce_scalar(getattr(fx, "numTranscriptionUnits", 0))
        )
        self.fold_change_tu_indices = np.asarray(
            getattr(fx, "tuIndexs", np.array([], dtype=np.int64)),
            dtype=np.int64,
        ).reshape(-1)
        self.fold_change_tu_coordinates = np.asarray(
            getattr(fx, "tuCoordinates", np.array([], dtype=np.int64)),
            dtype=np.int64,
        ).reshape(-1)
        fold_change_size = min(
            int(self.fold_change_slopes.size),
            int(self.fold_change_intercepts.size),
            int(self.fold_change_tu_indices.size),
            int(self.fold_change_tu_coordinates.size),
        )
        self.fold_change_slopes = self.fold_change_slopes[:fold_change_size]
        self.fold_change_intercepts = self.fold_change_intercepts[:fold_change_size]
        self.fold_change_tu_indices = self.fold_change_tu_indices[:fold_change_size] - 1
        self.fold_change_tu_coordinates = self.fold_change_tu_coordinates[:fold_change_size]
        self.supercoiling_tu_wids = tuple(
            f"TU_{tu_index + 1:03d}"
            for tu_index in self.fold_change_tu_indices.tolist()
            if 0 <= int(tu_index) < self.num_transcription_units
        )

    def _load_equilibrium_sigma(self, fixture: object, fallback: float) -> float:
        states = np.asarray(getattr(fixture, "states", []), dtype=object).ravel()
        for state in states:
            if getattr(state, "x_class_", "") != "edu.stanford.covert.cell.sim.state.Chromosome":
                continue
            if hasattr(state, "equilibriumSuperhelicalDensity"):
                return float(state.equilibriumSuperhelicalDensity)
        return float(fallback)

    def build_default_chromosome_state(
        self,
        *,
        sigma: float | None = None,
        replication_state: str = "idle",
    ) -> dict[str, Any]:
        sigma_value = self.equilibrium_sigma if sigma is None else float(sigma)
        store = ChromosomeStore(shape=self.chromosome_shape)
        polymerized = SparseTriplet(
            positions=np.array([0, 0], dtype=np.int64),
            strands=np.array([0, 1], dtype=np.int8),
            values=np.array([self.chromosome_length, self.chromosome_length], dtype=np.int32),
            shape=self.chromosome_shape,
        )
        store.set_field("polymerizedRegions", polymerized)
        positive_regions = self._positive_ds_regions(polymerized)
        positive_values = np.asarray(
            [
                int(round((length / float(self.parameters["bp_per_turn"])) * (1.0 + sigma_value)))
                for _, _, length in positive_regions
            ],
            dtype=np.int32,
        )
        store.set_field(
            "linkingNumbers",
            self._build_linking_numbers_triplet(positive_regions, positive_values),
        )
        state = store.to_state()
        state["replication_state"] = replication_state
        state["supercoil_density"] = float(sigma_value)
        state["supercoiled"] = bool(sigma_value < 0.0)
        return state

    def _preserve_default_chromosome_scalars(
        self,
        chromosome_state: dict[str, Any],
        *,
        replication_state: str,
        sigma_value: float,
    ) -> dict[str, Any]:
        chromosome_state["replication_state"] = replication_state
        chromosome_state["supercoil_density"] = float(sigma_value)
        chromosome_state["supercoiled"] = bool(sigma_value < 0.0)
        return chromosome_state

    def _initialize_default_gyrase_binding(
        self,
        *,
        chromosome_state: dict[str, Any],
        available_gyrase: float,
    ) -> tuple[dict[str, Any], float]:
        replication_state = str(chromosome_state.get("replication_state", "idle"))
        sigma_value = _to_finite(
            float(chromosome_state.get("supercoil_density", self.equilibrium_sigma)),
            fallback=self.equilibrium_sigma,
        )
        store = ChromosomeStore.from_state_mapping(chromosome_state, shape=self.chromosome_shape)
        polymerized = self._ensure_polymerized_regions(store.get_field("polymerizedRegions"))
        positive_regions = self._positive_regions_from_store(store=store, polymerized=polymerized)

        if not positive_regions or available_gyrase <= 0.0:
            return self._preserve_default_chromosome_scalars(
                store.to_state(),
                replication_state=replication_state,
                sigma_value=sigma_value,
            ), 0.0

        expected_binding = float(available_gyrase) * (
            1.0
            - 1.0 / float(self.gyrase_mean_dwell_time) / float(self.parameters["time_step"])
        )
        n_gyrase_binding = self._stochastic_round(expected_binding)
        if n_gyrase_binding <= 0:
            return self._preserve_default_chromosome_scalars(
                store.to_state(),
                replication_state=replication_state,
                sigma_value=sigma_value,
            ), 0.0

        store, binding_result = self._bind_protein_to_chromosome_stochastically(
            store=store,
            enzyme_idx=self.gyrase_idx,
            available_count=float(n_gyrase_binding),
            positive_regions=positive_regions,
        )
        return self._preserve_default_chromosome_scalars(
            store.to_state(),
            replication_state=replication_state,
            sigma_value=sigma_value,
        ), float(binding_result.n_bound)

    def build_default_initialized_state(
        self,
        *,
        sigma: float | None = None,
        replication_state: str = "idle",
        available_gyrase: float | None = None,
    ) -> dict[str, Any]:
        chromosome_state = self.build_default_chromosome_state(
            sigma=sigma,
            replication_state=replication_state,
        )
        if available_gyrase is None:
            available_gyrase = float(self.total_enzyme_seed.get(self.gyrase_wid, 0.0))
        chromosome_state, gyrase_bound = self._initialize_default_gyrase_binding(
            chromosome_state=chromosome_state,
            available_gyrase=float(available_gyrase),
        )
        bound_enzymes = {wid: 0.0 for wid in self.enzyme_wids}
        bound_enzymes[self.gyrase_wid] = float(gyrase_bound)
        return {
            "chromosome": chromosome_state,
            "boundEnzymes": bound_enzymes,
            "free_gyrase_count": max(0.0, float(available_gyrase) - float(gyrase_bound)),
        }

    def ports_schema(self) -> dict[str, Any]:
        chromosome_schema = {
            field: sparse_triplet_schema(self.chromosome_shape, emit=(field in {"linkingNumbers", "polymerizedRegions"}))
            for field in CHROMOSOME_FIELDS
        }
        chromosome_schema.update(
            {
                "supercoil_density": {
                    "_default": float(self.equilibrium_sigma),
                    "_updater": "set",
                    "_emit": True,
                },
                "replication_state": {
                    "_default": "idle",
                    "_updater": "set",
                    "_emit": True,
                },
                "supercoiled": {
                    "_default": True,
                    "_updater": "set",
                    "_emit": False,
                },
            }
        )

        schema: dict[str, Any] = {
            "chromosome": chromosome_schema,
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                for wid in self.substrate_wids
            },
            "enzymes": {
                wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                for wid in self.enzyme_wids
            },
            "boundEnzymes": {
                wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                for wid in self.enzyme_wids
            },
            "requests": {
                self.name: {
                    self.atp_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                    self.h2o_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                }
            },
            "substrates_allocated": {
                self.name: {
                    self.atp_wid: {"_default": 0.0, "_emit": False},
                    self.h2o_wid: {"_default": 0.0, "_emit": False},
                }
            },
        }
        if self.protein_enzyme_wids:
            schema["protein"] = {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self._declared_protein_count_wids
                }
            }
        if self._declared_complex_count_wids:
            schema["complex"] = {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self._declared_complex_count_wids
                }
            }
        if self.supercoiling_tu_wids:
            schema["tx_rate_fold_change"] = {
                tu_wid: {"_default": 1.0, "_updater": "set", "_emit": True}
                for tu_wid in self.supercoiling_tu_wids
            }
        return schema

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])
        gyrase_idx = int(self.gyrase_idx)
        topoiv_idx = int(self.topoiv_idx)
        topoi_idx = int(self.topoi_idx)

        chrom_state = states.get("chromosome", {})
        chrom_store = self._resolve_chromosome_store(chrom_state)
        polymerized = self._ensure_polymerized_regions(chrom_store.get_field("polymerizedRegions"))
        positive_regions = self._positive_regions_from_store(
            store=chrom_store,
            polymerized=polymerized,
        )

        sigma_fallback = _to_finite(
            float(chrom_state.get("supercoil_density", self.equilibrium_sigma)),
            fallback=self.equilibrium_sigma,
        )
        linking_numbers = chrom_store.get_field("linkingNumbers")
        # Compute the per-region sigma (legality-gating input) FIRST, then
        # use it as the writeback baseline's per-region fallback below --
        # NOT a separate global scalar. Root cause: for a region with no
        # explicit linkingNumbers entry (e.g. a nascent post-replication
        # region far from equilibrium), _positive_region_sigmas_from_store
        # already correctly sources its real density from the
        # superhelicalDensity input oracle when the ledger covers it, but
        # _align_positive_region_values previously always fell back to the
        # single global equilibrium-ish `sigma_fallback` for the BASE
        # linking value that activity deltas get added to -- silently
        # assuming a torsionally-relaxed baseline for a region the
        # legality gate had just correctly identified as far from relaxed
        # (e.g. sigma ~ -1.0, not ~0.0). That mismatch let OC treat a
        # region as both "legal for topoI to act on" (real sigma) and
        # "starting from the relaxed linking number" (wrong sigma) in the
        # same tick, producing spurious linkingNumbers activity real MATLAB
        # never has (root-caused via seed 46 tick 24, the earliest
        # remaining clustered-seed divergence after the process-RNG ledger
        # closed the RNG-sequence hypothesis).
        sigma_values = self._positive_region_sigmas_from_store(
            store=chrom_store,
            positive_regions=positive_regions,
            linking_numbers=linking_numbers,
            fallback_sigma=sigma_fallback,
        )
        positive_values = self._align_positive_region_values(
            positive_regions=positive_regions,
            linking_numbers=linking_numbers,
            fallback_sigma=sigma_values,
        )
        sigma = self._weighted_sigma(positive_regions=positive_regions, sigma_values=sigma_values)
        replication_state = str(chrom_state.get("replication_state", "idle"))

        protein_counts = states.get("protein", {}).get("counts", {})
        complex_counts = states.get("complex", {}).get("counts", {})
        top_level_enzymes = states.get("enzymes", {})
        gyrase_free_count = self._resolve_enzyme_count(
            self.gyrase_wid,
            protein_counts=protein_counts,
            complex_counts=complex_counts,
            top_level_enzymes=top_level_enzymes,
        )
        topoiv_free_count = self._resolve_enzyme_count(
            self.topoiv_wid,
            protein_counts=protein_counts,
            complex_counts=complex_counts,
            top_level_enzymes=top_level_enzymes,
        )
        topoi_free_count = self._resolve_enzyme_count(
            self.topoi_wid,
            protein_counts=protein_counts,
            complex_counts=complex_counts,
            top_level_enzymes=top_level_enzymes,
        )
        bound_now_raw = states.get("boundEnzymes", {})
        bound_now = bound_now_raw if isinstance(bound_now_raw, dict) else {}
        hint = states.get("trace_hint", {})
        hint = hint if isinstance(hint, dict) else {}
        bound_next_raw = hint.get("boundEnzymes_next", {})
        bound_next = bound_next_raw if isinstance(bound_next_raw, dict) else {}
        replay_mode = bool(bound_next or hint.get("chromosome_next"))
        enzymes_now_raw = states.get("enzymes", {})
        enzymes_now = enzymes_now_raw if isinstance(enzymes_now_raw, dict) else {}
        enzymes_next_raw = hint.get("enzymes_next", {})
        enzymes_next = enzymes_next_raw if isinstance(enzymes_next_raw, dict) else {}
        complex_bound_before = chrom_store.get_field("complexBoundSites")
        monomer_bound_before = chrom_store.get_field("monomerBoundSites")

        if replay_mode and not self._replay_rng_aligned:
            warmup = int(self._replay_rng_warmup_draws)
            if warmup > 0:
                self._rng.random(warmup)
            self._replay_rng_aligned = True

        gyrase_bound = max(0.0, float((bound_next or bound_now).get(self.gyrase_wid, 0.0)))
        topoiv_bound = max(0.0, float((bound_next or bound_now).get(self.topoiv_wid, 0.0)))
        gyrase_free_effective = max(0.0, float(gyrase_free_count))
        topoiv_free_effective = max(0.0, float(topoiv_free_count))
        nohint_bound_next_effective: dict[str, float] = {}
        nohint_enzymes_next_effective: dict[str, float] = {}
        protein_side_effect_deltas: dict[str, float] = {}
        complex_side_effect_deltas: dict[str, float] = {}
        legal = np.zeros((len(positive_regions), len(self.enzyme_wids)), dtype=bool)
        if sigma_values.size:
            legal[:, gyrase_idx] = sigma_values > self.gyrase_sigma_limit
            legal[:, topoiv_idx] = sigma_values > self.topoiv_sigma_limit
            legal[:, topoi_idx] = sigma_values < self.topoi_sigma_limit
        topoi_transient = np.zeros(len(positive_regions), dtype=np.float64)
        if not replay_mode:
            gyrase_legal = bool(np.any(legal[:, gyrase_idx]))
            topoiv_legal = bool(np.any(legal[:, topoiv_idx]))

            topoiv_protected_regions = [
                positive_regions[idx]
                for idx in np.flatnonzero(legal[:, topoiv_idx]).tolist()
            ]
            chrom_store, topoiv_release = self._release_bound_enzyme_from_chromosome(
                store=chrom_store,
                enzyme_idx=topoiv_idx,
                release_rate=float("inf"),
                dt=dt,
                protected_regions=topoiv_protected_regions,
            )
            if topoiv_release == 0 and not topoiv_legal:
                topoiv_release = topoiv_bound
            topoiv_bound = max(0.0, topoiv_bound - topoiv_release)
            topoiv_free_effective = max(0.0, topoiv_free_effective + topoiv_release)
            chrom_store, gyrase_release = self._release_bound_enzyme_from_chromosome(
                store=chrom_store,
                enzyme_idx=gyrase_idx,
                release_rate=1.0 / max(1.0, float(getattr(self, "gyrase_mean_dwell_time", 1.0))),
                dt=dt,
                protected_regions=[],
            )
            gyrase_bound = max(0.0, gyrase_bound - gyrase_release)
            gyrase_free_effective = max(0.0, gyrase_free_effective + gyrase_release)

            free_counts = {
                gyrase_idx: float(gyrase_free_effective),
                topoiv_idx: float(topoiv_free_effective),
                topoi_idx: float(topoi_free_count),
            }
            bound_counts = {
                gyrase_idx: float(gyrase_bound),
                topoiv_idx: float(topoiv_bound),
                topoi_idx: float(bound_now.get(self.topoi_wid, 0.0)),
            }
            for enzyme_idx in self._draw_permutation(len(self.enzyme_wids)).tolist():
                if float(self.enzyme_mean_dwell_times[enzyme_idx]) == 0.0:
                    topoi_transient = self._calculate_transient_binding(
                        store=chrom_store,
                        enzyme_idx=enzyme_idx,
                        positive_regions=positive_regions,
                        legal_mask=legal[:, enzyme_idx],
                        available_count=free_counts.get(enzyme_idx, 0.0),
                    )
                    continue
                legal_idxs = np.flatnonzero(legal[:, enzyme_idx]).tolist()
                if not legal_idxs:
                    continue
                chrom_store, binding_result = self._bind_protein_to_chromosome_stochastically(
                    store=chrom_store,
                    enzyme_idx=enzyme_idx,
                    available_count=free_counts.get(enzyme_idx, 0.0),
                    positive_regions=[positive_regions[idx] for idx in legal_idxs],
                )
                if binding_result.n_bound <= 0:
                    continue
                self._apply_binding_result(
                    binding_result=binding_result,
                    free_counts=free_counts,
                    bound_counts=bound_counts,
                    protein_side_effect_deltas=protein_side_effect_deltas,
                    complex_side_effect_deltas=complex_side_effect_deltas,
                )

            gyrase_bound = float(bound_counts.get(gyrase_idx, gyrase_bound))
            topoiv_bound = float(bound_counts.get(topoiv_idx, topoiv_bound))
            gyrase_free_effective = float(free_counts.get(gyrase_idx, gyrase_free_effective))
            topoiv_free_effective = float(free_counts.get(topoiv_idx, topoiv_free_effective))

            nohint_bound_next_effective = {
                self.gyrase_wid: float(gyrase_bound),
                self.topoiv_wid: float(topoiv_bound),
                self.topoi_wid: float(bound_now.get(self.topoi_wid, 0.0)),
            }
            nohint_enzymes_next_effective = {
                self.gyrase_wid: float(gyrase_free_effective),
                self.topoiv_wid: float(topoiv_free_effective),
                self.topoi_wid: float(topoi_free_count),
            }
        else:
            topoi_transient = self._calculate_transient_binding(
                store=chrom_store,
                enzyme_idx=topoi_idx,
                positive_regions=positive_regions,
                legal_mask=legal[:, topoi_idx],
                available_count=topoi_free_count,
            )

        gyrase_catalytic = gyrase_bound if gyrase_bound > 0.0 else gyrase_free_effective
        topoiv_catalytic = topoiv_bound if topoiv_bound > 0.0 else topoiv_free_effective

        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        available_atp = self._allocated_or_state(allocated_state, self.atp_wid)
        available_h2o = self._allocated_or_state(allocated_state, self.h2o_wid)

        replication_region_idx = self._replication_region_index(positive_regions)
        replication_delta = np.zeros(len(positive_regions), dtype=np.int32)
        rep_load_events = self._replication_supercoil_load_events(replication_state, dt)
        if replication_region_idx is not None and rep_load_events > 0:
            replication_delta[replication_region_idx] = int(rep_load_events)
        activity_events, atp_used = self._sample_activity_events_by_region(
            store=chrom_store,
            positive_regions=positive_regions,
            sigma_values=sigma_values,
            legal=legal,
            topoi_transient=topoi_transient,
            available_atp=available_atp,
            available_h2o=available_h2o,
            dt=dt,
        )
        gyrase_events = activity_events[:, gyrase_idx]
        topoiv_events = activity_events[:, topoiv_idx]
        topoi_events = activity_events[:, topoi_idx]

        link_delta = (
            replication_delta
            + gyrase_events * int(round(float(self.parameters["gyrase_link_delta"])))
            + topoiv_events * int(round(float(self.parameters["topoiv_link_delta"])))
            + topoi_events * int(round(float(self.parameters["topoi_link_delta"])))
        )
        # MATLAB updates integer linking numbers directly and writes them back
        # unchanged via CircularSparseMat; it does not clamp per-region sigma
        # into an artificial [-0.2, 0.2] box before the writeback.
        linking_next_positive = (
            positive_values.astype(np.int64) + link_delta.astype(np.int64)
        ).astype(np.int32)
        linking_next = self._build_linking_numbers_triplet(positive_regions, linking_next_positive)

        chromosome_hint = hint.get("chromosome_next")
        if isinstance(chromosome_hint, dict):
            next_hint = chromosome_hint.get("linkingNumbers")
            if isinstance(next_hint, dict):
                linking_next = SparseTriplet.from_state(next_hint, shape=self.chromosome_shape)

        linking_next_values = self._align_positive_region_values(
            positive_regions=positive_regions,
            linking_numbers=linking_next,
            fallback_sigma=self.equilibrium_sigma,
        )
        sigma_next = self._weighted_sigma(
            positive_regions=positive_regions,
            sigma_values=self._region_sigmas(
                positive_regions=positive_regions,
                linking_values=linking_next_values,
            ),
        )
        tx_rate_fold_change = self.calc_rna_polymerase_binding_prob_fold_change(
            positive_regions=positive_regions,
            linking_values=linking_next_values,
        )

        request_need = self._atp_request(
            sigma=float(sigma),
            replication_state=replication_state,
            gyrase_count=gyrase_catalytic,
            topoiv_count=topoiv_catalytic,
            dt=dt,
        )
        update: dict[str, Any] = {
            "chromosome": {
                "linkingNumbers": linking_next.to_state(),
                "supercoil_density": float(sigma_next),
                "supercoiled": bool(sigma_next < 0.0),
            },
            "requests": {
                self.name: {
                    self.atp_wid: request_need,
                    self.h2o_wid: request_need,
                }
            },
            "tx_rate_fold_change": tx_rate_fold_change,
        }
        if not self._triplets_equal(complex_bound_before, chrom_store.get_field("complexBoundSites")):
            update["chromosome"]["complexBoundSites"] = chrom_store.get_field(
                "complexBoundSites"
            ).to_state()
        if not self._triplets_equal(monomer_bound_before, chrom_store.get_field("monomerBoundSites")):
            update["chromosome"]["monomerBoundSites"] = chrom_store.get_field(
                "monomerBoundSites"
            ).to_state()

        substrates_now_raw = states.get("substrates", {})
        substrates_now = substrates_now_raw if isinstance(substrates_now_raw, dict) else {}
        substrate_delta_out: dict[str, float] = {
            wid: float(delta)
            for wid, delta in self._substrate_delta(atp_used).items()
            if float(delta) != 0.0
        }

        substrates_next_raw = hint.get("substrates_next", {})
        substrates_next = substrates_next_raw if isinstance(substrates_next_raw, dict) else {}
        if substrates_next:
            for wid, after_raw in substrates_next.items():
                if wid not in self.substrate_wids:
                    continue
                now = float(substrates_now.get(wid, 0.0))
                delta = float(after_raw) - now
                if delta != 0.0:
                    substrate_delta_out[wid] = float(delta)
                elif wid in substrate_delta_out:
                    del substrate_delta_out[wid]
        if protein_side_effect_deltas:
            update["protein"] = {
                "counts": {
                    wid: float(delta)
                    for wid, delta in protein_side_effect_deltas.items()
                    if float(delta) != 0.0
                }
            }
        if complex_side_effect_deltas:
            update["complex"] = {
                "counts": {
                    wid: float(delta)
                    for wid, delta in complex_side_effect_deltas.items()
                    if float(delta) != 0.0
                }
            }

        bound_next_effective = {wid: float(bound_now.get(wid, 0.0)) for wid in self.enzyme_wids}
        enzymes_next_effective = {wid: float(enzymes_now.get(wid, 0.0)) for wid in self.enzyme_wids}
        if replay_mode:
            for wid in self.enzyme_wids:
                bound_next_effective[wid] = float(bound_next.get(wid, bound_now.get(wid, 0.0)))
                enzymes_next_effective[wid] = float(enzymes_next.get(wid, enzymes_now.get(wid, 0.0)))
        else:
            for wid in self.enzyme_wids:
                bound_next_effective[wid] = float(
                    nohint_bound_next_effective.get(wid, bound_now.get(wid, 0.0))
                )
                enzymes_next_effective[wid] = float(
                    nohint_enzymes_next_effective.get(
                        wid,
                        self._resolve_enzyme_count(
                            wid,
                            protein_counts=protein_counts,
                            complex_counts=complex_counts,
                            top_level_enzymes=top_level_enzymes,
                        ),
                    )
                )

        update["substrates"] = substrate_delta_out

        bound_delta_out: dict[str, float] = {}
        enzyme_delta_out: dict[str, float] = {}
        for wid in self.enzyme_wids:
            bound_delta = float(bound_next_effective.get(wid, 0.0)) - float(bound_now.get(wid, 0.0))
            if bound_delta != 0.0:
                bound_delta_out[wid] = float(bound_delta)
            enzyme_delta = float(enzymes_next_effective.get(wid, 0.0)) - float(enzymes_now.get(wid, 0.0))
            if enzyme_delta != 0.0:
                enzyme_delta_out[wid] = float(enzyme_delta)
        update["boundEnzymes"] = bound_delta_out
        update["enzymes"] = enzyme_delta_out

        self._tick_index += 1
        return update

    def _resolve_chromosome_store(self, chrom_state: dict[str, Any]) -> ChromosomeStore:
        store = ChromosomeStore.from_state_mapping(chrom_state, shape=self.chromosome_shape)
        if store.calc_num_edges("polymerizedRegions") == 0 and store.calc_num_edges("linkingNumbers") == 0:
            default_state = self.build_default_chromosome_state(
                sigma=float(chrom_state.get("supercoil_density", self.equilibrium_sigma)),
                replication_state=str(chrom_state.get("replication_state", "idle")),
            )
            store = ChromosomeStore.from_state_mapping(default_state, shape=self.chromosome_shape)
        self._apply_superhelical_density_ledger(store)
        return store

    def _apply_superhelical_density_ledger(self, store: ChromosomeStore) -> None:
        """Inject the superhelical-density ledger's sigma oracle, if any.

        No-op if the caller already supplied a ``superhelicalDensity``
        hidden field (respects explicit caller intent) or if no ledger is
        loaded / it has no entry for this tick.
        """
        if store.has_hidden_sparse_field("superhelicalDensity"):
            return
        ledger = self._superhelical_density_ledger
        if ledger is None or not ledger.has_tick(self._tick_index):
            return
        hidden_field = ledger.hidden_field_for_tick(self._tick_index, store.shape)
        store.set_hidden_sparse_field("superhelicalDensity", hidden_field)

    def _rng_stream_signature(self, rng: Any) -> tuple[str, str]:
        base = getattr(rng, "base", rng)
        if isinstance(base, np.random.Generator):
            return ("numpy.random.Generator", type(base.bit_generator).__qualname__)
        rng_cls = type(base)
        return (str(rng_cls.__module__), str(rng_cls.__qualname__))

    def _seeded_rng_like(self, rng: Any) -> Any | None:
        base = getattr(rng, "base", rng)
        if isinstance(base, np.random.Generator):
            return np.random.default_rng(self._rng_seed)
        try:
            return type(base)(self._rng_seed)
        except TypeError:
            return None

    def _load_chromosome_release_ledger(self) -> ChromosomeReleaseLedger | None:
        """Load the (optional) MATLAB chromosome-owned release RNG ledger.

        This is an input oracle: it supplies the exact uniform draws MATLAB's
        ``chromosome.randStream`` produced for the gyrase-release consumption
        in ``DNASupercoiling`` (see
        ``scripts/matlab/l22_dnas_chromosome_release_rng_ledger.m``). When
        present, it fully replaces the Monte-Carlo
        ``chromosome_release_rng_warmup_draws`` approximation for this
        process instance. Missing ledgers are not an error: callers that
        never supply/generate one (e.g. most existing tests) keep the prior
        approximate behavior unchanged.

        A ledger is only a valid input oracle for a process instance driven
        by the *real* MATLAB-derived state sequence for that seed (the
        production/gate harness path). Unit tests that fabricate synthetic
        ``complexBoundSites``/substrate counts for a small seed (e.g. seed
        11, 13, ...) do not reproduce what MATLAB actually saw at that
        seed's ticks, so a same-numbered ledger's recorded draw count would
        not match and would raise loudly (by design -- see
        ``ChromosomeReleaseReplayRng``) rather than silently misapply. Such
        callers must pass ``chromosome_release_rng_ledger_path=False``
        (literal ``False``, distinct from the default-resolution ``None``)
        to explicitly opt out of ledger lookup regardless of what seed they
        use, since the reserved seed range for real ledgers is 0-199 (the
        frozen ``N=200`` gate corpus) and small test seeds otherwise collide
        with it.
        """
        configured = self.parameters.get("chromosome_release_rng_ledger_path")
        if configured is False:
            return None
        if configured is not None:
            path = Path(configured)
        else:
            path = default_ledger_path(self._rng_seed)
        if not path.exists():
            return None
        return ChromosomeReleaseLedger.load(path)

    def _load_superhelical_density_ledger(self) -> SuperhelicalDensityLedger | None:
        """Load the (optional) MATLAB superhelical-density (sigma) ledger.

        This is an input oracle: it supplies the exact double-precision
        sigma value MATLAB computed for every positive dsDNA region (see
        ``opencell.vivarium.dnas_superhelical_density_ledger`` for the full
        rationale -- it closes an int32-``linkingNumbers``-rounding source
        gap in the canonical trace). When present for this process's seed
        and tick, it is injected as the ``ChromosomeStore``'s
        ``superhelicalDensity`` hidden sparse field, which
        ``_positive_region_sigmas_from_store`` already checks FIRST (that
        mechanism predates this ledger; it was simply unpopulated for this
        wave). Missing ledgers are not an error -- callers that never
        generate one keep the prior lossy-reconstruction behavior
        unchanged.

        Mirrors ``_load_chromosome_release_ledger``'s opt-out convention: a
        caller passing ``superhelical_density_ledger_path=False`` (literal
        ``False``) disables ledger lookup regardless of seed, since the
        reserved seed range for real ledgers is 0-199 (the frozen N=200
        gate corpus) and small synthetic test seeds otherwise collide with
        it.
        """
        configured = self.parameters.get("superhelical_density_ledger_path")
        if configured is False:
            return None
        if configured is not None:
            path = Path(configured)
        else:
            path = default_superhelical_density_ledger_path(self._rng_seed)
        if not path.exists():
            return None
        return SuperhelicalDensityLedger.load(path)

    def _load_process_rng_ledger(self) -> ProcessRngLedger | None:
        """Load the (optional) MATLAB DNASupercoiling process-owned RNG ledger.

        This is an input oracle: it supplies real MATLAB draws for the
        process-owned ``this.randStream`` (private to the DNASupercoiling
        process, distinct from the shared ``chromosome.randStream``),
        generated by seeding a throwaway MATLAB stream directly to the
        exact ``process_state_before`` captured for this tick and drawing
        a generously-sized batch (NOT a reimplementation of mcg16807's
        internal formula, and NOT a fixed "exactly enough for one
        historical run" list -- see ``dnas_process_rng_ledger`` module
        docstring for the full state-seeded design rationale and the two
        empirically-verified transformations, ``randperm`` -> raw draws +
        ascending argsort and weighted ``randsample`` -> one raw draw +
        cumulative-weight lookup, ``ProcessRngReplayRng`` applies). When
        present for this process's seed and tick, it fully replaces the
        disconnected ``np.random.default_rng`` proxy stream for every call
        site this ledger covers
        (``_draw_random``/``_draw_permutation``/``_draw_choice``). Missing
        ledgers are not an error: callers that never supply/generate one
        keep the prior approximate proxy-stream behavior unchanged.

        Mirrors ``_load_chromosome_release_ledger``'s opt-out convention: a
        caller passing ``process_rng_ledger_path=False`` (literal
        ``False``) disables ledger lookup regardless of seed, since the
        reserved seed range for real ledgers is 0-199 (the frozen N=200
        gate corpus) and small synthetic test seeds otherwise collide with
        it.
        """
        configured = self.parameters.get("process_rng_ledger_path")
        if configured is False:
            return None
        if configured is not None:
            path = Path(configured)
        else:
            path = default_process_rng_ledger_path(self._rng_seed)
        if not path.exists():
            return None
        return ProcessRngLedger.load(path)

    def _process_rng_replay_for_tick(self) -> ProcessRngReplayRng | None:
        ledger = self._process_rng_ledger
        if ledger is None or not ledger.has_tick(self._tick_index):
            return None
        cached = self._process_rng_replay_cache
        if cached is not None and cached[0] == self._tick_index:
            return cached[1]
        entry = ledger.entry_for_tick(self._tick_index)
        replay = ProcessRngReplayRng(entry.draws, recorded_len=entry.recorded_len)
        self._process_rng_replay_cache = (self._tick_index, replay)
        return replay

    def _draw_random(self, size: int | None = None) -> np.ndarray | float:
        """Dispatch a ``this.randStream.rand``-equivalent draw.

        Routes through the process-RNG ledger (input oracle) for
        ledger-covered ticks; falls back to the process's own approximate
        ``self._rng`` proxy stream otherwise (unchanged prior behavior).
        """
        replay = self._process_rng_replay_for_tick()
        if replay is not None:
            return replay.random(size)
        return self._rng.random(size) if size is not None else self._rng.random()

    def _draw_permutation(self, n: int) -> np.ndarray:
        """Dispatch a ``this.randStream.randperm(n)``-equivalent draw."""
        replay = self._process_rng_replay_for_tick()
        if replay is not None:
            return replay.permutation(n)
        return self._rng.permutation(n)

    def _draw_choice(self, n: int, *, p: np.ndarray) -> int:
        """Dispatch a ``this.randStream.randsample(n, 1, true, p)``-equivalent draw."""
        replay = self._process_rng_replay_for_tick()
        if replay is not None:
            return replay.choice(n, p=p)
        return int(self._rng.choice(n, p=p))

    def _ensure_chromosome_release_rng(self) -> Any:
        ledger = self._chromosome_release_ledger
        if ledger is not None and ledger.has_tick(self._tick_index):
            draws = ledger.draws_for_tick(self._tick_index)
            replay_rng = ChromosomeReleaseReplayRng(draws)
            self._chromosome_release_rng = replay_rng
            return replay_rng

        current = self._chromosome_release_rng
        if isinstance(current, ChromosomeReleaseReplayRng):
            current = None
        desired_signature = self._rng_stream_signature(self._rng)
        current_signature = None if current is None else self._rng_stream_signature(current)
        if current is None or current_signature != desired_signature:
            chromosome_rng = self._seeded_rng_like(self._rng)
            if chromosome_rng is None:
                chromosome_rng = current if current is not None else self._rng
            else:
                warmup = int(self._chromosome_release_rng_warmup_draws)
                if warmup > 0:
                    chromosome_rng.random(warmup)
            self._chromosome_release_rng = chromosome_rng
        return self._chromosome_release_rng

    def calc_rna_polymerase_binding_prob_fold_change(
        self,
        *,
        positive_regions: list[tuple[int, int, int]],
        linking_values: np.ndarray,
    ) -> dict[str, float]:
        if (
            self.num_transcription_units <= 0
            or self.fold_change_tu_indices.size == 0
            or not positive_regions
            or linking_values.size == 0
        ):
            return {tu_wid: 1.0 for tu_wid in self.supercoiling_tu_wids}

        starts = np.asarray([start for start, _, _ in positive_regions], dtype=np.int64)
        strands = np.asarray([strand for _, strand, _ in positive_regions], dtype=np.int64)
        lengths_i64 = np.asarray([length for _, _, length in positive_regions], dtype=np.int64)
        relaxed = lengths_i64.astype(np.float64) / float(self.parameters["bp_per_turn"])
        sigmas = (linking_values.astype(np.float64) - relaxed) / np.maximum(1.0, relaxed)

        fold_change = np.ones((self.num_transcription_units, 2), dtype=np.float64)
        assigned = np.zeros((self.num_transcription_units, 2), dtype=bool)
        for i, tu_coord in enumerate(self.fold_change_tu_coordinates.tolist()):
            tu_index = int(self.fold_change_tu_indices[i])
            if tu_index < 0 or tu_index >= self.num_transcription_units:
                continue
            region_indices = np.flatnonzero(
                (starts <= int(tu_coord)) & (starts + lengths_i64 - 1 >= int(tu_coord))
            )
            for region_idx in region_indices.tolist():
                thresholded_sigma = float(
                    np.clip(
                        sigmas[region_idx],
                        self.fold_change_lower_sigma_limit,
                        self.fold_change_upper_sigma_limit,
                    )
                )
                chromosome_idx = int(strands[region_idx] // 2)
                if chromosome_idx < 0 or chromosome_idx >= fold_change.shape[1]:
                    continue
                fold_change[tu_index, chromosome_idx] = float(
                    self.fold_change_intercepts[i] + self.fold_change_slopes[i] * thresholded_sigma
                )
                assigned[tu_index, chromosome_idx] = True

        out: dict[str, float] = {}
        for tu_index in self.fold_change_tu_indices.tolist():
            idx = int(tu_index)
            if idx < 0 or idx >= self.num_transcription_units:
                continue
            tu_wid = f"TU_{idx + 1:03d}"
            present = assigned[idx]
            if np.any(present):
                out[tu_wid] = float(np.mean(fold_change[idx, present]))
            else:
                out[tu_wid] = 1.0
        return out

    def _ensure_polymerized_regions(self, polymerized: SparseTriplet) -> SparseTriplet:
        if polymerized.calc_num_edges() > 0:
            return polymerized
        default_state = self.build_default_chromosome_state()
        return SparseTriplet.from_state(default_state["polymerizedRegions"], shape=self.chromosome_shape)

    def _positive_ds_regions(self, polymerized: SparseTriplet) -> list[tuple[int, int, int]]:
        regions_by_strand: dict[int, list[tuple[int, int]]] = {}
        for start, strand, length in zip(
            polymerized.positions.tolist(),
            polymerized.strands.tolist(),
            polymerized.values.tolist(),
            strict=False,
        ):
            intervals = _split_circular_region(int(start), int(length), self.chromosome_length)
            regions_by_strand.setdefault(int(strand), []).extend(intervals)

        positive_regions: list[tuple[int, int, int]] = []
        strand_pairs = ((0, 1), (2, 3))
        for positive_strand, negative_strand in strand_pairs:
            for pos_start, pos_end in regions_by_strand.get(positive_strand, []):
                for neg_start, neg_end in regions_by_strand.get(negative_strand, []):
                    start = max(pos_start, neg_start)
                    end = min(pos_end, neg_end)
                    if start <= end:
                        positive_regions.append((start, positive_strand, end - start + 1))
        return _merge_linear_regions(positive_regions)

    def _positive_regions_from_store(
        self,
        *,
        store: ChromosomeStore,
        polymerized: SparseTriplet,
    ) -> list[tuple[int, int, int]]:
        if store.has_hidden_sparse_field("doubleStrandedRegions"):
            hidden = store.get_hidden_sparse_field("doubleStrandedRegions")
            hidden_regions = [
                (int(position), int(strand), int(value))
                for position, strand, value in hidden.to_regions()
                if int(strand) % 2 == 0 and int(value) > 0
            ]
            return _merge_linear_regions(hidden_regions)
        return self._positive_ds_regions(polymerized)

    def _align_positive_region_values(
        self,
        *,
        positive_regions: list[tuple[int, int, int]],
        linking_numbers: SparseTriplet,
        fallback_sigma: float | np.ndarray,
    ) -> np.ndarray:
        lookup = {
            (int(position), int(strand)): int(value)
            for position, strand, value in zip(
                linking_numbers.positions.tolist(),
                linking_numbers.strands.tolist(),
                linking_numbers.values.tolist(),
                strict=False,
            )
            if int(strand) % 2 == 0
        }
        # fallback_sigma may be a single scalar (uniform fallback, prior
        # behavior) or a per-region array (e.g. sigma_values sourced from
        # the superhelicalDensity input oracle -- see next_update, which
        # passes the SAME per-region sigma used for legality gating here,
        # so an absent-linkingNumbers region's writeback baseline is never
        # computed from a different density than the one that decided
        # whether an enzyme was legal to act on it this tick).
        fallback_arr = np.broadcast_to(
            np.asarray(fallback_sigma, dtype=np.float64), (len(positive_regions),)
        )
        values: list[int] = []
        for region_idx, (start, strand, length) in enumerate(positive_regions):
            current = lookup.get((int(start), int(strand)))
            if current is None:
                relaxed = float(length) / float(self.parameters["bp_per_turn"])
                current = int(round(relaxed * (1.0 + float(fallback_arr[region_idx]))))
            values.append(int(current))
        return np.asarray(values, dtype=np.int32)

    def _positive_region_sigmas_from_store(
        self,
        *,
        store: ChromosomeStore,
        positive_regions: list[tuple[int, int, int]],
        linking_numbers: SparseTriplet,
        fallback_sigma: float,
    ) -> np.ndarray:
        if store.has_hidden_sparse_field("superhelicalDensity"):
            hidden = store.get_hidden_sparse_field("superhelicalDensity")
            lookup = {
                (int(position), int(strand)): float(value)
                for position, strand, value in zip(
                    hidden.positions.tolist(),
                    hidden.strands.tolist(),
                    hidden.values.tolist(),
                    strict=False,
                )
                if int(strand) % 2 == 0
            }
            return np.asarray(
                [
                    float(lookup.get((int(start), int(strand)), 0.0))
                    for start, strand, _ in positive_regions
                ],
                dtype=np.float64,
            )

        linking_values = self._align_positive_region_values(
            positive_regions=positive_regions,
            linking_numbers=linking_numbers,
            fallback_sigma=fallback_sigma,
        )
        return self._region_sigmas(
            positive_regions=positive_regions,
            linking_values=linking_values,
        )

    def _build_linking_numbers_triplet(
        self,
        positive_regions: list[tuple[int, int, int]],
        positive_values: np.ndarray,
    ) -> SparseTriplet:
        positions: list[int] = []
        strands: list[int] = []
        values: list[int] = []
        for (start, strand, _), value in zip(positive_regions, positive_values.tolist(), strict=False):
            positions.extend([int(start), int(start)])
            strands.extend([int(strand), int(strand) + 1])
            values.extend([int(value), int(value)])
        return SparseTriplet(
            positions=np.asarray(positions, dtype=np.int64),
            strands=np.asarray(strands, dtype=np.int8),
            values=np.asarray(values, dtype=np.int32),
            shape=self.chromosome_shape,
        )

    def _region_sigmas(
        self,
        *,
        positive_regions: list[tuple[int, int, int]],
        linking_values: np.ndarray,
    ) -> np.ndarray:
        if not positive_regions:
            return np.array([], dtype=np.float64)
        relaxed = np.asarray(
            [length / float(self.parameters["bp_per_turn"]) for _, _, length in positive_regions],
            dtype=np.float64,
        )
        return (linking_values.astype(np.float64) - relaxed) / np.maximum(1.0, relaxed)

    def _weighted_sigma(
        self,
        *,
        positive_regions: list[tuple[int, int, int]],
        sigma_values: np.ndarray,
    ) -> float:
        if sigma_values.size == 0:
            return float(self.equilibrium_sigma)
        weights = np.asarray([length for _, _, length in positive_regions], dtype=np.float64)
        total = float(weights.sum())
        if total <= 0.0:
            return float(np.mean(sigma_values))
        return float(np.sum(weights * sigma_values) / total)

    def _replication_region_index(self, positive_regions: list[tuple[int, int, int]]) -> int | None:
        if not positive_regions:
            return None
        chromosome_one = [idx for idx, (_, strand, _) in enumerate(positive_regions) if strand == 0]
        if chromosome_one:
            return max(chromosome_one, key=lambda idx: positive_regions[idx][2])
        return max(range(len(positive_regions)), key=lambda idx: positive_regions[idx][2])

    def _resolve_enzyme_count(
        self,
        wid: str,
        *,
        protein_counts: dict[str, Any],
        complex_counts: dict[str, Any],
        top_level_enzymes: dict[str, Any],
    ) -> float:
        if wid in top_level_enzymes:
            return max(0.0, float(top_level_enzymes.get(wid, 0.0)))
        store = self.enzyme_store_by_wid.get(wid)
        if store is None:
            raise KeyError(f"Declared enzyme '{wid}' is missing store classification")
        if store == "complex":
            if wid not in complex_counts:
                raise KeyError(f"Missing declared complex enzyme '{wid}' in complex.counts")
            return max(0.0, float(complex_counts[wid]))
        if wid not in protein_counts:
            return 0.0
        return max(0.0, float(protein_counts[wid]))

    def _bound_site_field_name(self, enzyme_idx: int) -> str:
        idx = int(enzyme_idx)
        if bool(self.enzyme_is_monomer[idx]):
            return "monomerBoundSites"
        return "complexBoundSites"

    def _enzyme_footprint(self, enzyme_idx: int) -> int:
        return int(self.enzyme_dna_footprints[int(enzyme_idx)])

    def _region_chromosome_index(self, strand: int) -> int:
        return int(strand) // 2

    def _damage_pairs(self, store: ChromosomeStore) -> np.ndarray:
        if store.has_hidden_sparse_field("damagedSites"):
            damaged = store.get_hidden_sparse_field("damagedSites")
            if damaged.positions.size == 0:
                return np.zeros((0, 2), dtype=np.int64)
            return np.unique(
                np.column_stack((damaged.positions, damaged.strands)).astype(np.int64, copy=False),
                axis=0,
            )
        pairs: list[np.ndarray] = []
        for field_name in _DAMAGE_FIELD_NAMES:
            triplet = store.get_field(field_name)
            if triplet.positions.size == 0:
                continue
            if field_name == "damagedBases":
                # Chromosome.calcDamagedSites (Chromosome.m:3626-3627) calls
                # getDamagedSites with includeM6AD=false: m6AD-methylated
                # positions in damagedBases are a routine epigenetic mark,
                # not damage, and real MATLAB's damagedSites/exclusion
                # logic never blocks protein binding because of one. See
                # _load_m6ad_global_index's docstring.
                keep = triplet.values.astype(np.int64, copy=False) != self._m6ad_global_index
                if not np.any(keep):
                    continue
                pairs.append(np.column_stack((triplet.positions[keep], triplet.strands[keep])))
                continue
            pairs.append(np.column_stack((triplet.positions, triplet.strands)))
        if not pairs:
            return np.zeros((0, 2), dtype=np.int64)
        return np.unique(np.vstack(pairs).astype(np.int64, copy=False), axis=0)

    def _bound_site_footprints(self, triplet: SparseTriplet, *, is_monomer: bool) -> np.ndarray:
        if triplet.values.size == 0:
            return np.zeros(0, dtype=np.int64)
        indexes = triplet.values.astype(np.int64, copy=False) - 1
        if np.any(indexes < 0):
            raise ValueError(f"Bound-site global indexes must be positive, got {triplet.values.tolist()!r}")
        footprints = (
            self.all_monomer_dna_footprints
            if is_monomer
            else self.all_complex_dna_footprints
        )
        return footprints[indexes]

    def _occupied_space_in_full_length(
        self,
        *,
        store: ChromosomeStore,
        chromosome_index: int | None = None,
    ) -> float:
        total = 0.0
        for field_name, is_monomer in (
            ("monomerBoundSites", True),
            ("complexBoundSites", False),
        ):
            triplet = store.get_field(field_name)
            if triplet.positions.size == 0:
                continue
            mask = np.ones(triplet.positions.size, dtype=bool)
            if chromosome_index is not None:
                mask = (triplet.strands.astype(np.int64, copy=False) // 2) == int(chromosome_index)
            if not np.any(mask):
                continue
            total += float(self._bound_site_footprints(triplet, is_monomer=is_monomer)[mask].sum())

        damage_pairs = self._damage_pairs(store)
        if damage_pairs.size == 0:
            return total
        if chromosome_index is None:
            return total + float(damage_pairs.shape[0])
        return total + float(
            np.count_nonzero(
                (damage_pairs[:, 1].astype(np.int64, copy=False) // 2) == int(chromosome_index)
            )
        )

    def _accessible_space_in_region(
        self,
        *,
        store: ChromosomeStore,
        start: int,
        strand: int,
        length: int,
    ) -> float:
        region_start = int(start)
        region_end = region_start + int(length) - 1
        chromosome_index = self._region_chromosome_index(int(strand))
        occupied = 0.0

        monomer_triplet = store.get_field("monomerBoundSites")
        if monomer_triplet.positions.size:
            monomer_mask = (
                (monomer_triplet.positions.astype(np.int64, copy=False) >= region_start)
                & (monomer_triplet.positions.astype(np.int64, copy=False) <= region_end)
                & ((monomer_triplet.strands.astype(np.int64, copy=False) // 2) == chromosome_index)
            )
            if np.any(monomer_mask):
                occupied += float(
                    self._bound_site_footprints(monomer_triplet, is_monomer=True)[monomer_mask].sum()
                )

        complex_triplet = store.get_field("complexBoundSites")
        if complex_triplet.positions.size:
            complex_mask = (
                (complex_triplet.positions.astype(np.int64, copy=False) >= region_start)
                & (complex_triplet.positions.astype(np.int64, copy=False) <= region_end)
                & ((complex_triplet.strands.astype(np.int64, copy=False) // 2) == chromosome_index)
            )
            if np.any(complex_mask):
                # Literal MATLAB quirk for the fragmented transient topoI branch
                # (DNASupercoiling.m:453): occupied complex-bound sites are
                # subtracted with `monomerDNAFootprints(cmps(...), 1)`, not the
                # complex-footprint table used by the full-length branches.
                occupied += float(
                    self._bound_site_footprints(complex_triplet, is_monomer=True)[complex_mask].sum()
                )

        damage_pairs = self._damage_pairs(store)
        if damage_pairs.size:
            damage_mask = (
                (damage_pairs[:, 0].astype(np.int64, copy=False) >= region_start)
                & (damage_pairs[:, 0].astype(np.int64, copy=False) <= region_end)
                & ((damage_pairs[:, 1].astype(np.int64, copy=False) // 2) == chromosome_index)
            )
            occupied += float(np.count_nonzero(damage_mask))

        return float(int(length) - occupied)

    def _calculate_transient_binding(
        self,
        *,
        store: ChromosomeStore,
        enzyme_idx: int,
        positive_regions: list[tuple[int, int, int]],
        legal_mask: np.ndarray,
        available_count: float,
    ) -> np.ndarray:
        transient = np.zeros(len(positive_regions), dtype=np.float64)
        if not positive_regions or available_count <= 0.0:
            return transient

        footprint = float(self._enzyme_footprint(enzyme_idx))
        if footprint <= 0.0:
            return transient

        lengths = np.asarray([length for _, _, length in positive_regions], dtype=np.float64)
        if lengths.size == 1 and int(lengths[0]) == self.chromosome_length:
            space = float(self.chromosome_length) - self._occupied_space_in_full_length(store=store)
            transient[0] = min(float(available_count), space / footprint)
            return transient

        if lengths.size == 2 and np.all(lengths.astype(np.int64) == self.chromosome_length):
            spaces = np.asarray(
                [
                    float(self.chromosome_length)
                    - self._occupied_space_in_full_length(
                        store=store,
                        chromosome_index=chromosome_index,
                    )
                    for chromosome_index in range(2)
                ],
                dtype=np.float64,
            )
            total_space = float(spaces.sum())
            if total_space == 0.0:
                return transient
            transient = min(float(available_count), total_space / footprint) * spaces / total_space
            if self._draw_random() < 0.5:
                transient[0] = float(_round_half_up(transient[0]))
                transient[1] = float(_round_half_down(transient[1]))
            else:
                transient[1] = float(_round_half_up(transient[1]))
                transient[0] = float(_round_half_down(transient[0]))
            return transient

        spaces = np.zeros(len(positive_regions), dtype=np.float64)
        for region_index, (start, strand, length) in enumerate(positive_regions):
            if region_index >= legal_mask.size or not bool(legal_mask[region_index]):
                continue
            spaces[region_index] = self._accessible_space_in_region(
                store=store,
                start=int(start),
                strand=int(strand),
                length=int(length),
            )

        if len(positive_regions) == 1:
            transient[0] = min(float(available_count), spaces[0] / footprint)
            return transient

        total_space = float(spaces.sum())
        if total_space == 0.0:
            return transient
        return spaces / total_space * min(float(available_count), total_space / footprint)

    def _enzyme_binding_strandedness(self, enzyme_idx: int) -> int:
        enzyme_global_idx = int(self.enzyme_global_indices[int(enzyme_idx)]) - 1
        if bool(self.enzyme_is_monomer[int(enzyme_idx)]):
            return int(self.all_monomer_binding_strandedness[enzyme_global_idx])
        return int(self.all_complex_binding_strandedness[enzyme_global_idx])

    def _enzyme_region_strandedness(self, enzyme_idx: int) -> int:
        enzyme_global_idx = int(self.enzyme_global_indices[int(enzyme_idx)]) - 1
        if bool(self.enzyme_is_monomer[int(enzyme_idx)]):
            return int(self.all_monomer_region_strandedness[enzyme_global_idx])
        return int(self.all_complex_region_strandedness[enzyme_global_idx])

    def _releasable_protein_indices(
        self,
        *,
        binding_monomers: tuple[int, ...] = (),
        binding_complexes: tuple[int, ...] = (),
    ) -> tuple[np.ndarray, np.ndarray]:
        """Literal `Chromosome.getReleasableProteins` port for stable binding.

        Indices stay in Karr's 1-based global-index spaces because the
        chromosome bound-site triplets use those same vocabularies.
        """
        score = np.zeros_like(self.reaction_thresholds)
        if binding_monomers:
            monomer_cols = np.asarray(binding_monomers, dtype=np.int64) - 1
            score = score + np.sum(self.reaction_monomer_catalysis_matrix[:, monomer_cols], axis=1)
        if binding_complexes:
            complex_cols = np.asarray(binding_complexes, dtype=np.int64) - 1
            score = score + np.sum(self.reaction_complex_catalysis_matrix[:, complex_cols], axis=1)

        releasable_monomers = self.reaction_bound_monomer[score >= self.reaction_thresholds]
        releasable_monomers = releasable_monomers[releasable_monomers != 0]
        if releasable_monomers.size:
            releasable_monomers = np.unique(releasable_monomers.astype(np.int64, copy=False))
        else:
            releasable_monomers = np.zeros(0, dtype=np.int64)

        releasable_complexes = self.reaction_bound_complex[score >= self.reaction_thresholds]
        releasable_complexes = releasable_complexes[releasable_complexes != 0]
        if releasable_complexes.size:
            releasable_complexes = np.unique(releasable_complexes.astype(np.int64, copy=False))
        else:
            releasable_complexes = np.zeros(0, dtype=np.int64)

        return releasable_monomers, releasable_complexes

    def _binding_blocked_regions(
        self,
        *,
        store: ChromosomeStore,
        enzyme_idx: int,
    ) -> dict[int, list[tuple[int, int]]]:
        if self._enzyme_binding_strandedness(enzyme_idx) != _DNA_STRANDEDNESS_DSDNA:
            raise NotImplementedError("DNASupercoiling stable binding expects dsDNA-binding enzymes")
        if self._enzyme_region_strandedness(enzyme_idx) != _DNA_STRANDEDNESS_DSDNA:
            raise NotImplementedError("DNASupercoiling stable binding expects dsDNA-region enzymes")

        enzyme_global_idx = int(self.enzyme_global_indices[int(enzyme_idx)])
        releasable_monomers, releasable_complexes = self._releasable_protein_indices(
            binding_monomers=(enzyme_global_idx,) if bool(self.enzyme_is_monomer[int(enzyme_idx)]) else (),
            binding_complexes=(enzyme_global_idx,) if bool(self.enzyme_is_complex[int(enzyme_idx)]) else (),
        )
        blocked: dict[int, list[tuple[int, int]]] = {}
        for field_name, is_monomer, releasable_indices in (
            ("monomerBoundSites", True, releasable_monomers),
            ("complexBoundSites", False, releasable_complexes),
        ):
            triplet = store.get_field(field_name)
            if triplet.positions.size == 0:
                continue
            keep_mask = ~np.isin(
                triplet.values.astype(np.int64, copy=False),
                releasable_indices,
            )
            if not np.any(keep_mask):
                continue
            footprints = self._bound_site_footprints(triplet, is_monomer=is_monomer)[keep_mask]
            for position, strand, footprint in zip(
                triplet.positions[keep_mask].tolist(),
                triplet.strands[keep_mask].tolist(),
                footprints.tolist(),
                strict=False,
            ):
                positive_strand = 2 * self._region_chromosome_index(int(strand))
                # Deliberately NOT `_split_circular_region`-wrapped here: a
                # bound site's footprint may extend past
                # `chromosome_length` (e.g. `position=580051`,
                # `footprint=630` on a 580076bp chromosome). Real MATLAB's
                # `getAccessibleRegions`/`excludeRegions` never pre-splits
                # such an exclusion at the chromosome boundary either --
                # `excludeRegions` handles ALL circularity later, uniformly,
                # via its own `excPos = [pos-L; pos; pos+L]` triple-shift
                # (see `_matlab_exclude_regions`, this module). Pre-splitting
                # here would silently truncate this single continuous
                # exclusion into a short in-bounds fragment plus a separate
                # wrapped-to-position-0 fragment, corrupting
                # `_matlab_exclude_regions`'s call-global "last entry"
                # (MATLAB's own `excLens(end)` bug value) whenever the
                # truncated fragment happens to still sort last -- exactly
                # the divergence that caused seed 14 ticks 76-78's
                # audit-boundary breach (STATUS_L22_DNAS_SEPT2.md).
                blocked.setdefault(positive_strand, []).append(
                    (int(position), int(position) + int(footprint))
                )

        for position, strand in self._damage_pairs(store).tolist():
            positive_strand = 2 * self._region_chromosome_index(int(strand))
            blocked.setdefault(positive_strand, []).append((int(position), int(position) + 1))

        for intervals in blocked.values():
            intervals.sort()
        return blocked


    def _accessible_binding_regions(
        self,
        *,
        store: ChromosomeStore,
        enzyme_idx: int,
        positive_regions: list[tuple[int, int, int]],
    ) -> list[tuple[int, int, int]]:
        """Real, live accessible-space fragments for stable protein binding.

        Delegates to ``_matlab_exclude_regions``, a bug-compatible port of
        ``Chromosome.excludeRegions`` (see that function's docstring): the
        exclusion set is processed as ONE global call spanning every
        strand/pair-index together (matching MATLAB's own single
        ``getAccessibleRegions``/``excludeRegions`` call per
        ``bindProteinToChromosomeStochastically`` invocation), not as
        independent per-region subtraction -- the real algorithm's "does
        the matched exclusion reach this fragment's end?" branch depends
        on the length of whichever exclusion entry sorts last GLOBALLY
        (any strand, anywhere on the chromosome), not on anything specific
        to the fragment being processed, so per-region-independent
        subtraction cannot reproduce it.
        """
        blocked = self._binding_blocked_regions(store=store, enzyme_idx=enzyme_idx)
        excluded: list[tuple[int, int, int]] = [
            (int(block_start), int(strand), int(block_end) - int(block_start))
            for strand, intervals in blocked.items()
            for block_start, block_end in intervals
        ]
        return _matlab_exclude_regions(
            [(int(start), int(strand), int(length)) for start, strand, length in positive_regions],
            excluded,
            chromosome_length=self.chromosome_length,
        )

    def _stable_binding_candidate_start_windows(
        self,
        *,
        accessible_regions: list[tuple[int, int, int]],
        footprint: int,
    ) -> list[tuple[int, int, int]]:
        return [
            (int(start), int(strand), int(start) + int(length) - int(footprint))
            for start, strand, length in accessible_regions
            if int(length) >= int(footprint)
        ]

    def _validate_sampled_stable_binding_sites(
        self,
        *,
        accessible_regions: list[tuple[int, int, int]],
        positions: list[int],
        strands: list[int],
        footprint: int,
    ) -> None:
        if not positions:
            return

        windows = self._stable_binding_candidate_start_windows(
            accessible_regions=accessible_regions,
            footprint=int(footprint),
        )
        for position, strand in zip(positions, strands, strict=False):
            if not any(
                int(window_strand) == int(strand)
                and int(window_start) <= int(position) <= int(window_end)
                for window_start, window_strand, window_end in windows
            ):
                raise ValueError(
                    "Stable binding sampled a site outside the source candidate space: "
                    f"position={position}, strand={strand}, windows={windows!r}"
                )

        occupancy: dict[int, list[tuple[int, int]]] = {}
        for position, strand in zip(positions, strands, strict=False):
            for start, end in _split_circular_region(
                int(position),
                int(footprint),
                self.chromosome_length,
            ):
                occupancy.setdefault(int(strand), []).append((int(start), int(end)))

        for strand, intervals in occupancy.items():
            ordered = sorted(intervals)
            for idx in range(1, len(ordered)):
                if int(ordered[idx][0]) <= int(ordered[idx - 1][1]):
                    raise ValueError(
                        "Stable binding sampled overlapping source-invalid sites: "
                        f"strand={strand}, intervals={ordered!r}"
                    )

    def _apply_binding_result(
        self,
        *,
        binding_result: ChromosomeBindingResult,
        free_counts: dict[int, float],
        bound_counts: dict[int, float],
        protein_side_effect_deltas: dict[str, float],
        complex_side_effect_deltas: dict[str, float],
    ) -> None:
        for global_index, delta in zip(
            self._stable_binding_main_effect_monomer_indices.tolist(),
            binding_result.released_monomers.tolist(),
            strict=False,
        ):
            if float(delta) == 0.0:
                continue
            enzyme_idx = self._enzyme_idx_by_global_index[int(global_index)]
            free_counts[enzyme_idx] = max(0.0, float(free_counts.get(enzyme_idx, 0.0) + float(delta)))
            bound_counts[enzyme_idx] = max(
                0.0,
                float(bound_counts.get(enzyme_idx, 0.0) - float(delta)),
            )
        for global_index, delta in zip(
            self._stable_binding_main_effect_complex_indices.tolist(),
            binding_result.released_complexes.tolist(),
            strict=False,
        ):
            if float(delta) == 0.0:
                continue
            enzyme_idx = self._enzyme_idx_by_global_index[int(global_index)]
            free_counts[enzyme_idx] = max(0.0, float(free_counts.get(enzyme_idx, 0.0) + float(delta)))
            bound_counts[enzyme_idx] = max(
                0.0,
                float(bound_counts.get(enzyme_idx, 0.0) - float(delta)),
            )
        for effect in binding_result.side_effects:
            if int(effect.bound_delta) != -int(effect.mature_delta):
                raise ValueError(
                    "Expected chromosome-release side effect bound_delta to mirror mature_delta, "
                    f"got {effect!r}"
                )
            if effect.molecule_kind == "monomer":
                raise NotImplementedError(
                    "DNAS stable binding unexpectedly produced an external monomer side effect: "
                    f"{effect!r}"
                )
            if effect.molecule_kind != "complex":
                raise ValueError(f"Unknown chromosome-binding side-effect kind: {effect.molecule_kind!r}")
            wid = self._complex_wid_by_global_index.get(int(effect.global_index))
            if wid is None:
                raise KeyError(
                    f"Missing complex WID for chromosome-binding side effect index {effect.global_index}"
                )
            complex_side_effect_deltas[wid] = float(
                complex_side_effect_deltas.get(wid, 0.0) + float(effect.mature_delta)
            )

    def _bind_protein_to_chromosome_stochastically(
        self,
        *,
        store: ChromosomeStore,
        enzyme_idx: int,
        available_count: float,
        positive_regions: list[tuple[int, int, int]],
    ) -> tuple[ChromosomeStore, ChromosomeBindingResult]:
        if available_count <= 0.0 or not positive_regions:
            return (
                store,
                ChromosomeBindingResult(
                    n_bound=0,
                    released_monomers=np.zeros(
                        self._stable_binding_main_effect_monomer_indices.size,
                        dtype=np.int64,
                    ),
                    released_complexes=np.zeros(
                        self._stable_binding_main_effect_complex_indices.size,
                        dtype=np.int64,
                    ),
                    side_effects=(),
                ),
            )

        footprint = int(self._enzyme_footprint(enzyme_idx))
        if footprint <= 0:
            return (
                store,
                ChromosomeBindingResult(
                    n_bound=0,
                    released_monomers=np.zeros(
                        self._stable_binding_main_effect_monomer_indices.size,
                        dtype=np.int64,
                    ),
                    released_complexes=np.zeros(
                        self._stable_binding_main_effect_complex_indices.size,
                        dtype=np.int64,
                    ),
                    side_effects=(),
                ),
            )

        accessible = self._accessible_binding_regions(
            store=store,
            enzyme_idx=enzyme_idx,
            positive_regions=positive_regions,
        )
        if not accessible:
            return (
                store,
                ChromosomeBindingResult(
                    n_bound=0,
                    released_monomers=np.zeros(
                        self._stable_binding_main_effect_monomer_indices.size,
                        dtype=np.int64,
                    ),
                    released_complexes=np.zeros(
                        self._stable_binding_main_effect_complex_indices.size,
                        dtype=np.int64,
                    ),
                    side_effects=(),
                ),
            )

        region_starts = [int(start) for start, _, _ in accessible]
        region_strands = [int(strand) for _, strand, _ in accessible]
        region_lengths = [int(length) for _, _, length in accessible]
        region_weights = [max(0, int(length) - footprint + 1) for length in region_lengths]
        bound_positions: list[int] = []
        bound_strands: list[int] = []

        for _ in range(int(math.floor(float(available_count)))):
            if not any(region_weights):
                break
            weights = np.asarray(region_weights, dtype=np.float64)
            weights /= float(weights.sum())
            region_idx = int(self._draw_choice(len(region_weights), p=weights))
            offset = int(
                math.floor(
                    self._draw_random() * float(region_lengths[region_idx] - footprint + 1)
                )
            )
            bound_positions.append(region_starts[region_idx] + offset)
            bound_strands.append(region_strands[region_idx])

            region_starts.append(region_starts[region_idx] + offset + footprint)
            region_strands.append(region_strands[region_idx])
            region_lengths.append(region_lengths[region_idx] - offset - footprint)
            region_lengths[region_idx] = offset
            region_weights[region_idx] = max(0, region_lengths[region_idx] - footprint + 1)
            region_weights.append(max(0, region_lengths[-1] - footprint + 1))

        if not bound_positions:
            return (
                store,
                ChromosomeBindingResult(
                    n_bound=0,
                    released_monomers=np.zeros(
                        self._stable_binding_main_effect_monomer_indices.size,
                        dtype=np.int64,
                    ),
                    released_complexes=np.zeros(
                        self._stable_binding_main_effect_complex_indices.size,
                        dtype=np.int64,
                    ),
                    side_effects=(),
                ),
            )

        self._validate_sampled_stable_binding_sites(
            accessible_regions=accessible,
            positions=bound_positions,
            strands=bound_strands,
            footprint=footprint,
        )

        field_name = self._bound_site_field_name(enzyme_idx)
        enzyme_global_idx = int(self.enzyme_global_indices[int(enzyme_idx)])
        store_next = store.copy()
        binding_result = store_next.set_site_protein_bound(
            positions=np.asarray(bound_positions, dtype=np.int64),
            strands=np.asarray(bound_strands, dtype=np.int64),
            field_name=field_name,
            binding_global_index=enzyme_global_idx,
            binding_footprint=footprint,
            binding_both_strands=self._enzyme_binding_strandedness(enzyme_idx) == _DNA_STRANDEDNESS_DSDNA,
            region_both_strands=self._enzyme_region_strandedness(enzyme_idx) == _DNA_STRANDEDNESS_DSDNA,
            main_effect_monomer_indices=self._stable_binding_main_effect_monomer_indices,
            main_effect_complex_indices=self._stable_binding_main_effect_complex_indices,
            monomer_footprints=self.all_monomer_dna_footprints,
            complex_footprints=self.all_complex_dna_footprints,
            monomer_binding_strandedness=self.all_monomer_binding_strandedness,
            complex_binding_strandedness=self.all_complex_binding_strandedness,
        )
        return store_next, binding_result

    def _count_bound_proteins_in_region(
        self,
        *,
        store: ChromosomeStore,
        position: int,
        strand: int,
        region_length: int,
        enzyme_idx: int,
    ) -> int:
        if region_length == 0:
            return 0
        triplet = store.get_field(self._bound_site_field_name(enzyme_idx))
        if triplet.positions.size == 0:
            return 0
        enzyme_global_idx = int(self.enzyme_global_indices[int(enzyme_idx)])
        mask = (
            (triplet.values.astype(np.int64, copy=False) == enzyme_global_idx)
            & (triplet.strands.astype(np.int64, copy=False) == int(strand))
            & (triplet.positions.astype(np.int64, copy=False) >= int(position))
            & (
                triplet.positions.astype(np.int64, copy=False)
                < int(position) + int(region_length)
            )
        )
        return int(np.count_nonzero(mask))

    def _enzyme_activity_probability_for_sigma(self, *, enzyme_idx: int, sigma: float) -> float:
        if int(enzyme_idx) == int(self.topoiv_idx):
            return 1.0 if sigma > self.topoiv_sigma_limit else 0.0
        if int(enzyme_idx) == int(self.gyrase_idx):
            return self._activity_probability(
                sigma=float(sigma),
                logistic_const=float(self.gyrase_logistic_const),
                sigma_limit=float(self.gyrase_sigma_limit),
                allowed_when="greater",
            )
        if int(enzyme_idx) == int(self.topoi_idx):
            return self._activity_probability(
                sigma=float(sigma),
                logistic_const=float(self.topoi_logistic_const),
                sigma_limit=float(self.topoi_sigma_limit),
                allowed_when="less",
            )
        return 0.0

    def _sample_activity_events_by_region(
        self,
        *,
        store: ChromosomeStore,
        positive_regions: list[tuple[int, int, int]],
        sigma_values: np.ndarray,
        legal: np.ndarray,
        topoi_transient: np.ndarray,
        available_atp: float,
        available_h2o: float,
        dt: float,
    ) -> tuple[np.ndarray, float]:
        events = np.zeros((len(positive_regions), len(self.enzyme_wids)), dtype=np.int32)
        if not positive_regions or sigma_values.size == 0 or dt <= 0.0:
            return events, 0.0
        activity_order = self._draw_permutation(len(self.enzyme_wids)).tolist()
        remaining_atp = max(0.0, float(available_atp))
        remaining_h2o = max(0.0, float(available_h2o))
        atp_used = 0.0
        for region_index, (start, strand, length) in enumerate(positive_regions):
            for enzyme_idx in activity_order:
                if enzyme_idx >= legal.shape[1] or not bool(legal[region_index, enzyme_idx]):
                    continue
                # Karr MATLAB (DNASupercoiling.m evolveState) calls
                # this.randStream.stochasticRound(...) unconditionally for
                # every (region, enzyme) pair with legal(i, enzProps(j).idx)
                # true -- stochasticRound itself (RandStream.m) always draws
                # rand() regardless of the input value, even when the
                # expected count is exactly zero (e.g. an enzyme with no
                # currently-bound copies in this region, or a saturated
                # sigma giving zero activity probability). Earlier-exiting
                # before this draw (on activity_rate, n_bound, or
                # probability being non-positive) desyncs the process RNG
                # stream from the authoritative MATLAB consumption order, so
                # none of those checks may skip the draw -- only whether the
                # pair is "legal" gates it, exactly as in the source.
                activity_rate = float(self.enzyme_activity_rates[enzyme_idx])
                if float(self.enzyme_mean_dwell_times[enzyme_idx]) == 0.0:
                    n_bound = float(topoi_transient[region_index])
                else:
                    n_bound = float(
                        self._count_bound_proteins_in_region(
                            store=store,
                            position=int(start),
                            strand=int(strand),
                            region_length=int(length),
                            enzyme_idx=enzyme_idx,
                        )
                    )
                probability = self._enzyme_activity_probability_for_sigma(
                    enzyme_idx=enzyme_idx,
                    sigma=float(sigma_values[region_index]),
                )
                expected = max(0.0, n_bound * activity_rate * probability * float(dt))
                n_events = int(self._stochastic_round(expected))
                if n_events <= 0:
                    continue
                atp_cost = float(self.enzyme_atp_costs[enzyme_idx])
                if atp_cost > 0.0:
                    max_events = min(
                        int(math.floor(remaining_atp / atp_cost)),
                        int(math.floor(remaining_h2o / atp_cost)),
                    )
                    if max_events <= 0:
                        continue
                    n_events = min(n_events, max_events)
                    n_atp = float(n_events) * atp_cost
                    remaining_atp = max(0.0, remaining_atp - n_atp)
                    remaining_h2o = max(0.0, remaining_h2o - n_atp)
                    atp_used += n_atp
                events[region_index, enzyme_idx] = n_events
        return events, atp_used

    def _triplets_equal(self, left: SparseTriplet, right: SparseTriplet) -> bool:
        return (
            left.shape == right.shape
            and np.array_equal(left.positions, right.positions)
            and np.array_equal(left.strands, right.strands)
            and np.array_equal(left.values, right.values)
        )

    def _protected_overlap(
        self,
        *,
        position: int,
        strand: int,
        footprint: int,
        protected_regions: list[tuple[int, int, int]],
    ) -> bool:
        if not protected_regions or footprint <= 0:
            return False
        for site_start, site_end in _split_circular_region(
            int(position),
            int(footprint),
            self.chromosome_length,
        ):
            for region_start, region_strand, region_len in protected_regions:
                if int(region_strand) != int(strand):
                    continue
                region_end = int(region_start) + int(region_len) - 1
                if site_start <= region_end and site_end >= int(region_start):
                    return True
        return False

    def _release_bound_enzyme_from_chromosome(
        self,
        *,
        store: ChromosomeStore,
        enzyme_idx: int,
        release_rate: float,
        dt: float,
        protected_regions: list[tuple[int, int, int]],
    ) -> tuple[ChromosomeStore, float]:
        rate = float(release_rate)
        if enzyme_idx < 0 or (not np.isfinite(rate) and rate <= 0.0) or (np.isfinite(rate) and rate == 0.0):
            return store, 0.0

        field_name = self._bound_site_field_name(enzyme_idx)
        triplet = store.get_field(field_name)
        enzyme_global_idx = int(self.enzyme_global_indices[int(enzyme_idx)])
        matching = np.flatnonzero(triplet.values.astype(np.int64) == enzyme_global_idx)
        if matching.size == 0:
            return store, 0.0

        release_flags = np.ones(matching.size, dtype=bool)
        if np.isfinite(rate):
            release_prob = min(1.0, max(0.0, rate * max(0.0, float(dt))))
            if release_prob <= 0.0:
                return store, 0.0
            chromosome_release_rng = self._ensure_chromosome_release_rng()
            release_flags = (
                np.asarray(chromosome_release_rng.random(int(matching.size)), dtype=np.float64)
                < release_prob
            )
        if protected_regions:
            footprint = self._enzyme_footprint(enzyme_idx)
            for rel_i, triplet_i in enumerate(matching.tolist()):
                if not release_flags[rel_i]:
                    continue
                if self._protected_overlap(
                    position=int(triplet.positions[triplet_i]),
                    strand=int(triplet.strands[triplet_i]),
                    footprint=footprint,
                    protected_regions=protected_regions,
                ):
                    release_flags[rel_i] = False
        if not np.any(release_flags):
            return store, 0.0

        drop = np.zeros(triplet.positions.shape[0], dtype=bool)
        drop[matching[release_flags]] = True
        store_next = store.copy()
        store_next.set_field(
            field_name,
            SparseTriplet(
                positions=triplet.positions[~drop],
                strands=triplet.strands[~drop],
                values=triplet.values[~drop],
                shape=triplet.shape,
            ),
        )
        return store_next, float(np.count_nonzero(release_flags))

    def _allocated_or_state(self, allocated_state: dict[str, Any], wid: str) -> float:
        allocated = float(allocated_state.get(wid, 0.0))
        return max(0.0, allocated)

    def _replication_supercoil_load_events(self, replication_state: str, dt: float) -> int:
        if replication_state != "elongating":
            return 0
        rate = max(0.0, float(self.parameters["replication_supercoil_load_rate"]))
        return int(self._rng.poisson(rate * max(0.0, dt)))

    def _activity_probability(
        self,
        *,
        sigma: float,
        logistic_const: float,
        sigma_limit: float,
        allowed_when: str,
    ) -> float:
        if allowed_when == "greater":
            if sigma <= sigma_limit:
                return 0.0
        elif allowed_when == "less":
            if sigma >= sigma_limit:
                return 0.0
        else:
            raise ValueError(f"Unknown allowed_when mode: {allowed_when}")

        x = float(logistic_const) * (float(sigma) - float(self.equilibrium_sigma))
        x = float(np.clip(x, a_min=-60.0, a_max=60.0))
        return float(1.0 / (1.0 + np.exp(x)))

    def _stochastic_round(self, value: float) -> int:
        # Karr MATLAB RandStream.stochasticRound (RandStream.m:236-240) has
        # no early return: `roundUp = rand(this.randStream, size(value)) <
        # mod(value,1)` always draws exactly one random number, even when
        # value is <= 0 or an exact integer (mod(value,1)==0 then makes
        # roundUp deterministically false, but the draw itself still
        # advances the RNG stream). Short-circuiting before the draw here
        # desyncs the process RNG stream from the authoritative MATLAB
        # consumption order, so this must always draw unconditionally.
        base = int(math.floor(value))
        frac = float(value - base)
        round_up = self._draw_random() < frac
        return base + 1 if round_up else base

    def _emit_hint_delta(
        self,
        *,
        update: dict[str, Any],
        channel: str,
        current: dict[str, Any],
        nxt: dict[str, Any],
    ) -> None:
        if not nxt:
            return
        for wid in self.enzyme_wids:
            now = float(current.get(wid, 0.0))
            after = float(nxt.get(wid, now))
            delta = after - now
            if delta != 0.0:
                update.setdefault(channel, {})[wid] = float(delta)

    def _expected_event_rate(
        self,
        *,
        base_rate: float,
        enzyme_count: float,
        reference_count: float,
        probability: float,
        dt: float,
    ) -> float:
        if base_rate <= 0.0 or enzyme_count <= 0.0 or probability <= 0.0 or dt <= 0.0:
            return 0.0
        ref = max(1e-9, reference_count)
        count_scale = enzyme_count / ref
        return max(0.0, base_rate * count_scale * probability * dt)

    def _atp_request(
        self,
        *,
        sigma: float,
        replication_state: str,
        gyrase_count: float,
        topoiv_count: float,
        dt: float,
    ) -> float:
        gyrase_prob = self._activity_probability(
            sigma=sigma,
            logistic_const=self.gyrase_logistic_const,
            sigma_limit=self.gyrase_sigma_limit,
            allowed_when="greater",
        )
        topoiv_prob = 1.0 if sigma > self.topoiv_sigma_limit else 0.0

        expected_g_events = self._expected_event_rate(
            base_rate=self.gyrase_activity_rate,
            enzyme_count=gyrase_count,
            reference_count=float(self.parameters["reference_gyrase_count"]),
            probability=gyrase_prob,
            dt=dt,
        )
        expected_t_events = self._expected_event_rate(
            base_rate=self.topoiv_activity_rate,
            enzyme_count=topoiv_count,
            reference_count=float(self.parameters["reference_topoiv_count"]),
            probability=topoiv_prob,
            dt=dt,
        )

        replication_extra = 0.0
        if replication_state == "elongating":
            replication_extra = (
                max(0.0, float(self.parameters["replication_supercoil_load_rate"]))
                * max(0.0, dt)
            )

        expected_atp = (
            expected_g_events * self.gyrase_atp_cost
            + expected_t_events * self.topoiv_atp_cost
            + replication_extra * self.gyrase_atp_cost
        )
        safety = max(1.0, float(self.parameters["request_safety_factor"]))
        req = math.ceil(expected_atp * safety)
        return float(min(req, max(0.0, float(self.parameters["request_max_atp"]))))

    def _substrate_delta(self, atp_used: float) -> dict[str, float]:
        if atp_used <= 0.0:
            return {}
        out = {
            self.atp_wid: float(-atp_used),
            self.h2o_wid: float(-atp_used),
            self.adp_wid: float(atp_used),
            self.pi_wid: float(atp_used),
        }
        if self.h_wid is not None:
            out[self.h_wid] = float(atp_used)
        return out


__all__ = ["KarrDNASupercoilingProcess"]
