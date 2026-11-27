"""Vivarium Process port of Karr's ProteinTranslocation flow."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

from opencell.util import MatlabRandStream
from opencell.vivarium.protein_state import MIGRATED_WIDS, compartment_counts_schema

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ProteinTranslocation_flat.mat"
_MACROMOLECULAR_COMPLEXATION_FIXTURE_PATH = (
    "data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat"
)
_RIBOSOME_ASSEMBLY_FIXTURE_PATH = "data/karr_fixtures/per_process/RibosomeAssembly_flat.mat"
_MEMBRANE = "membrane"
_EXTRACELLULAR = "extracellular"
_MEMBRANE_COMPARTMENT = "m"
_EXTRACELLULAR_COMPARTMENT = "e"
_PROCESSED_I_CYTOSOL_COMPARTMENT = "c"
# Design D2: destination letter is source-derived from `destination_by_wid`
# (itself derived from the fixture's post-remap `monomerCompartments`, P2),
# never a hardcoded tm/tc-unaware constant.
_DEST_COMPARTMENT_BY_DESTINATION = {
    _MEMBRANE: _MEMBRANE_COMPARTMENT,
    _EXTRACELLULAR: _EXTRACELLULAR_COMPARTMENT,
}


def _resolve_fixture_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    raise FileNotFoundError(f"Fixture not found: {path}")


def _parse_wid_array(cell_array: np.ndarray) -> list[str]:
    """Convert MATLAB cell-string arrays into a flat Python string list."""
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


def _as_vector(value: np.ndarray) -> np.ndarray:
    arr: object = np.asarray(value, dtype=object)
    while isinstance(arr, np.ndarray) and arr.dtype == object and arr.size == 1:
        arr = arr.flat[0]
    return np.asarray(arr, dtype=np.float64).reshape(-1)


def _as_scalar_int(value: np.ndarray) -> int:
    return int(_as_vector(value)[0])


def _fixture_wids(value: np.ndarray) -> list[str]:
    return np.asarray(value, dtype=object).ravel().astype(str).tolist()


@lru_cache(maxsize=0)  # Keep cache-management hooks without retaining fixture authority.
def _canonical_complex_wids() -> set[str]:
    """Read the current two-fixture union for each constructor's enzyme routes."""
    d2_fixture = loadmat(
        str(_resolve_fixture_path(_MACROMOLECULAR_COMPLEXATION_FIXTURE_PATH)),
        squeeze_me=True,
        struct_as_record=False,
    )["data"].fixture
    ribasm_fixture = loadmat(
        str(_resolve_fixture_path(_RIBOSOME_ASSEMBLY_FIXTURE_PATH)),
        squeeze_me=True,
        struct_as_record=False,
    )["data"].fixture
    return set(_fixture_wids(d2_fixture.complexWholeCellModelIDs)) | set(
        _fixture_wids(ribasm_fixture.complexWholeCellModelIDs)
    ) | {"RNA_POLYMERASE", "RIBOSOME_70S"}


def _read_nonnegative_count(state: dict[str, Any], wid: str) -> int:
    return int(max(0.0, np.floor(float(state.get(wid, 0.0)))))


