"""Vivarium Process port of Karr's ChromosomeSegregation (literal port).

Primary source:
data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/process/ChromosomeSegregation.m

Karr models segregation as a literal boolean-gated, one-shot event on the
Chromosome state's ``segregated`` flag:

- ``calcResourceRequirements_Current`` (ChromosomeSegregation.m:179-189):
  request ``gtpCost`` GTP + H2O iff the chromosome is not yet segregated, the
  chromosome is fully replicated
  (``collapse(polymerizedRegions) == nCompartments * sequenceLen``), and
  every one of the five segregation enzymes -- including topoisomerase IV
  (``MG_203_204_TETRAMER``) -- is present (``all(this.enzymes)``).
- ``evolveState`` (ChromosomeSegregation.m:193-212): additionally requires
  the chromosome to be fully supercoiled
  (``collapse(supercoiled) == nCompartments``) and at least ``gtpCost`` of
  allocated GTP and H2O; then sets ``segregated = true`` and applies the
  exact GTP + H2O -> GDP + PI + H hydrolysis stoichiometry.

``supercoiled`` is itself a Chromosome-state *dependent* property
(Chromosome.m:3602 ``get.supercoiled``/``calcSupercoiled``, built on
``calcDoubleStrandedRegions`` at Chromosome.m:3205) computed from
``polymerizedRegions`` + ``linkingNumbers`` via the KB constants
``relaxedBasesPerTurn``, ``equilibriumSuperhelicalDensity``, and
``supercoiledSuperhelicalDensityTolerance`` (sourced from the Chromosome
fixture, never hardcoded). The L2 oracle trace does not serialize
``supercoiled`` directly -- it is derived, not stored -- so this port
recomputes it from the two raw sparse chromosome fields the trace *does*
serialize (``polymerizedRegions``, ``linkingNumbers``): a real hidden-state
read, never an oracle-trace read (see Rule 8,
docs/prompts/FIX_TEMPLATE_L2_REPLAY.md).

Downstream compatibility: ``chromosome.segregated`` is the literal Karr
field, and it is already the value ``karr_cytokinesis.py``'s
``_segregation_gate`` prefers when present. ``segregation_progress`` /
``segregation_complete`` / ``daughter_pole_positions`` / ``cell_cycle_event``
are retained as *derived*, pure 0.0/1.0 projections of ``segregated`` --
carrying no independent state of their own -- solely so
``karr_cell_cycle_coordinator.py`` and any other pre-existing consumer of
the old Karr-LIGHT v1 continuous-progress surface keep working unchanged.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.m_gen_constants import GENOME_LENGTH_BP, N_CHROMOSOME_COMPARTMENTS
from opencell.state.chromosome_store import (
    SparseTriplet,
    merge_adjacent_regions,
    sparse_triplet_schema,
)

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ChromosomeSegregation_flat.mat"
_DEFAULT_CHROMOSOME_FIXTURE_PATH = "data/karr_fixtures/per_process/Chromosome_flat.mat"
_MACROMOLECULAR_COMPLEXATION_FIXTURE_PATH = (
    "data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat"
)
_RIBOSOME_ASSEMBLY_FIXTURE_PATH = "data/karr_fixtures/per_process/RibosomeAssembly_flat.mat"
_ALWAYS_COMPLEX_WIDS = frozenset({"RNA_POLYMERASE", "RIBOSOME_70S"})

# Chromosome.m:calcDoubleStrandedRegions pairs strand k with strand k+1 within
# each group `ceil(strand/2)` (1-based); 0-based that is (0, 1) and (2, 3).
_STRAND_PAIRS = ((0, 1), (2, 3))


def _resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    raise FileNotFoundError(f"Path not found: {path}")


def _coerce_scalar(value: object) -> object:
    out = value
    while isinstance(out, np.ndarray):
        if out.size == 0:
            return 0
        out = out.flat[0]
    return out


def _parse_wids(value: object) -> list[str]:
    values = np.asarray(value, dtype=object)
    out: list[str] = []
    for raw in values.ravel():
        out.append(str(_coerce_scalar(raw)))
    return out


def _one_based_to_zero(value: object) -> int:
    return int(_coerce_scalar(value)) - 1


@lru_cache(maxsize=1)
def _canonical_complex_wids() -> frozenset[str]:
    mc = loadmat(
        str(_resolve_path(_MACROMOLECULAR_COMPLEXATION_FIXTURE_PATH)),
        squeeze_me=True,
        struct_as_record=False,
    )["data"].fixture
    ra = loadmat(
        str(_resolve_path(_RIBOSOME_ASSEMBLY_FIXTURE_PATH)),
        squeeze_me=True,
        struct_as_record=False,
    )["data"].fixture
    wids = set(_parse_wids(mc.complexWholeCellModelIDs))
    wids.update(_parse_wids(ra.complexWholeCellModelIDs))
    wids.update(_ALWAYS_COMPLEX_WIDS)
    return frozenset(wids)


def _double_stranded_region_entries(
    polymerized: SparseTriplet,
) -> list[tuple[int, int, int]]:
    """Faithful (if degenerate-case-optimized) port of
    ``Chromosome.m:calcDoubleStrandedRegions`` (~3205-3253).

    Karr pairs strand ``2k-1`` with strand ``2k`` (0-based: strand pair
    ``(2k, 2k+1)``), intersects each pair's polymerized extents, and emits
    the intersected extent at *both* member strands of the pair. Returns a
    list of ``(start, strand, length)`` entries -- one per member strand per
    intersected sub-region.
    """
    merged = merge_adjacent_regions(polymerized)
    by_strand: dict[int, list[tuple[int, int]]] = {}
    for position, strand, length in merged.to_regions():
        by_strand.setdefault(int(strand), []).append((int(position), int(length)))

    entries: list[tuple[int, int, int]] = []
    for strand_a, strand_b in _STRAND_PAIRS:
        for start_a, len_a in by_strand.get(strand_a, []):
            end_a = start_a + len_a
            for start_b, len_b in by_strand.get(strand_b, []):
                end_b = start_b + len_b
                start = max(start_a, start_b)
                end = min(end_a, end_b)
                if end > start:
                    length = end - start
                    entries.append((start, strand_a, length))
                    entries.append((start, strand_b, length))
    return entries


def _supercoiled_pass_count(
    *,
    polymerized: SparseTriplet,
    linking: SparseTriplet,
    bp_per_turn: float,
    equilibrium_sigma: float,
    tolerance: float,
) -> int:
    """Faithful port of ``Chromosome.m:calcSupercoiled`` (~3602-3614).

    For every double-stranded-region entry, look up the linking number at
    that exact (position, strand) -- 0 if absent, matching MATLAB's sparse
    default-fill semantics -- compute the superhelical density sigma, and
    count entries within tolerance of equilibrium. The caller compares this
    count against ``nCompartments`` (Chromosome.m's ``collapse(...)``).
    """
    linking_lookup: dict[tuple[int, int], int] = {
        (int(position), int(strand)): int(value)
        for position, strand, value in zip(
            linking.positions.tolist(),
            linking.strands.tolist(),
            linking.values.tolist(),
            strict=False,
        )
    }

    count = 0
    for start, strand, length in _double_stranded_region_entries(polymerized):
        if length <= 0:
            continue
        lk = linking_lookup.get((start, strand), 0)
        lk0 = length / bp_per_turn
        if lk0 <= 0:
            continue
        sigma = (lk - lk0) / lk0
        if abs(sigma - equilibrium_sigma) < tolerance:
            count += 1
    return count


class KarrChromosomeSegregationProcess(Process):
    """Karr Process_ChromosomeSegregation: literal boolean-gated segregation."""

    name = "karr_chromosome_segregation"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "chromosome_fixture_path": _DEFAULT_CHROMOSOME_FIXTURE_PATH,
        "time_step": 1.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self.chromosome_shape = (int(GENOME_LENGTH_BP), int(N_CHROMOSOME_COMPARTMENTS))
        self.sequence_len, self.n_compartments = self.chromosome_shape

        self._load_fixture(self.parameters["fixture_path"])
        self._load_chromosome_constants(self.parameters["chromosome_fixture_path"])

        gtp_cost_override = self.parameters.get("gtp_cost_override")
        if gtp_cost_override is None:
            self.gtp_cost = float(self._fixture_gtp_cost)
        else:
            self.gtp_cost = float(gtp_cost_override)
        if self.gtp_cost <= 0.0:
            raise ValueError(f"gtp_cost must be > 0, got {self.gtp_cost}")

        self._partition_enzyme_wids()

    def _load_fixture(self, path: str | Path) -> None:
        mat = loadmat(str(_resolve_path(path)), squeeze_me=True, struct_as_record=False)
        fx = mat["data"].fixture

        self.substrate_wids = _parse_wids(fx.substrateWholeCellModelIDs)
        self.enzyme_wids = _parse_wids(fx.enzymeWholeCellModelIDs)

        self.substrate_index_gtp = _one_based_to_zero(fx.substrateIndexs_gtp)
        self.substrate_index_gdp = _one_based_to_zero(fx.substrateIndexs_gdp)
        self.substrate_index_hydrogen = _one_based_to_zero(fx.substrateIndexs_hydrogen)
        self.substrate_index_water = _one_based_to_zero(fx.substrateIndexs_water)
        self.substrate_index_phosphate = _one_based_to_zero(fx.substrateIndexs_phosphate)

        self.gtp_wid = self.substrate_wids[self.substrate_index_gtp]
        self.gdp_wid = self.substrate_wids[self.substrate_index_gdp]
        self.h_wid = self.substrate_wids[self.substrate_index_hydrogen]
        self.h2o_wid = self.substrate_wids[self.substrate_index_water]
        self.pi_wid = self.substrate_wids[self.substrate_index_phosphate]

        self.enzyme_index_cobq = _one_based_to_zero(fx.enzymeIndexs_cobQ)
        self.enzyme_index_mraz = _one_based_to_zero(fx.enzymeIndexs_mraZ)
        self.enzyme_index_obg = _one_based_to_zero(fx.enzymeIndexs_obg)
        self.enzyme_index_era = _one_based_to_zero(fx.enzymeIndexs_era)
        self.enzyme_index_topoiv = _one_based_to_zero(fx.enzymeIndexs_topoIV)

        self.cobq_wid = self.enzyme_wids[self.enzyme_index_cobq]
        self.mraz_wid = self.enzyme_wids[self.enzyme_index_mraz]
        self.obg_wid = self.enzyme_wids[self.enzyme_index_obg]
        self.era_wid = self.enzyme_wids[self.enzyme_index_era]
        self.topoiv_wid = self.enzyme_wids[self.enzyme_index_topoiv]

        # Karr's gate is `all(this.enzymes)`: every one of the 5 fixture
        # enzymes (including topoisomerase IV) is required, unconditionally.
        self.required_enzyme_wids = list(self.enzyme_wids)

        # Fixture-provided per-enzyme steady-state counts, consumed by
        # karr_composite.py's chassis initial-state seeding (not used by the
        # gate logic itself, which reads live protein/complex counts).
        enzyme_counts = np.asarray(fx.enzymes, dtype=np.float64).reshape(-1)
        self.enzyme_count_by_wid = {
            wid: float(enzyme_counts[idx]) for idx, wid in enumerate(self.enzyme_wids)
        }

        self._fixture_gtp_cost = int(_coerce_scalar(fx.gtpCost))

    def _load_chromosome_constants(self, path: str | Path) -> None:
        mat = loadmat(str(_resolve_path(path)), squeeze_me=True, struct_as_record=False)
        fx = mat["data"].fixture
        self.relaxed_bases_per_turn = float(_coerce_scalar(fx.relaxedBasesPerTurn))
        self.equilibrium_superhelical_density = float(
            _coerce_scalar(fx.equilibriumSuperhelicalDensity)
        )
        self.supercoiled_tolerance = float(
            _coerce_scalar(fx.supercoiledSuperhelicalDensityTolerance)
        )

    def _partition_enzyme_wids(self) -> None:
        complex_wids = _canonical_complex_wids()
        self.complex_enzyme_wids = [wid for wid in self.enzyme_wids if wid in complex_wids]
        self.monomer_enzyme_wids = [wid for wid in self.enzyme_wids if wid not in complex_wids]
        self.required_complex_enzyme_wids = [
            wid for wid in self.required_enzyme_wids if wid in complex_wids
        ]
        self.required_monomer_enzyme_wids = [
            wid for wid in self.required_enzyme_wids if wid not in complex_wids
        ]
        self._required_complex_enzyme_wids_set = set(self.required_complex_enzyme_wids)
        self._required_monomer_enzyme_wids_set = set(self.required_monomer_enzyme_wids)

    def ports_schema(self) -> dict[str, Any]:
        return {
            "chromosome": {
                # Literal Karr field (Chromosome.m `segregated` property).
                "segregated": {
                    "_default": False,
                    "_updater": "set",
                    "_emit": True,
                },
                # Read-only hidden inputs: the two raw sparse Chromosome
                # fields needed to derive the `replicated` and `supercoiled`
                # gates. Never written by this process.
                "polymerizedRegions": sparse_triplet_schema(self.chromosome_shape, emit=False),
                "linkingNumbers": sparse_triplet_schema(self.chromosome_shape, emit=False),
                # Derived compatibility outputs (see module docstring): pure
                # 0.0/1.0 projections of `segregated`, kept only so
                # pre-existing consumers of the Karr-LIGHT v1 continuous
                # surface (karr_cell_cycle_coordinator.py) keep working.
                "segregation_progress": {
                    "_default": 0.0,
                    "_updater": "accumulate",
                    "_emit": True,
                },
                "daughter_pole_positions": {
                    "left": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
                    "right": {"_default": 0.0, "_updater": "accumulate", "_emit": True},
                },
                "segregation_complete": {
                    "_default": False,
                    "_updater": "set",
                    "_emit": True,
                },
                "cell_cycle_event": {
                    "_default": "none",
                    "_updater": "set",
                    "_emit": True,
                },
            },
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                for wid in self.substrate_wids
            },
            "enzymes": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.enzyme_wids
            },
            "boundEnzymes": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.enzyme_wids
            },
            "protein": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.monomer_enzyme_wids
                }
            },
            "complex": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.complex_enzyme_wids
                }
            },
            "requests": {
                self.name: {
                    self.gtp_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                    self.h2o_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                }
            },
            "substrates_allocated": {
                self.name: {
                    self.gtp_wid: {"_default": 0.0, "_emit": False},
                    self.h2o_wid: {"_default": 0.0, "_emit": False},
                }
            },
        }

    def _allocated_or_state(self, allocated_state: dict[str, Any], wid: str) -> float:
        allocated = float(allocated_state.get(wid, 0.0))
        return max(0.0, allocated)

    def _enzyme_count(
        self,
        *,
        wid: str,
        protein_counts: dict[str, Any],
        complex_counts: dict[str, Any],
    ) -> float:
        if wid in self._required_complex_enzyme_wids_set:
            if wid not in complex_counts:
                raise KeyError(
                    f"Missing required complex input '{wid}' in complex.counts for {self.name}"
                )
            return float(complex_counts[wid])
        if wid in self._required_monomer_enzyme_wids_set:
            if wid not in protein_counts:
                raise KeyError(
                    f"Missing required monomer input '{wid}' in protein.counts for {self.name}"
                )
            return float(protein_counts[wid])
        raise KeyError(f"Required enzyme '{wid}' is not classified for {self.name}")

    def _all_enzymes_present(
        self,
        *,
        protein_counts: dict[str, Any],
        complex_counts: dict[str, Any],
    ) -> bool:
        # Karr: `all(this.enzymes)` -- every one of the 5 fixture enzymes
        # must be nonzero (MATLAB `all()` numeric-nonzero semantics).
        return all(
            self._enzyme_count(
                wid=wid, protein_counts=protein_counts, complex_counts=complex_counts
            )
            != 0.0
            for wid in self.required_enzyme_wids
        )

    def _is_fully_replicated(self, polymerized: SparseTriplet) -> bool:
        # Karr: `collapse(c.polymerizedRegions) == c.nCompartments * c.sequenceLen`.
        total = int(np.sum(polymerized.values, dtype=np.int64))
        return total == self.n_compartments * self.sequence_len

    def _is_fully_supercoiled(
        self,
        *,
        polymerized: SparseTriplet,
        linking: SparseTriplet,
    ) -> bool:
        # Karr: `collapse(c.supercoiled) == c.nCompartments`.
        pass_count = _supercoiled_pass_count(
            polymerized=polymerized,
            linking=linking,
            bp_per_turn=self.relaxed_bases_per_turn,
            equilibrium_sigma=self.equilibrium_superhelical_density,
            tolerance=self.supercoiled_tolerance,
        )
        return pass_count == self.n_compartments

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep  # Karr's gate has no dt-dependence: segregation is a one-shot event.

        chromosome = states.get("chromosome", {})
        already_segregated = bool(chromosome.get("segregated", False))

        polymerized = SparseTriplet.from_state(
            chromosome.get("polymerizedRegions"), shape=self.chromosome_shape
        )
        linking = SparseTriplet.from_state(
            chromosome.get("linkingNumbers"), shape=self.chromosome_shape
        )

        protein_counts = states.get("protein", {}).get("counts", {})
        complex_counts = states.get("complex", {}).get("counts", {})

        fully_replicated = self._is_fully_replicated(polymerized)
        all_enzymes_present = self._all_enzymes_present(
            protein_counts=protein_counts, complex_counts=complex_counts
        )

        # calcResourceRequirements_Current (ChromosomeSegregation.m:179-189).
        can_request = (not already_segregated) and fully_replicated and all_enzymes_present
        request_gtp = float(self.gtp_cost) if can_request else 0.0
        request_h2o = request_gtp

        # evolveState (ChromosomeSegregation.m:193-212).
        just_segregated = False
        substrate_update: dict[str, float] = {}
        if can_request:
            allocated = states.get("substrates_allocated", {}).get(self.name, {})
            allocated_gtp = self._allocated_or_state(allocated, self.gtp_wid)
            allocated_h2o = self._allocated_or_state(allocated, self.h2o_wid)
            fully_supercoiled = self._is_fully_supercoiled(polymerized=polymerized, linking=linking)
            if (
                fully_supercoiled
                and allocated_gtp >= self.gtp_cost
                and allocated_h2o >= self.gtp_cost
            ):
                just_segregated = True
                substrate_update = {
                    self.gtp_wid: -float(self.gtp_cost),
                    self.h2o_wid: -float(self.gtp_cost),
                    self.gdp_wid: float(self.gtp_cost),
                    self.pi_wid: float(self.gtp_cost),
                    self.h_wid: float(self.gtp_cost),
                }

        chromosome_update: dict[str, Any] = {
            "cell_cycle_event": "segregation_complete" if just_segregated else "none",
        }
        if just_segregated:
            chromosome_update["segregated"] = True
            chromosome_update["segregation_complete"] = True
            # Derived compatibility surface: one-shot 0.0 -> 1.0 jump (the
            # process fires at most once, guarded by `already_segregated`,
            # so the prior accumulated value is always 0.0 here).
            chromosome_update["segregation_progress"] = 1.0
            chromosome_update["daughter_pole_positions"] = {"left": -1.0, "right": 1.0}

        update: dict[str, Any] = {
            "requests": {
                self.name: {
                    self.gtp_wid: float(request_gtp),
                    self.h2o_wid: float(request_h2o),
                }
            },
            "chromosome": chromosome_update,
        }
        if substrate_update:
            update["substrates"] = substrate_update
        return update


__all__ = ["KarrChromosomeSegregationProcess"]
