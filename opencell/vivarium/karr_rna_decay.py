"""Vivarium Process for Karr RNADecay (process #13), light variant.

Karr-light v1 scope:
- First-order stochastic RNA decay per species.
- Allocation-gated H2O consumption via KarrAllocationStep contract.
- RNA count decrements plus substrate/byproduct stoichiometric deltas from
  `RnaDecay_flat.mat` when available.

Deferred (v2):
- Explicit ribonuclease and peptidyl-tRNA hydrolase enzyme activity limits.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "data" / "karr_fixtures" / "per_process"
_RNA_DECAY_FLAT = _FIXTURE_DIR / "RnaDecay_flat.mat"
_RNA_STATE_CLASS = "edu.stanford.covert.cell.sim.state.Rna"
_LN2 = math.log(2.0)


def _load_flat_fixture(path: Path) -> object:  # noqa: ANN401 - matlab struct dynamic
    return loadmat(str(path), squeeze_me=True, struct_as_record=False)["data"].fixture


def _resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    rooted = Path(__file__).resolve().parents[2] / candidate
    if rooted.exists():
        return rooted

    return candidate


def _to_str_list(values: object) -> list[str]:
    raw = np.asarray(values, dtype=object).ravel()
    out: list[str] = []
    for value in raw:
        item: object = value
        while isinstance(item, np.ndarray):
            if item.size == 0:
                item = ""
                break
            item = item.flat[0]
        out.append(str(item))
    return out


def _fixture_state_by_class(
    fixture: object,
    class_name: str,
) -> object:  # noqa: ANN401 - matlab struct dynamic
    for state in np.asarray(fixture.states, dtype=object).ravel():
        if getattr(state, "x_class_", "") == class_name:
            return state
    raise ValueError(f"Fixture state not found: {class_name}")


class RnaDecayLightProcess(Process):
    """Karr RNADecay process #13, light allocation-aware variant."""

    name = "karr_rna_decay"
    defaults: dict[str, Any] = {
        "fixture_path": str(_RNA_DECAY_FLAT),
        "rng_seed": 0,
        "time_step": 1.0,
        # Guard against invalid tiny sentinel values in some fixture half-life slots.
        "min_valid_half_life_s": 1.0e-6,
        "emit_substrate_stoich": True,
        # Fixture-absent fallback parameters.
        "fallback_rna_ids": [],
        "fallback_rna_type_by_wid": {},
        "fallback_half_life_min": {
            "mRNA": 4.5,
            "rRNA": 150.0,
            "sRNA": 89.0,
            "tRNA": 45.0,
        },
        # If False, fallback omits substrate/H2O deltas (documented approximation).
        "fallback_consume_h2o": False,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._rng_seed = int(self.parameters["rng_seed"])
        self._rng = np.random.RandomState(self._rng_seed)

        fixture_path = _resolve_path(self.parameters["fixture_path"])
        if fixture_path.exists():
            self._load_from_fixture(fixture_path)
        else:
            self._load_from_fallback()

        if self.decay_reactions.shape != (len(self.rna_wids), len(self.substrate_wids)):
            raise ValueError(
                "RnaDecay stoichiometry dimension mismatch: "
                f"{self.decay_reactions.shape} vs "
                f"({len(self.rna_wids)}, {len(self.substrate_wids)})"
            )
        self._rng = np.random.RandomState(self._rng_seed)

    def _load_from_fixture(self, fixture_path: Path) -> None:
        fixture = _load_flat_fixture(fixture_path)
        rna_state = _fixture_state_by_class(fixture, _RNA_STATE_CLASS)

        self.rna_wids = _to_str_list(rna_state.wholeCellModelIDs)
        self.substrate_wids = _to_str_list(fixture.substrateWholeCellModelIDs)

        half_lives = np.asarray(rna_state.halfLives, dtype=np.float64).reshape(-1)
        if half_lives.size != len(self.rna_wids):
            raise ValueError(
                "RnaDecay half-life vector length mismatch: "
                f"{half_lives.size} vs {len(self.rna_wids)}"
            )

        min_valid_half_life_s = float(self.parameters["min_valid_half_life_s"])
        valid_half_life = np.isfinite(half_lives) & (half_lives > min_valid_half_life_s)
        rates = np.zeros_like(half_lives, dtype=np.float64)
        rates[valid_half_life] = _LN2 / half_lives[valid_half_life]
        self.decay_rates_per_s = rates

        stoich = np.asarray(fixture.decayReactions, dtype=np.int64)
        if stoich.shape == (len(self.substrate_wids), len(self.rna_wids)):
            stoich = stoich.T
        self.decay_reactions = stoich

        water_idx_raw = getattr(fixture, "substrateIndexs_water", None)
        if water_idx_raw is not None:
            self.substrate_index_water = int(water_idx_raw) - 1
        else:
            try:
                self.substrate_index_water = self.substrate_wids.index("H2O")
            except ValueError as exc:
                raise ValueError("H2O index unavailable in RnaDecay fixture") from exc

        self.water_need_per_decay = np.clip(
            -self.decay_reactions[:, self.substrate_index_water], a_min=0, a_max=None
        ).astype(np.int64)
        self._fixture_rna_counts = np.asarray(getattr(fixture, "RNAs", np.zeros(len(self.rna_wids))), dtype=np.int64).reshape(-1)[: len(self.rna_wids)]
        self._rng_seed = int(getattr(fixture, "seed", self._rng_seed))

    def _load_from_fallback(self) -> None:
        self.rna_wids = [str(wid) for wid in self.parameters.get("fallback_rna_ids", [])]
        if not self.rna_wids:
            raise FileNotFoundError(
                "RnaDecay fixture not found and fallback_rna_ids is empty; cannot initialize."
            )

        type_by_wid = {
            str(wid): str(rna_type)
            for wid, rna_type in (self.parameters.get("fallback_rna_type_by_wid") or {}).items()
        }
        half_life_min = {
            str(key): float(val)
            for key, val in (self.parameters.get("fallback_half_life_min") or {}).items()
        }
        default_half_life_min = float(half_life_min.get("mRNA", 4.5))

        half_lives_s = np.asarray(
            [
                60.0 * float(half_life_min.get(type_by_wid.get(wid, "mRNA"), default_half_life_min))
                for wid in self.rna_wids
            ],
            dtype=np.float64,
        )
        self.decay_rates_per_s = _LN2 / half_lives_s

        self.substrate_wids = ["H2O"]
        self.substrate_index_water = 0
        self.decay_reactions = np.zeros((len(self.rna_wids), 1), dtype=np.int64)
        if bool(self.parameters.get("fallback_consume_h2o", False)):
            self.decay_reactions[:, 0] = -1

        self.water_need_per_decay = np.clip(-self.decay_reactions[:, 0], a_min=0, a_max=None)
        self._fixture_rna_counts = np.zeros(len(self.rna_wids), dtype=np.int64)

    def ports_schema(self) -> dict[str, Any]:
        return {
            "rna": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.rna_wids
                }
            },
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                for wid in self.substrate_wids
            },
            "requests": {
                self.name: {
                    "H2O": {"_default": 0.0, "_updater": "set", "_emit": False},
                }
            },
            "substrates_allocated": {
                self.name: {
                    "H2O": {"_default": 0.0, "_emit": False},
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        rna_counts = np.asarray(
            [
                max(0, int(float(states.get("rna", {}).get("counts", {}).get(wid, 0.0))))
                for wid in self.rna_wids
            ],
            dtype=np.int64,
        )
        if not np.any(rna_counts):
            rna_counts = self._fixture_rna_counts

        expected = self.decay_rates_per_s * rna_counts.astype(np.float64) * float(timestep)
        sampled_decay = self._rng.poisson(expected).astype(np.int64)
        sampled_decay = np.minimum(sampled_decay, rna_counts)

        # Karr RNADecay hydrolysis uses water as the sole reactant;
        # allocation bounds this H2O requirement each tick.
        raw_h2o_need = float(np.dot(self.water_need_per_decay, sampled_decay))
        allocated_h2o = max(
            0.0,
            float(
                states.get("substrates_allocated", {})
                .get(self.name, {})
                .get("H2O", 0.0)
            ),
        )

        decay_events = sampled_decay.copy()
        if raw_h2o_need > 0.0:
            if allocated_h2o <= 0.0:
                decay_events[:] = 0
            elif allocated_h2o < raw_h2o_need:
                scale = allocated_h2o / raw_h2o_need
                decay_events = np.floor(decay_events.astype(np.float64) * scale).astype(np.int64)

        update: dict[str, Any] = {
            "requests": {
                self.name: {
                    "H2O": raw_h2o_need,
                }
            }
        }

        if np.any(decay_events > 0):
            rna_delta = -decay_events
            rna_update = {
                wid: float(rna_delta[i]) for i, wid in enumerate(self.rna_wids) if rna_delta[i] != 0
            }
            if rna_update:
                update["rna"] = {"counts": rna_update}

            if bool(self.parameters.get("emit_substrate_stoich", True)):
                substrate_delta = decay_events @ self.decay_reactions
                substrate_update = {
                    wid: float(substrate_delta[i])
                    for i, wid in enumerate(self.substrate_wids)
                    if substrate_delta[i] != 0
                }
                if substrate_update:
                    update["substrates"] = substrate_update

        return update


__all__ = ["RnaDecayLightProcess"]
