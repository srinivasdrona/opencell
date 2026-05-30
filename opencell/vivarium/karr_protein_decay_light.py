"""Vivarium Process for Karr ProteinDecay-light complex decay only.

Evidence provenance:
- `data/karr_fixtures/per_process/ProteinDecay_flat.mat`:
  `data.fixture.{complexDecayReactions,proteinComplexMonomerComposition,`
  `proteinComplexRNAComposition,substrateWholeCellModelIDs,states,`
  `rnaWholeCellModelIDs,substrateIndexs_atp,substrateIndexs_water}`
- `data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat`:
  `data.fixture.complexWholeCellModelIDs` (canonical D.2-real complex filter)
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "per_process"
_PROTEIN_DECAY_FLAT = _FIXTURE_DIR / "ProteinDecay_flat.mat"
_MACROMOLECULAR_COMPLEXATION_FLAT = _FIXTURE_DIR / "MacromolecularComplexation_flat.mat"
_LN2 = math.log(2.0)


class _Mcg16807:
    """Minimal MATLAB-compatible mcg16807 stream for replay-only helpers."""

    _MOD = 2_147_483_647
    _MUL = 16_807

    def __init__(self, seed: int) -> None:
        self._state = max(1, int(seed))

    def rand(self, shape: tuple[int, ...]) -> np.ndarray:
        n = int(np.prod(shape))
        out = np.empty(n, dtype=np.float64)
        for i in range(n):
            self._state = (self._MUL * self._state) % self._MOD
            out[i] = self._state / self._MOD
        return out.reshape(shape)

    def stochastic_round(self, values: np.ndarray | float) -> np.ndarray:
        arr = np.asarray(values, dtype=np.float64)
        frac = np.mod(arr, 1.0)
        rnd = self.rand(arr.shape)
        return np.where(rnd < frac, np.ceil(arr), np.floor(arr)).astype(np.int64)

    def randsample_one(self, weights: np.ndarray) -> int | None:
        total = float(np.sum(weights, dtype=np.float64))
        if total <= 0.0:
            return None
        threshold = float(self.rand((1,))[0]) * total
        return int(np.searchsorted(np.cumsum(weights, dtype=np.float64), threshold, side="right"))


def _load_flat_fixture(path: Path) -> object:  # noqa: ANN401 - matlab struct dynamic
    return loadmat(str(path), squeeze_me=True, struct_as_record=False)["data"].fixture


def _fixture_wids(values: object) -> list[str]:
    return np.asarray(values, dtype=object).ravel().astype(str).tolist()


def _fixture_state_by_class(
    fixture: object,
    class_name: str,  # noqa: ANN401 - matlab struct dynamic
) -> object:  # noqa: ANN401 - matlab struct dynamic
    for state in np.asarray(fixture.states, dtype=object).ravel():
        if getattr(state, "x_class_", "") == class_name:
            return state
    raise ValueError(f"Fixture state not found: {class_name}")


def _d2_complex_wids(path: Path) -> list[str]:
    fixture = _load_flat_fixture(path)
    return _fixture_wids(fixture.complexWholeCellModelIDs)


class ProteinDecayLightProcess(Process):
    """Karr ProteinDecay sub-process #3 (complex decay), light variant."""

    name = "karr_protein_decay_light"
    defaults: dict[str, Any] = {
        "fixture_path": str(_PROTEIN_DECAY_FLAT),
        "rng_seed": 0,
        "time_step": 1.0,
        "complex_decay_rate_per_s": _LN2 / (8.0 * 3600.0),
        "complex_half_lives": None,
        "consume_atp_h2o": True,
        "complex_wid_filter": None,
        "enable_latent_monomer_decay": True,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        fixture = _load_flat_fixture(Path(self.parameters["fixture_path"]))

        protein_complex_state = _fixture_state_by_class(
            fixture, "edu.stanford.covert.cell.sim.state.ProteinComplex"
        )
        protein_monomer_state = _fixture_state_by_class(
            fixture, "edu.stanford.covert.cell.sim.state.ProteinMonomer"
        )
        polypeptide_state = _fixture_state_by_class(
            fixture, "edu.stanford.covert.cell.sim.state.Polypeptide"
        )

        all_complex_wids = _fixture_wids(protein_complex_state.wholeCellModelIDs)
        canonical_filter = self.parameters.get("complex_wid_filter")
        if canonical_filter is None:
            canonical_filter = _d2_complex_wids(_MACROMOLECULAR_COMPLEXATION_FLAT)
        else:
            canonical_filter = [str(wid) for wid in canonical_filter]

        complex_col_by_wid = {wid: idx for idx, wid in enumerate(all_complex_wids)}
        seen: set[str] = set()
        kept_wids: list[str] = []
        kept_cols: list[int] = []
        for wid in canonical_filter:
            if wid in seen:
                continue
            col = complex_col_by_wid.get(wid)
            if col is None:
                continue
            seen.add(wid)
            kept_wids.append(wid)
            kept_cols.append(col)

        kept_cols_arr = np.asarray(kept_cols, dtype=np.int64)
        self.complex_wids = kept_wids
        self.substrate_wids = _fixture_wids(fixture.substrateWholeCellModelIDs)
        self.enzyme_wids = _fixture_wids(fixture.enzymeWholeCellModelIDs)
        self.protein_wids = _fixture_wids(polypeptide_state.monomerWholeCellModelIDs)
        self.rna_wids = _fixture_wids(fixture.rnaWholeCellModelIDs)

        complex_decay_reactions = np.asarray(fixture.complexDecayReactions, dtype=np.int64)
        protein_complex_monomer_composition = np.asarray(
            fixture.proteinComplexMonomerComposition, dtype=np.int64
        )
        protein_complex_rna_composition = np.asarray(
            fixture.proteinComplexRNAComposition, dtype=np.int64
        )

        self.complex_decay_reactions = complex_decay_reactions[:, kept_cols_arr]
        self.protein_complex_monomer_composition = protein_complex_monomer_composition[
            :, kept_cols_arr
        ]
        self.protein_complex_rna_composition = protein_complex_rna_composition[:, kept_cols_arr]

        self.substrate_index_atp = int(fixture.substrateIndexs_atp) - 1
        self.substrate_index_adp = int(fixture.substrateIndexs_adp) - 1
        self.substrate_index_phosphate = int(fixture.substrateIndexs_phosphate) - 1
        self.substrate_index_hydrogen = int(fixture.substrateIndexs_hydrogen) - 1
        self.substrate_index_water = int(fixture.substrateIndexs_water) - 1

        self.lon_protease_specific_rate = float(fixture.lonProteaseSpecificRate)
        self.lon_protease_energy_cost = float(fixture.lonProteaseEnergyCost)
        self.enzyme_index_lon_protease = int(fixture.enzymeIndexs_lonProtease) - 1
        self.enzyme_index_peptidases = (
            np.asarray(fixture.enzymeIndexs_peptidases, dtype=np.int64).reshape(-1) - 1
        )

        self._default_rate_per_s = float(self.parameters["complex_decay_rate_per_s"])
        self._complex_half_lives = {
            str(wid): float(seconds)
            for wid, seconds in (self.parameters.get("complex_half_lives") or {}).items()
        }
        for wid, half_life_s in self._complex_half_lives.items():
            if half_life_s <= 0.0:
                raise ValueError(f"complex_half_lives[{wid!r}] must be > 0, got {half_life_s}")

        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

        self._latent_rng = _Mcg16807(int(self.parameters["rng_seed"]) + 1)
        self._latent_enabled = bool(self.parameters["enable_latent_monomer_decay"])
        self._latent_monomers = np.asarray(fixture.monomers, dtype=np.int64).copy()
        self._latent_monomer_decay_reactions = np.asarray(
            fixture.monomerDecayReactions, dtype=np.int64
        )
        self._latent_monomer_lon_cleavages = np.asarray(
            fixture.monomerLonProteaseCleavages, dtype=np.int64
        ).reshape(-1)
        half_lives = np.asarray(protein_monomer_state.halfLives, dtype=np.float64).reshape(-1)
        latent_rates = np.full_like(half_lives, 1e6, dtype=np.float64)
        positive_half_life = half_lives > 0.0
        latent_rates[positive_half_life] = _LN2 / half_lives[positive_half_life]
        self._latent_monomer_decay_rates = np.minimum(latent_rates, 1e6)
        self._latent_cytosol_col = 0
        self._latent_terminal_cytosol_col = max(0, self._latent_monomers.shape[1] - 1)

        if self.complex_decay_reactions.shape[0] != len(self.substrate_wids):
            raise ValueError(
                "ProteinDecay substrate dimension mismatch: "
                f"{self.complex_decay_reactions.shape[0]} vs {len(self.substrate_wids)}"
            )
        if self.protein_complex_monomer_composition.shape[0] != len(self.protein_wids):
            raise ValueError(
                "ProteinDecay monomer dimension mismatch: "
                f"{self.protein_complex_monomer_composition.shape[0]} vs {len(self.protein_wids)}"
            )
        if self.protein_complex_rna_composition.shape[0] != len(self.rna_wids):
            raise ValueError(
                "ProteinDecay RNA dimension mismatch: "
                f"{self.protein_complex_rna_composition.shape[0]} vs {len(self.rna_wids)}"
            )
        if self._latent_monomer_decay_reactions.shape[0] != len(self.substrate_wids):
            self._latent_enabled = False
        if self._latent_monomer_decay_reactions.shape[1] != self._latent_monomers.shape[0]:
            self._latent_enabled = False
        if self._latent_monomers.shape[0] != len(self.protein_wids):
            # The replay process exposes the mature 482-monomer surface; fixture
            # latent tensors can include expanded species that are not 1:1 mappable
            # to that surface. Disable latent decay until a canonical projection exists.
            self._latent_enabled = False

    def ports_schema(self) -> dict[str, Any]:
        return {
            "complex": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.complex_wids
                }
            },
            "complexs": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.complex_wids
            },
            "monomers": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.protein_wids
            },
            "enzymes": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.enzyme_wids
            },
            "boundEnzymes": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.enzyme_wids
            },
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.substrate_wids
            },
            "protein": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.protein_wids
                }
            },
            "rna": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                    for wid in self.rna_wids
                }
            },
            "requests": {
                "karr_protein_decay_light": {
                    "ATP": {"_default": 0.0, "_updater": "set", "_emit": False},
                    "H2O": {"_default": 0.0, "_updater": "set", "_emit": False},
                }
            },
            "substrates_allocated": {
                "karr_protein_decay_light": {
                    "ATP": {"_default": 0.0, "_emit": False},
                    "H2O": {"_default": 0.0, "_emit": False},
                }
            },
        }

    def _complex_rates_per_s(self) -> np.ndarray:
        rates = np.full(len(self.complex_wids), self._default_rate_per_s, dtype=np.float64)
        for idx, wid in enumerate(self.complex_wids):
            half_life_s = self._complex_half_lives.get(wid)
            if half_life_s is not None:
                rates[idx] = _LN2 / half_life_s
        return rates

    def _latent_substrate_vector(self, states: dict[str, Any]) -> np.ndarray:
        substrates_store = states.get("substrates", {})
        if not isinstance(substrates_store, dict):
            return np.zeros(len(self.substrate_wids), dtype=np.float64)
        return np.asarray(
            [float(substrates_store.get(wid, 0.0)) for wid in self.substrate_wids],
            dtype=np.float64,
        )

    def _latent_enzyme_vector(self, states: dict[str, Any]) -> np.ndarray:
        enzyme_store = states.get("enzymes", {})
        if isinstance(enzyme_store, dict) and enzyme_store:
            return np.asarray(
                [float(enzyme_store.get(wid, 0.0)) for wid in self.enzyme_wids],
                dtype=np.float64,
            )
        return np.zeros(len(self.enzyme_wids), dtype=np.float64)

    def _latent_monomer_substrate_delta(
        self, timestep: float, states: dict[str, Any]
    ) -> np.ndarray:
        # Keep unit tests for the light process stable: activate only in replay
        # contexts that expose the monomer surface.
        if not self._latent_enabled or "monomers" not in states:
            return np.zeros(len(self.substrate_wids), dtype=np.int64)

        substrates = self._latent_substrate_vector(states)
        enzymes = self._latent_enzyme_vector(states)
        if enzymes.shape[0] <= self.enzyme_index_lon_protease:
            return np.zeros(len(self.substrate_wids), dtype=np.int64)

        monomers = self._latent_monomers
        decaying_rates = (
            monomers.astype(np.float64)
            * self._latent_monomer_decay_rates[:, np.newaxis]
            * float(timestep)
        )
        finite_decay = self._latent_monomer_decay_rates < 1e6
        for col in range(decaying_rates.shape[1]):
            if col in {self._latent_cytosol_col, self._latent_terminal_cytosol_col}:
                continue
            decaying_rates[finite_decay, col] = 0.0

        decaying = np.minimum(
            monomers,
            self._latent_rng.stochastic_round(decaying_rates),
        ).astype(np.int64)
        decaying_rates[decaying == 0] = 0.0
        if not np.any(decaying):
            return np.zeros(len(self.substrate_wids), dtype=np.int64)

        decayed = np.zeros_like(decaying, dtype=np.int64)
        i_energy = np.asarray(
            [
                self.substrate_index_atp,
                self.substrate_index_adp,
                self.substrate_index_phosphate,
                self.substrate_index_water,
                self.substrate_index_hydrogen,
            ],
            dtype=np.int64,
        )

        protease = (
            float(enzymes[self.enzyme_index_lon_protease])
            * float(timestep)
            * self.lon_protease_specific_rate
        )
        peptidase = int(
            self._latent_rng.stochastic_round(
                float(np.min(enzymes[self.enzyme_index_peptidases])) * float(timestep)
            ).item()
        )

        work_substrates = substrates.copy()
        flat_rates = decaying_rates.reshape(-1, order="F")
        flat_decaying = decaying.reshape(-1, order="F")
        flat_decayed = decayed.reshape(-1, order="F")
        n_rows = monomers.shape[0]

        while np.any(flat_decaying > 0):
            idx = self._latent_rng.randsample_one(flat_rates)
            if idx is None:
                break
            i_protein = idx % n_rows

            substrate_cost = -self._latent_monomer_decay_reactions[:, i_protein].astype(np.float64)
            lon_cleavages = float(self._latent_monomer_lon_cleavages[i_protein])
            lon_energy = self.lon_protease_energy_cost * lon_cleavages
            substrate_cost[i_energy] = (
                substrate_cost[i_energy]
                + np.asarray([1.0, -1.0, -1.0, 1.0, -1.0], dtype=np.float64) * lon_energy
            )

            if lon_cleavages <= 0.0:
                protease_gate = 1
            else:
                protease_gate = int(
                    self._latent_rng.stochastic_round(protease / lon_cleavages).item()
                )
            if (
                np.any(work_substrates[i_energy] < np.maximum(0.0, substrate_cost[i_energy]))
                or protease_gate < 1
                or peptidase < 1
            ):
                break

            flat_decaying[idx] -= 1
            flat_decayed[idx] += 1
            if flat_decaying[idx] <= 0:
                flat_rates[idx] = 0.0
            else:
                flat_rates[idx] = max(
                    0.0,
                    float(flat_rates[idx]) - self._latent_monomer_decay_rates[i_protein] * float(timestep),
                )

            work_substrates -= substrate_cost
            if lon_cleavages > 0.0:
                protease = max(0.0, protease - lon_cleavages)

        decayed = flat_decayed.reshape(decayed.shape, order="F")
        if not np.any(decayed):
            return np.zeros(len(self.substrate_wids), dtype=np.int64)

        self._latent_monomers = self._latent_monomers - decayed
        decayed_by_species = np.sum(decayed, axis=1, dtype=np.int64)
        delta = (self._latent_monomer_decay_reactions @ decayed_by_species).astype(np.float64)
        total_lon_energy = self.lon_protease_energy_cost * float(
            self._latent_monomer_lon_cleavages @ decayed_by_species
        )
        delta[i_energy] = (
            delta[i_energy]
            + np.asarray([-1.0, 1.0, 1.0, -1.0, 1.0], dtype=np.float64) * total_lon_energy
        )
        return np.rint(delta).astype(np.int64)

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        complex_store = states.get("complex", {})
        if isinstance(complex_store, dict):
            raw_complex_counts = complex_store.get("counts", {})
        else:
            raw_complex_counts = {}
        if not isinstance(raw_complex_counts, dict):
            raw_complex_counts = {}

        complex_counts = np.asarray(
            [
                max(0, int(float(raw_complex_counts.get(wid, 0.0))))
                for wid in self.complex_wids
            ],
            dtype=np.int64,
        )

        rates = self._complex_rates_per_s()
        expected = rates * complex_counts.astype(np.float64) * float(timestep)
        n_decay = self._rng.poisson(expected).astype(np.int64)
        n_decay = np.minimum(n_decay, complex_counts)

        sub_deltas = self.complex_decay_reactions @ n_decay
        latent_sub_deltas = self._latent_monomer_substrate_delta(timestep, states)
        total_sub_deltas = np.asarray(sub_deltas, dtype=np.int64) + np.asarray(
            latent_sub_deltas, dtype=np.int64
        )
        monomer_deltas = self.protein_complex_monomer_composition @ n_decay
        rna_deltas = self.protein_complex_rna_composition @ n_decay

        complex_update = {
            wid: float(-n_decay[i]) for i, wid in enumerate(self.complex_wids) if n_decay[i] > 0
        }
        protein_update = {
            wid: float(monomer_deltas[i])
            for i, wid in enumerate(self.protein_wids)
            if monomer_deltas[i] != 0
        }
        rna_update = {
            wid: float(rna_deltas[i]) for i, wid in enumerate(self.rna_wids) if rna_deltas[i] != 0
        }

        consume_atp_h2o = bool(self.parameters["consume_atp_h2o"])
        if consume_atp_h2o:
            atp_need = float(max(0.0, -float(total_sub_deltas[self.substrate_index_atp])))
            h2o_need = float(max(0.0, -float(total_sub_deltas[self.substrate_index_water])))
            if atp_need > 0.0 or h2o_need > 0.0:
                substrate_update = {
                    wid: float(total_sub_deltas[i])
                    for i, wid in enumerate(self.substrate_wids)
                    if total_sub_deltas[i] != 0
                }
            else:
                # Fixture extraction currently yields all-zero ATP/H2O rows for
                # filtered complexes. Avoid negative direct substrate writes when
                # allocator demand is zero for this tick.
                substrate_update = {
                    wid: float(total_sub_deltas[i])
                    for i, wid in enumerate(self.substrate_wids)
                    if total_sub_deltas[i] > 0
                }
        else:
            substrate_update = {}
            atp_need = 0.0
            h2o_need = 0.0

        update: dict[str, Any] = {
            "requests": {
                "karr_protein_decay_light": {
                    "ATP": atp_need,
                    "H2O": h2o_need,
                }
            }
        }
        if complex_update:
            update["complex"] = {"counts": complex_update}
        if substrate_update:
            update["substrates"] = substrate_update
        if protein_update:
            update["protein"] = {"counts": protein_update}
        if rna_update:
            update["rna"] = {"counts": rna_update}
        return update


__all__ = ["ProteinDecayLightProcess"]
