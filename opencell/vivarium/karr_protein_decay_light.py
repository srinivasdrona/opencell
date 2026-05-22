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
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        fixture = _load_flat_fixture(Path(self.parameters["fixture_path"]))

        protein_complex_state = _fixture_state_by_class(
            fixture, "edu.stanford.covert.cell.sim.state.ProteinComplex"
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
        self.substrate_index_water = int(fixture.substrateIndexs_water) - 1

        self._default_rate_per_s = float(self.parameters["complex_decay_rate_per_s"])
        self._complex_half_lives = {
            str(wid): float(seconds)
            for wid, seconds in (self.parameters.get("complex_half_lives") or {}).items()
        }
        for wid, half_life_s in self._complex_half_lives.items():
            if half_life_s <= 0.0:
                raise ValueError(f"complex_half_lives[{wid!r}] must be > 0, got {half_life_s}")

        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

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

    def ports_schema(self) -> dict[str, Any]:
        return {
            "complex": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.complex_wids
                }
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
                    "ATP": {"_default": 0.0, "_updater": "accumulate", "_emit": False},
                    "H2O": {"_default": 0.0, "_updater": "accumulate", "_emit": False},
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

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        complex_counts = np.asarray(
            [
                max(0, int(float(states["complex"]["counts"].get(wid, 0.0))))
                for wid in self.complex_wids
            ],
            dtype=np.int64,
        )

        rates = self._complex_rates_per_s()
        expected = rates * complex_counts.astype(np.float64) * float(timestep)
        n_decay = self._rng.poisson(expected).astype(np.int64)
        n_decay = np.minimum(n_decay, complex_counts)

        sub_deltas = self.complex_decay_reactions @ n_decay
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
            substrate_update = {
                wid: float(sub_deltas[i])
                for i, wid in enumerate(self.substrate_wids)
                if sub_deltas[i] != 0
            }
            atp_need = float(abs(sub_deltas[self.substrate_index_atp]))
            h2o_need = float(abs(sub_deltas[self.substrate_index_water]))
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
