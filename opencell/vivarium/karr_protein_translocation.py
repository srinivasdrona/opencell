"""Vivarium Process port of Karr's ProteinTranslocation flow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/ProteinTranslocation_flat.mat"
_CYTOPLASM = "cytoplasm"
_MEMBRANE = "membrane"
_EXTRACELLULAR = "extracellular"

# These two terminal-organelle proteins are assembled in a dedicated process.
_TERMINAL_ORGANELLE_EXCLUSIONS = {"MG_191_MONOMER", "MG_192_MONOMER"}


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
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved))
        fx = mat["data"]["fixture"][0, 0]

        self.substrate_wids = _parse_wid_array(fx["substrateWholeCellModelIDs"])
        self.enzyme_wids = _parse_wid_array(fx["enzymeWholeCellModelIDs"])
        self.monomer_wids = _parse_wid_array(fx["monomerWholeCellModelIDs"])

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
        aa_per_atp = float(_as_vector(fx["preproteinTranslocase_aaTranslocatedPerATP"])[0])
        self.srp_gtp_cost_per_monomer = int(
            max(0.0, np.floor(float(_as_vector(fx["SRP_GTPUsedPerMonomer"])[0])))
        )

        self.destination_by_wid: dict[str, str] = {}
        self.destination_class_by_wid: dict[str, str] = {}
        self.pathway_by_wid: dict[str, str] = {}
        self.atp_cost_by_wid: dict[str, int] = {}

        integral_membrane_wids: list[str] = []
        lipoprotein_wids: list[str] = []
        extracellular_wids: list[str] = []

        for idx in translocating_indices.tolist():
            wid = self.monomer_wids[int(idx)]
            if wid in _TERMINAL_ORGANELLE_EXCLUSIONS:
                continue

            destination = _MEMBRANE
            destination_class = "integral_membrane"
            pathway = "srp"

            # Empirically in this fixture:
            # - compartment code 3 maps to extracellular proteins
            # - among membrane-target proteins (code 4), SRP flag=1 are lipoproteins
            #   routed through the direct path in this Phase-B simplification.
            compartment_code = int(monomer_compartments[int(idx)])
            srp_flag = int(monomer_srp_pathways[int(idx)])
            if compartment_code == 3:
                destination = _EXTRACELLULAR
                destination_class = "extracellular"
                pathway = "direct"
                extracellular_wids.append(wid)
            elif srp_flag == 1:
                destination = _MEMBRANE
                destination_class = "lipoprotein"
                pathway = "direct"
                lipoprotein_wids.append(wid)
            else:
                destination = _MEMBRANE
                destination_class = "integral_membrane"
                pathway = "srp"
                integral_membrane_wids.append(wid)

            monomer_len = max(1, int(monomer_lengths[int(idx)]))
            atp_cost = max(1, int(np.ceil(float(monomer_len) / aa_per_atp)))

            self.destination_by_wid[wid] = destination
            self.destination_class_by_wid[wid] = destination_class
            self.pathway_by_wid[wid] = pathway
            self.atp_cost_by_wid[wid] = atp_cost

        self.integral_membrane_wids = integral_membrane_wids
        self.lipoprotein_wids = lipoprotein_wids
        self.extracellular_wids = extracellular_wids
        self.translocatable_wids = (
            self.integral_membrane_wids + self.lipoprotein_wids + self.extracellular_wids
        )
        self.direct_path_wids = self.lipoprotein_wids + self.extracellular_wids

        self.protein_count_wids = list(dict.fromkeys(self.enzyme_wids + self.translocatable_wids))

    def ports_schema(self) -> dict[str, Any]:
        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.substrate_wids
            },
            "protein": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.protein_count_wids
                },
                "location": {
                    wid: {"_default": _CYTOPLASM, "_updater": "set", "_emit": True}
                    for wid in self.translocatable_wids
                },
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

    def _available_substrate(self, states: dict[str, Any], wid: str) -> int:
        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})
        if wid in allocated_state:
            return int(max(0.0, np.floor(float(allocated_state.get(wid, 0.0)))))
        return int(max(0.0, np.floor(float(states["substrates"].get(wid, 0.0)))))

    def _ordered_wids(self, wids: list[str]) -> list[str]:
        if len(wids) <= 1:
            return wids
        order = self._rng.permutation(len(wids))
        return [wids[int(i)] for i in order]

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep
        protein_counts_state = states.get("protein", {}).get("counts", {})
        location_state = states.get("protein", {}).get("location", {})

        cytoplasmic_counts = {
            wid: _read_nonnegative_count(protein_counts_state, wid)
            for wid in self.translocatable_wids
            if str(location_state.get(wid, _CYTOPLASM)) == _CYTOPLASM
            and _read_nonnegative_count(protein_counts_state, wid) > 0
        }
        if not cytoplasmic_counts:
            return {}

        atp_remaining = self._available_substrate(states, self.atp_wid)
        gtp_remaining = self._available_substrate(states, self.gtp_wid)
        h2o_remaining = self._available_substrate(states, self.h2o_wid)
        if atp_remaining <= 0 or h2o_remaining <= 0:
            return {}

        srp_remaining = _read_nonnegative_count(protein_counts_state, self.srp_wid)
        srp_receptor_remaining = _read_nonnegative_count(
            protein_counts_state, self.srp_receptor_wid
        )
        atpase_remaining = _read_nonnegative_count(
            protein_counts_state, self.translocase_atpase_wid
        )
        pore_remaining = _read_nonnegative_count(protein_counts_state, self.translocase_pore_wid)

        translocated_counts: dict[str, int] = {}
        atp_spent = 0
        gtp_spent = 0

        def attempt_phase(candidates: list[str], needs_srp: bool) -> None:
            nonlocal atp_remaining
            nonlocal gtp_remaining
            nonlocal h2o_remaining
            nonlocal srp_remaining
            nonlocal srp_receptor_remaining
            nonlocal atpase_remaining
            nonlocal pore_remaining
            nonlocal atp_spent
            nonlocal gtp_spent

            for wid in self._ordered_wids(candidates):
                count = int(cytoplasmic_counts.get(wid, 0))
                if count <= 0:
                    continue

                atp_need = count * int(self.atp_cost_by_wid[wid])
                gtp_need = count * int(self.srp_gtp_cost_per_monomer) if needs_srp else 0
                hydrolysis_need = atp_need + gtp_need
                if atp_need > atp_remaining or gtp_need > gtp_remaining or hydrolysis_need > h2o_remaining:
                    continue
                if atpase_remaining < count or pore_remaining < count:
                    continue
                if needs_srp and (srp_remaining < count or srp_receptor_remaining < count):
                    continue

                translocated_counts[wid] = count
                atp_remaining -= atp_need
                gtp_remaining -= gtp_need
                h2o_remaining -= hydrolysis_need
                atpase_remaining -= count
                pore_remaining -= count
                atp_spent += atp_need
                gtp_spent += gtp_need
                if needs_srp:
                    srp_remaining -= count
                    srp_receptor_remaining -= count

        # Phase 1: SRP-mediated pathway for integral membrane proteins.
        attempt_phase(
            [wid for wid in self.integral_membrane_wids if wid in cytoplasmic_counts],
            needs_srp=True,
        )

        # Phase 2: direct pathway for lipoproteins and extracellular proteins.
        attempt_phase(
            [wid for wid in self.direct_path_wids if wid in cytoplasmic_counts],
            needs_srp=False,
        )

        if not translocated_counts:
            return {}

        hydrolysis_spent = atp_spent + gtp_spent
        location_update = {wid: self.destination_by_wid[wid] for wid in translocated_counts}

        update: dict[str, Any] = {"protein": {"location": location_update}}
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
