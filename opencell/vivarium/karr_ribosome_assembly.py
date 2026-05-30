"""Vivarium Process for Karr's GTP-dependent ribosome assembly."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/RibosomeAssembly_flat.mat"


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


def _extract_one_based_index(value: np.ndarray) -> int:
    """Extract a fixture index field and convert it to zero-based integer."""
    item: object = np.asarray(value, dtype=object)
    while isinstance(item, np.ndarray):
        if item.size == 0:
            raise ValueError("Empty index field in RibosomeAssembly fixture")
        item = item.flat[0]
    return int(item) - 1


def _stoich_limit_from_pool(
    pool: dict[str, int],
    wids: list[str],
    stoich_col: np.ndarray,
) -> int:
    active = np.flatnonzero(stoich_col > 0)
    if active.size == 0:
        return np.iinfo(np.int64).max

    limits: list[int] = []
    for idx in active:
        wid = wids[int(idx)]
        coeff = int(stoich_col[int(idx)])
        avail = max(0, int(pool.get(wid, 0)))
        limits.append(avail // coeff)
    return int(min(limits)) if limits else 0


class KarrRibosomeAssemblyProcess(Process):
    """Karr Process_RibosomeAssembly with all-or-nothing per-tick formation."""

    name = "karr_ribosome_assembly"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

        self.complex_index_by_wid = {wid: idx for idx, wid in enumerate(self.complex_wids)}
        self.substrate_index_by_wid = {wid: idx for idx, wid in enumerate(self.substrate_wids)}
        self.gtpase_index_by_wid = {wid: idx for idx, wid in enumerate(self.gtpase_wids)}
        self.protein_state_wids = list(dict.fromkeys(self.monomer_subunit_wids + self.gtpase_wids))

        self.gtpase_wids_by_name = {
            "EngA": self.gtpase_wids[self.enzyme_index_engA],
            "EngB": self.gtpase_wids[self.enzyme_index_engB],
            "Era": self.gtpase_wids[self.enzyme_index_era],
            "Obg": self.gtpase_wids[self.enzyme_index_obg],
            "RbfA": self.gtpase_wids[self.enzyme_index_rbfA],
            "RbgA": self.gtpase_wids[self.enzyme_index_rbgA],
        }

        self.substrate_wid_gtp = self.substrate_wids[self.substrate_index_gtp]
        self.substrate_wid_gdp = self.substrate_wids[self.substrate_index_gdp]
        self.substrate_wid_phosphate = self.substrate_wids[self.substrate_index_phosphate]
        self.substrate_wid_h2o = self.substrate_wids[self.substrate_index_h2o]
        self.substrate_wid_h = self.substrate_wids[self.substrate_index_hydrogen]

        self.n_gtpases_per_particle = {
            wid: int(np.sum(self.complexation_catalysis[:, idx]))
            for wid, idx in self.complex_index_by_wid.items()
        }

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved))
        fx = mat["data"]["fixture"][0, 0]

        self.substrate_wids = _extract_wids(fx["substrateWholeCellModelIDs"])
        self.gtpase_wids = _extract_wids(fx["enzymeWholeCellModelIDs"])
        self.rna_subunit_wids = _extract_wids(fx["rnaWholeCellModelIDs"])
        self.monomer_subunit_wids = _extract_wids(fx["monomerWholeCellModelIDs"])
        self.complex_wids = _extract_wids(fx["complexWholeCellModelIDs"])

        self.complexation_catalysis = np.asarray(
            fx["complexationCatalysisMatrix"][0, 0], dtype=np.int64
        )
        self.protein_complex_rna_composition = np.asarray(
            fx["proteinComplexRNAComposition"][0, 0], dtype=np.int64
        )
        self.protein_complex_monomer_composition = np.asarray(
            fx["proteinComplexMonomerComposition"][0, 0], dtype=np.int64
        )

        self.substrate_index_gtp = _extract_one_based_index(fx["substrateIndexs_gtp"])
        self.substrate_index_gdp = _extract_one_based_index(fx["substrateIndexs_gdp"])
        self.substrate_index_phosphate = _extract_one_based_index(fx["substrateIndexs_phosphate"])
        self.substrate_index_h2o = _extract_one_based_index(fx["substrateIndexs_water"])
        self.substrate_index_hydrogen = _extract_one_based_index(fx["substrateIndexs_hydrogen"])

        self.enzyme_index_engA = _extract_one_based_index(fx["enzymeIndexs_engA"])
        self.enzyme_index_engB = _extract_one_based_index(fx["enzymeIndexs_engB"])
        self.enzyme_index_era = _extract_one_based_index(fx["enzymeIndexs_era"])
        self.enzyme_index_obg = _extract_one_based_index(fx["enzymeIndexs_obg"])
        self.enzyme_index_rbfA = _extract_one_based_index(fx["enzymeIndexs_rbfA"])
        self.enzyme_index_rbgA = _extract_one_based_index(fx["enzymeIndexs_rbgA"])

    def ports_schema(self) -> dict[str, Any]:
        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.substrate_wids
            },
            "enzymes": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.gtpase_wids
            },
            "boundEnzymes": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.gtpase_wids
            },
            "complexs": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.complex_wids
            },
            "monomers": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.monomer_subunit_wids
            },
            "rna": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.rna_subunit_wids
                }
            },
            "protein": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.protein_state_wids
                }
            },
            "complex": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.complex_wids
                }
            },
            "requests": {
                self.name: {
                    self.substrate_wid_gtp: {
                        "_default": 0.0,
                        "_updater": "set",
                        "_emit": False,
                    },
                    self.substrate_wid_h2o: {
                        "_default": 0.0,
                        "_updater": "set",
                        "_emit": False,
                    },
                }
            },
            "substrates_allocated": {
                self.name: {
                    self.substrate_wid_gtp: {
                        "_default": 0.0,

                        "_emit": False,
                    },
                    self.substrate_wid_h2o: {
                        "_default": 0.0,

                        "_emit": False,
                    },
                }
            },
        }

    def _build_rna_pool(self, states: dict[str, Any]) -> dict[str, int]:
        counts = states.get("rna", {}).get("counts", {})
        return {
            wid: max(0, int(math.floor(float(counts.get(wid, 0.0)))))
            for wid in self.rna_subunit_wids
        }

    def _build_monomer_pool(self, states: dict[str, Any]) -> dict[str, int]:
        counts = states.get("protein", {}).get("counts", {})
        return {
            wid: max(0, int(math.floor(float(counts.get(wid, 0.0)))))
            for wid in self.monomer_subunit_wids
        }

    def _build_gtpase_pool(self, states: dict[str, Any]) -> dict[str, int]:
        counts = states.get("protein", {}).get("counts", {})
        return {
            wid: max(0, int(math.floor(float(counts.get(wid, 0.0))))) for wid in self.gtpase_wids
        }

    def _particle_resource_limits(
        self,
        particle_wid: str,
        rna_pool: dict[str, int],
        monomer_pool: dict[str, int],
        gtpase_pool: dict[str, int],
    ) -> tuple[int, int, int]:
        cidx = self.complex_index_by_wid[particle_wid]
        rna_limit = _stoich_limit_from_pool(
            rna_pool,
            self.rna_subunit_wids,
            self.protein_complex_rna_composition[:, cidx],
        )
        monomer_limit = _stoich_limit_from_pool(
            monomer_pool,
            self.monomer_subunit_wids,
            self.protein_complex_monomer_composition[:, cidx],
        )
        gtpase_limit = _stoich_limit_from_pool(
            gtpase_pool,
            self.gtpase_wids,
            self.complexation_catalysis[:, cidx],
        )
        return int(rna_limit), int(monomer_limit), int(gtpase_limit)

    def estimate_formable_without_substrates(self, states: dict[str, Any]) -> dict[str, int]:
        """Estimate max formable particles from RNA/protein/enzyme state only."""
        rna_pool = self._build_rna_pool(states)
        monomer_pool = self._build_monomer_pool(states)
        gtpase_pool = self._build_gtpase_pool(states)
        out: dict[str, int] = {}
        for particle_wid in self.complex_wids:
            limits = self._particle_resource_limits(
                particle_wid,
                rna_pool=rna_pool,
                monomer_pool=monomer_pool,
                gtpase_pool=gtpase_pool,
            )
            out[particle_wid] = int(min(limits))
        return out

    def _build_update(self, n_formed: dict[str, int]) -> dict[str, Any]:
        rna_delta = {wid: 0 for wid in self.rna_subunit_wids}
        monomer_delta = {wid: 0 for wid in self.monomer_subunit_wids}
        total_gtp_hydrolyzed = 0

        for particle_wid, n_form in n_formed.items():
            if n_form <= 0:
                continue
            cidx = self.complex_index_by_wid[particle_wid]
            total_gtp_hydrolyzed += n_form * self.n_gtpases_per_particle[particle_wid]

            for ridx, wid in enumerate(self.rna_subunit_wids):
                coeff = int(self.protein_complex_rna_composition[ridx, cidx])
                if coeff > 0:
                    rna_delta[wid] -= n_form * coeff

            for midx, wid in enumerate(self.monomer_subunit_wids):
                coeff = int(self.protein_complex_monomer_composition[midx, cidx])
                if coeff > 0:
                    monomer_delta[wid] -= n_form * coeff

        complex_update = {wid: float(v) for wid, v in n_formed.items() if v > 0}
        substrate_update: dict[str, float] = {}
        if total_gtp_hydrolyzed > 0:
            substrate_update = {
                self.substrate_wid_gtp: float(-total_gtp_hydrolyzed),
                self.substrate_wid_h2o: float(-total_gtp_hydrolyzed),
                self.substrate_wid_gdp: float(total_gtp_hydrolyzed),
                self.substrate_wid_phosphate: float(total_gtp_hydrolyzed),
                self.substrate_wid_h: float(total_gtp_hydrolyzed),
            }

        update: dict[str, Any] = {}
        if substrate_update:
            update["substrates"] = substrate_update
        if any(v != 0 for v in rna_delta.values()):
            update["rna"] = {"counts": {wid: float(v) for wid, v in rna_delta.items() if v != 0}}
        if any(v != 0 for v in monomer_delta.values()):
            update["protein"] = {
                "counts": {wid: float(v) for wid, v in monomer_delta.items() if v != 0}
            }
        if complex_update:
            update["complex"] = {"counts": complex_update}
        return update

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep
        allocated = states.get("substrates_allocated", {}).get(self.name, {})
        gtp_alloc = max(0.0, float(allocated.get(self.substrate_wid_gtp, 0.0)))
        h2o_alloc = max(0.0, float(allocated.get(self.substrate_wid_h2o, 0.0)))

        if gtp_alloc <= 0.0 or h2o_alloc <= 0.0:
            return {}

        rna_pool = self._build_rna_pool(states)
        monomer_pool = self._build_monomer_pool(states)
        gtpase_pool = self._build_gtpase_pool(states)

        n_formed = {wid: 0 for wid in self.complex_wids}

        for cidx in self._rng.permutation(len(self.complex_wids)):
            particle_wid = self.complex_wids[int(cidx)]
            rna_limit, monomer_limit, gtpase_limit = self._particle_resource_limits(
                particle_wid,
                rna_pool=rna_pool,
                monomer_pool=monomer_pool,
                gtpase_pool=gtpase_pool,
            )
            gtp_per_particle = int(self.n_gtpases_per_particle[particle_wid])
            if gtp_per_particle <= 0:
                continue

            gtp_limit = int(math.floor(gtp_alloc / gtp_per_particle))
            h2o_limit = int(math.floor(h2o_alloc / gtp_per_particle))

            n_form = int(min(rna_limit, monomer_limit, gtpase_limit, gtp_limit, h2o_limit))
            if n_form <= 0:
                continue

            n_formed[particle_wid] = n_form
            gtp_alloc -= n_form * gtp_per_particle
            h2o_alloc -= n_form * gtp_per_particle

            for ridx, wid in enumerate(self.rna_subunit_wids):
                coeff = int(self.protein_complex_rna_composition[ridx, int(cidx)])
                if coeff > 0:
                    rna_pool[wid] -= n_form * coeff
            for midx, wid in enumerate(self.monomer_subunit_wids):
                coeff = int(self.protein_complex_monomer_composition[midx, int(cidx)])
                if coeff > 0:
                    monomer_pool[wid] -= n_form * coeff

        return self._build_update(n_formed)


__all__ = ["KarrRibosomeAssemblyProcess"]