class KarrProteinTranslocationProcess(Process):
    """Karr Process_ProteinTranslocation (SRP + direct pathway)."""

    name = "karr_protein_translocation"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._rng = MatlabRandStream(int(self.parameters["rng_seed"]))

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved))
        fx = mat["data"]["fixture"][0, 0]

        self.substrate_wids = _parse_wid_array(fx["substrateWholeCellModelIDs"])
        self.enzyme_wids = _parse_wid_array(fx["enzymeWholeCellModelIDs"])
        self.monomer_wids = _parse_wid_array(fx["monomerWholeCellModelIDs"])
        canonical_complex_wids = _canonical_complex_wids()
        self.complex_enzyme_wids = [wid for wid in self.enzyme_wids if wid in canonical_complex_wids]
        self.monomer_enzyme_wids = [
            wid for wid in self.enzyme_wids if wid not in canonical_complex_wids
        ]
        self._complex_enzyme_wid_set = set(self.complex_enzyme_wids)

        atp_substrate_idx = _as_scalar_int(fx["substrateIndexs_atp"]) - 1
        gtp_substrate_idx = _as_scalar_int(fx["substrateIndexs_gtp"]) - 1
        adp_substrate_idx = _as_scalar_int(fx["substrateIndexs_adp"]) - 1
        gdp_substrate_idx = _as_scalar_int(fx["substrateIndexs_gdp"]) - 1
        pi_substrate_idx = _as_scalar_int(fx["substrateIndexs_phosphate"]) - 1
        h2o_substrate_idx = _as_scalar_int(fx["substrateIndexs_water"]) - 1
        h_substrate_idx = _as_scalar_int(fx["substrateIndexs_hydrogen"]) - 1
        self.atp_wid = self.substrate_wids[atp_substrate_idx]
        self.gtp_wid = self.substrate_wids[gtp_substrate_idx]
        self.adp_wid = self.substrate_wids[adp_substrate_idx]
        self.gdp_wid = self.substrate_wids[gdp_substrate_idx]
        self.pi_wid = self.substrate_wids[pi_substrate_idx]
        self.h2o_wid = self.substrate_wids[h2o_substrate_idx]
        self.h_wid = self.substrate_wids[h_substrate_idx]
        self.allocation_substrate_wids: tuple[str, ...] = tuple(
            sorted(
                {
                    self.atp_wid,
                    self.gtp_wid,
                    self.adp_wid,
                    self.gdp_wid,
                    self.pi_wid,
                    self.h2o_wid,
                    self.h_wid,
                }
            )
        )
        self.request_wids = (self.atp_wid, self.gtp_wid, self.h2o_wid)
        self.vector_wids = (
            self.atp_wid,
            self.gtp_wid,
            self.adp_wid,
            self.gdp_wid,
            self.pi_wid,
            self.h2o_wid,
            self.h_wid,
        )

        srp_idx = _as_scalar_int(fx["enzymeIndexs_signalRecognitionParticle"]) - 1
        srp_receptor_idx = _as_scalar_int(fx["enzymeIndexs_signalRecognitionParticleReceptor"]) - 1
        atpase_idx = _as_scalar_int(fx["enzymeIndexs_translocaseATPase"]) - 1
        pore_idx = _as_scalar_int(fx["enzymeIndexs_translocasePore"]) - 1

        self.srp_wid = self.enzyme_wids[srp_idx]
        self.srp_receptor_wid = self.enzyme_wids[srp_receptor_idx]
        self.translocase_atpase_wid = self.enzyme_wids[atpase_idx]
        self.translocase_pore_wid = self.enzyme_wids[pore_idx]

        translocating_indices = _as_vector(fx["monomerIndexs_translocating"]).astype(np.int64) - 1
        monomer_lengths = _as_vector(fx["monomerLengths"]).astype(np.int64)
        monomer_compartments = _as_vector(fx["monomerCompartments"]).astype(np.int64)
        monomer_srp_pathways = _as_vector(fx["monomerSRPPathways"]).astype(np.int64)
        self.translocase_specific_rate = float(_as_vector(fx["translocaseSpecificRate"])[0])
        self.aa_per_atp = float(_as_vector(fx["preproteinTranslocase_aaTranslocatedPerATP"])[0])
        self.srp_gtp_cost_per_monomer = int(
            max(0.0, np.floor(float(_as_vector(fx["SRP_GTPUsedPerMonomer"])[0])))
        )

        self.destination_by_wid: dict[str, str] = {}
        self.destination_class_by_wid: dict[str, str] = {}
        self.pathway_by_wid: dict[str, str] = {}
        self.atp_cost_by_wid: dict[str, int] = {}
        translocatable_wids_in_fixture_order: list[str] = []

        integral_membrane_wids: list[str] = []
        lipoprotein_wids: list[str] = []
        extracellular_wids: list[str] = []

        for idx in translocating_indices.tolist():
            wid = self.monomer_wids[int(idx)]

            destination = _MEMBRANE
            destination_class = "integral_membrane"
            pathway = "srp"

            # Empirically in this fixture:
            # - compartment code 3 maps to extracellular proteins
            # - among membrane-target proteins (code 4), SRP flag=1 are lipoproteins
            # MATLAB fidelity: SRP/GTP requirements are controlled by SRP flag,
            # independent of destination-class labeling.
            compartment_code = int(monomer_compartments[int(idx)])
            srp_flag = int(monomer_srp_pathways[int(idx)])
            if compartment_code == 3:
                destination = _EXTRACELLULAR
                destination_class = "extracellular"
                extracellular_wids.append(wid)
            elif srp_flag == 1:
                destination = _MEMBRANE
                destination_class = "lipoprotein"
                lipoprotein_wids.append(wid)
            else:
                destination = _MEMBRANE
                destination_class = "integral_membrane"
                integral_membrane_wids.append(wid)
            pathway = "srp" if srp_flag == 1 else "direct"

            monomer_len = max(1, int(monomer_lengths[int(idx)]))
            atp_cost = max(1, int(np.ceil(float(monomer_len) / self.aa_per_atp)))

            self.destination_by_wid[wid] = destination
            self.destination_class_by_wid[wid] = destination_class
            self.pathway_by_wid[wid] = pathway
            self.atp_cost_by_wid[wid] = atp_cost
            translocatable_wids_in_fixture_order.append(wid)

        self.integral_membrane_wids = integral_membrane_wids
        self.lipoprotein_wids = lipoprotein_wids
        self.extracellular_wids = extracellular_wids
        self.translocatable_wids_in_fixture_order = translocatable_wids_in_fixture_order
        self.translocatable_wids = (
            self.integral_membrane_wids + self.lipoprotein_wids + self.extracellular_wids
        )
        self.srp_path_wids = [
            wid for wid in self.translocatable_wids if self.pathway_by_wid[wid] == "srp"
        ]
        self.direct_path_wids = [
            wid for wid in self.translocatable_wids if self.pathway_by_wid[wid] == "direct"
        ]

        # Design D1 (Stage 2): every Karr-translocatable WID is now migrated
        # (the source-derived `MIGRATED_WIDS` union is TOA-8 u PT-translocating-119,
        # so `translocatable_wids` subset MIGRATED_WIDS always). Kept as an
        # explicit intersection (not a bare alias of `translocatable_wids`)
        # so a partial-migration regression in `protein_state.MIGRATED_WIDS`
        # is caught here rather than silently assumed; the assertion below
        # is the load-bearing check, not the variable's existence.
        self.migrated_translocating_wids = set(MIGRATED_WIDS) & set(self.translocatable_wids)
        assert self.migrated_translocating_wids == set(self.translocatable_wids), (
            "Design D1 violation: not every translocatable WID is in "
            "protein_state.MIGRATED_WIDS -- partial migration is banned"
        )

        # `protein_count_wids` is read externally by
        # `RequestCalculatorPTransloc.ports_schema()` (out of Stage-1b's
        # `protein_count_wids` is read externally by
        # `RequestCalculatorPTransloc.ports_schema()` (out of this process's
        # own write scope) to build ITS OWN flat `protein.counts` schema
        # declaration; it must respect the same authority boundary as this
        # process's own `ports_schema()` (2 blocks below) or that external
        # Step re-declares a plain "accumulate" updater over a migrated WID's
        # rejecting-updater leaf (design D3 S12/9.3). After Stage 2, every
        # translocatable WID is migrated, so this reduces to exactly the
        # non-complex enzyme WIDs (MG_297_MONOMER).
        self.protein_count_wids = [
            wid
            for wid in dict.fromkeys(self.monomer_enzyme_wids + self.translocatable_wids)
            if wid not in MIGRATED_WIDS
        ]
        self.complex_count_wids = list(dict.fromkeys(self.complex_enzyme_wids))

    def ports_schema(self) -> dict[str, Any]:
        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
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
            "monomers": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.monomer_wids
            },
            "protein": {
                # Design D1/D6: every translocatable WID is migrated, so the
                # legacy `unprocessed_counts`/`location` branches are deleted
                # outright (not declared-but-empty -- an empty dict here
                # would be the "empty-schema trick" C5 forbids). `counts`
                # keeps only the required monomer enzyme (MG_297_MONOMER);
                # this process never reads/writes any translocatable WID's
                # flat/enzyme-pool leaf, so no schema conflict risk is taken.
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.protein_count_wids
                },
                # Design D2: the full 119-translocatable-WID processedI pool
                # lives at the compartment authority (cytosol source,
                # source-derived `e`/`m` destination -- ProteinTranslocation.m
                # :198-200 remap), iterated in fixture order (never a set).
                "compartment_counts": {
                    "processed_i": {
                        wid: compartment_counts_schema(MIGRATED_WIDS)["processed_i"][wid]
                        for wid in self.translocatable_wids_in_fixture_order
                    }
                },
            },
            "complex": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.complex_count_wids
                }
            },
            "requests": {
                self.name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self.request_wids
                }
            },
            "substrates_allocated": {
                self.name: {
                    wid: {"_default": 0.0, "_emit": False} for wid in self.vector_wids
                }
            },
        }

    def _available_substrate(self, allocated_state: dict[str, Any], wid: str) -> int:
        # Strict-zero allocator contract: only allocated budget is readable here.
        allocated = float(allocated_state.get(wid, 0.0))
        return int(max(0.0, np.floor(allocated)))

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        # Fail closed before reading or selecting anything: the copy-order
        # mapping below (`searchsorted(..., side="left")`) is only correct for
        # MATLAB's one-based `randperm`; a zero-based NumPy permutation
        # silently duplicates/skips WIDs.
        if not isinstance(self._rng, MatlabRandStream):
            raise TypeError(
                "karr_protein_translocation requires a MatlabRandStream _rng "
                "(one-based MATLAB randperm behavior); got "
                f"{type(self._rng).__name__}"
            )

        protein_state = states.get("protein", {})
        protein_counts_state = protein_state.get("counts", {})
        enzyme_counts_state = protein_state.get("enzyme_counts", {})
        complex_counts_state = states.get("complex", {}).get("counts", {})
        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})

        missing_complex_wids = [wid for wid in self.complex_count_wids if wid not in complex_counts_state]
        if missing_complex_wids:
            missing_joined = ", ".join(sorted(missing_complex_wids))
            raise KeyError(
                "karr_protein_translocation missing required complex.counts keys: "
                f"{missing_joined}"
            )

        # Design D2/D5: every translocatable WID's cytosolic processedI pool
        # lives at the compartment authority, read in strict fixture order
        # (`translocatable_wids_in_fixture_order`) -- no migrated/non-migrated
        # split, no trailing set-ordered append, no legacy
        # `unprocessed_counts`/`location` read or fallback.
        processed_i_authority_state = protein_state.get("compartment_counts", {}).get(
            "processed_i", {}
        )
        cytoplasmic_counts: dict[str, int] = {}
        for wid in self.translocatable_wids_in_fixture_order:
            count = _read_nonnegative_count(
                processed_i_authority_state.get(wid, {}), _PROCESSED_I_CYTOSOL_COMPARTMENT
            )
            if count > 0:
                cytoplasmic_counts[wid] = count
        if not cytoplasmic_counts:
            return {}

        translocating_wids = list(cytoplasmic_counts)
        translocating_counts = np.fromiter(
            (cytoplasmic_counts[wid] for wid in translocating_wids),
            dtype=np.int64,
            count=len(translocating_wids),
        )
        cumulative_counts = np.cumsum(translocating_counts, dtype=np.int64)
        total_copies = int(cumulative_counts[-1]) if cumulative_counts.size else 0
        if total_copies <= 0:
            return {}

        # Design D5 / docstring Simulation step 1 ("In a randomized order...")
        # + step 2 ("Terminate if insufficient resources exist"): Karr
        # establishes the random processing order UNCONDITIONALLY whenever
        # any copy is pending, THEN terminates per-copy on infeasibility --
        # it does not skip the draw merely because the allocator granted
        # zero ATP/H2O this tick. Drawing here (before the atp/h2o
        # early-return below) keeps this process's single persistent stream
        # advancing in lockstep with Karr's on every pending tick, not just
        # the ticks that end up moving a copy. Confirmed empirically against
        # the F-trace oracle: drawing after the feasibility check desyncs
        # the stream the first time pending>0 coincides with a zero-ATP
        # tick, silently flipping which WID a later tick's draw selects.
        copy_order = self._rng.randperm(total_copies)

        atp_remaining = self._available_substrate(allocated_state, self.atp_wid)
        gtp_remaining = self._available_substrate(allocated_state, self.gtp_wid)
        h2o_remaining = self._available_substrate(allocated_state, self.h2o_wid)
        if atp_remaining <= 0 or h2o_remaining <= 0:
            return {}

        def _enzyme_remaining(wid: str) -> int:
            if wid in self._complex_enzyme_wid_set:
                return _read_nonnegative_count(complex_counts_state, wid)
            return max(
                _read_nonnegative_count(protein_counts_state, wid),
                _read_nonnegative_count(enzyme_counts_state, wid),
            )

        srp_capacity = float(
            min(
                _enzyme_remaining(self.srp_wid),
                _enzyme_remaining(self.srp_receptor_wid),
            )
            * float(timestep)
        )
        translocase_capacity = float(
            min(
                _enzyme_remaining(self.translocase_atpase_wid),
                _enzyme_remaining(self.translocase_pore_wid),
            )
            * self.translocase_specific_rate
            * float(timestep)
            / self.aa_per_atp
        )

        translocated_counts: dict[str, float] = {}
        atp_spent = 0.0
        gtp_spent = 0.0

        # Match Karr's randperm over individual copies without expanding a copy list.
        for copy_index in copy_order:
            wid_index = int(np.searchsorted(cumulative_counts, int(copy_index), side="left"))
            wid = translocating_wids[wid_index]
            atp_per_monomer = int(self.atp_cost_by_wid[wid])
            requires_srp = self.pathway_by_wid.get(wid) == "srp"
            srp_per_monomer = 1 if requires_srp else 0
            gtp_per_monomer = int(self.srp_gtp_cost_per_monomer) if requires_srp else 0
            hydrolysis_per_monomer = atp_per_monomer + gtp_per_monomer

            if atp_per_monomer > translocase_capacity:
                break
            if srp_per_monomer > srp_capacity:
                break
            if atp_per_monomer > atp_remaining:
                break
            if gtp_per_monomer > gtp_remaining:
                break
            if hydrolysis_per_monomer > h2o_remaining:
                break

            translocated_counts[wid] = translocated_counts.get(wid, 0.0) + 1.0
            translocase_capacity -= float(atp_per_monomer)
            srp_capacity -= float(srp_per_monomer)
            atp_remaining -= atp_per_monomer
            gtp_remaining -= gtp_per_monomer
            h2o_remaining -= hydrolysis_per_monomer
            atp_spent += float(atp_per_monomer)
            gtp_spent += float(gtp_per_monomer)

        if not translocated_counts:
            return {}

        hydrolysis_spent = atp_spent + gtp_spent

        # Design D2/D6: conserve copies via an authority c -> source-derived
        # destination transfer only (no `location` string, no queue
        # decrement -- C15/C16). Destination is `self.destination_by_wid[wid]`
        # mapped to its single-letter compartment code, so MG_191/192/318
        # land at `m` (their post-remap destination) exactly like every
        # other membrane-destined WID -- never the pre-remap `tm`.
        processed_i_authority_update: dict[str, dict[str, float]] = {
            wid: {
                _PROCESSED_I_CYTOSOL_COMPARTMENT: -float(cnt),
                _DEST_COMPARTMENT_BY_DESTINATION[self.destination_by_wid[wid]]: float(cnt),
            }
            for wid, cnt in translocated_counts.items()
        }

        protein_update: dict[str, Any] = {
            "compartment_counts": {"processed_i": processed_i_authority_update}
        }

        update: dict[str, Any] = {"protein": protein_update}
        if atp_spent > 0:
            substrate_update: dict[str, float] = {
                self.atp_wid: -float(atp_spent),
                self.adp_wid: float(atp_spent),
                self.pi_wid: float(hydrolysis_spent),
                self.h2o_wid: -float(hydrolysis_spent),
                self.h_wid: float(hydrolysis_spent),
            }
            if gtp_spent > 0:
                substrate_update[self.gtp_wid] = -float(gtp_spent)
                substrate_update[self.gdp_wid] = float(gtp_spent)
            update["substrates"] = substrate_update
        return update


__all__ = ["KarrProteinTranslocationProcess"]
