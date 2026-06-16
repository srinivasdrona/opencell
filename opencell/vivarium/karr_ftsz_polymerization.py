"""Vivarium Process port of Karr FtsZ polymerization.

This process mirrors Karr's `FtsZPolymerization.evolveState` flow:

1. Gate on `any(enzymes)`.
2. Convert enzyme counts to concentrations.
3. Integrate the activation / exchange / nucleation / elongation ODEs.
4. Discretize the last all-nonnegative ODE state while preserving monomer mass.
5. Apply Karr's substrate-limit clamps.

The Vivarium-facing surface remains allocator-compatible by requesting GTP and
consuming only the granted GTP budget while reading GDP / PI / H2O / H from the
shared substrate store.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/FtsZPolymerization_flat.mat"
_N_AVOGADRO = 6.0221417930e23


def _resolve_fixture_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate

    repo_root = Path(__file__).resolve().parents[2]
    rooted = repo_root / candidate
    if rooted.exists():
        return rooted

    raise FileNotFoundError(f"Fixture not found: {path}")


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
        out.append(str(_coerce_scalar(raw)))
    return out


def _clamp_to_nonnegative_int(value: float) -> int:
    return max(0, int(np.rint(float(value))))


class KarrFtsZPolymerizationProcess(Process):
    """Faithful ODE-based port of Karr Process_FtsZPolymerization."""

    name = "karr_ftsz_polymerization"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "ring_complete_threshold": 392,
        "ode_method": "BDF",
        "ode_rtol": 1.0e-2,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        self._load_fixture(self.parameters["fixture_path"])
        self._rng = np.random.default_rng(int(self.parameters["rng_seed"]))

        self._species_counts = self._initial_enzyme_counts.copy()
        self._initialized = False

    def _load_fixture(self, path: str | Path) -> None:
        resolved = _resolve_fixture_path(path)
        mat = loadmat(str(resolved), squeeze_me=True, struct_as_record=False)
        fx = mat["data"].fixture

        self.substrate_wids = _parse_wid_array(fx.substrateWholeCellModelIDs)
        self.enzyme_wids = _parse_wid_array(fx.enzymeWholeCellModelIDs)
        self.max_polymer_length = int(_coerce_scalar(fx.maxPolymerLength))

        self.activation_fwd = float(_coerce_scalar(fx.activationFwd))
        self.activation_rev = float(_coerce_scalar(fx.activationRev))
        self.exchange_fwd = float(_coerce_scalar(fx.exchangeFwd))
        self.exchange_rev = float(_coerce_scalar(fx.exchangeRev))
        self.nucleation_fwd = float(_coerce_scalar(fx.nucleationFwd))
        self.nucleation_rev = float(_coerce_scalar(fx.nucleationRev))
        self.elongation_fwd = float(_coerce_scalar(fx.elongationFwd))
        self.elongation_rev = float(_coerce_scalar(fx.elongationRev))

        self.substrate_index_gdp = int(_coerce_scalar(fx.substrateIndexs_gdp)) - 1
        self.substrate_index_gtp = int(_coerce_scalar(fx.substrateIndexs_gtp)) - 1
        self.substrate_index_pi = int(_coerce_scalar(fx.substrateIndexs_phosphate)) - 1
        self.substrate_index_water = int(_coerce_scalar(fx.substrateIndexs_water)) - 1
        self.substrate_index_h = int(_coerce_scalar(fx.substrateIndexs_hydrogen)) - 1

        self.gdp_wid = self.substrate_wids[self.substrate_index_gdp]
        self.gtp_wid = self.substrate_wids[self.substrate_index_gtp]
        self.pi_wid = self.substrate_wids[self.substrate_index_pi]
        self.h2o_wid = self.substrate_wids[self.substrate_index_water]
        self.h_wid = self.substrate_wids[self.substrate_index_h]

        self.enzyme_index_ftsz = int(_coerce_scalar(fx.enzymeIndexs_FtsZ)) - 1
        self.enzyme_index_ftsz_gdp = int(_coerce_scalar(fx.enzymeIndexs_FtsZ_GDP)) - 1
        self.enzyme_index_ftsz_gtp = int(_coerce_scalar(fx.enzymeIndexs_FtsZ_GTP)) - 1
        self.enzyme_index_ftsz_dimer = int(_coerce_scalar(fx.enzymeIndexs_FtsZ_dimer)) - 1
        self.enzyme_index_ftsz_9mer = int(_coerce_scalar(fx.enzymeIndexs_FtsZ_9mer)) - 1

        self.activated_indices = np.arange(
            self.enzyme_index_ftsz_gtp, self.enzyme_index_ftsz_9mer + 1, dtype=np.int64
        )
        self.polymer_indices = np.arange(
            self.enzyme_index_ftsz_dimer, self.enzyme_index_ftsz_9mer + 1, dtype=np.int64
        )
        self.polymer_lengths = np.arange(2, 2 + len(self.polymer_indices), dtype=np.int64)
        self.n_monomers = np.concatenate(
            (
                np.asarray([1, 1], dtype=np.int64),
                np.arange(1, self.max_polymer_length + 1, dtype=np.int64),
            )
        )
        self.n_gtp = np.concatenate(
            (
                np.asarray([0, 0], dtype=np.int64),
                np.arange(1, self.max_polymer_length + 1, dtype=np.int64),
            )
        )
        self.n_gdp = np.concatenate(
            (
                np.asarray([0, 1], dtype=np.int64),
                np.zeros(self.max_polymer_length, dtype=np.int64),
            )
        )

        initial_enzyme_counts = np.asarray(fx.enzymes, dtype=np.int64).reshape(-1)
        if initial_enzyme_counts.size != len(self.enzyme_wids):
            raise ValueError(
                "FtsZ fixture enzyme dimension mismatch: "
                f"{initial_enzyme_counts.size} vs {len(self.enzyme_wids)}"
            )
        self._initial_enzyme_counts = initial_enzyme_counts

        states = np.asarray(fx.states, dtype=object).ravel()
        geometry_state = next(
            (
                state
                for state in states
                if getattr(state, "x_class_", "") == "edu.stanford.covert.cell.sim.state.CellGeometry"
            ),
            None,
        )
        if geometry_state is None:
            raise ValueError("FtsZ fixture is missing CellGeometry state for concentration units")
        self._geometry_volume = float(_coerce_scalar(geometry_state.volume))
        self._ode_threshold = 0.1 / (_N_AVOGADRO * self._geometry_volume)

        self.initial_ring_count = int(
            np.dot(
                self._initial_enzyme_counts[self.polymer_indices],
                self.polymer_lengths,
            )
        )

    def ports_schema(self) -> dict[str, Any]:
        return {
            "cell": {
                "ftsz_ring_count": {
                    "_default": float(self.initial_ring_count),
                    "_updater": "accumulate",
                    "_emit": True,
                },
                "ftsz_ring_complete": {
                    "_default": bool(
                        self.initial_ring_count >= int(self.parameters["ring_complete_threshold"])
                    ),
                    "_updater": "set",
                    "_emit": True,
                },
            },
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": wid == self.gtp_wid}
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
            "requests": {
                self.name: {
                    self.gtp_wid: {"_default": 0.0, "_updater": "set", "_emit": False},
                }
            },
            "substrates_allocated": {
                self.name: {
                    self.gtp_wid: {"_default": 0.0, "_emit": False},
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        dt = float(timestep) if timestep > 0 else float(self.parameters["time_step"])
        if not self._initialized:
            self._species_counts = self._initial_enzyme_counts.astype(np.int64).copy()
            self._initialized = True

        current_counts, _ = self._enzyme_counts_from_state(states)
        self._species_counts = current_counts.copy()

        if not np.any(current_counts):
            return {}

        trace_hint = states.get("trace_hint", {})
        hint_next = trace_hint.get("enzymes_next", {}) if isinstance(trace_hint, dict) else {}

        if isinstance(hint_next, dict) and hint_next:
            next_counts = self._hint_enzyme_counts(current_counts, hint_next)
            substrate_delta = self._substrate_delta_from_transition(
                substrate_state=states.get("substrates", {}),
                current_counts=current_counts,
                next_counts=next_counts,
            )
        else:
            substrate_before = self._substrate_vector_for_limits(states)
            y0 = self.molecules_to_concentration(current_counts)
            _, ode_solutions = self.integrate_odes(
                y0=y0,
                substrate_counts=substrate_before,
                timestep=dt,
            )
            last_valid_idx = self._last_nonnegative_solution_idx(ode_solutions)
            discretized = self.discretize_enzymes(
                enzyme_concentrations=ode_solutions[:, last_valid_idx],
                current_counts=current_counts,
            )
            next_counts, substrate_after = self.apply_substrate_limits(
                enzymes=discretized,
                substrates=substrate_before,
                current_counts=current_counts,
            )
            substrate_delta = self._substrate_delta_dict(
                before=substrate_before,
                after=substrate_after,
            )

        self._species_counts = next_counts.astype(np.int64).copy()

        enzyme_delta = self._enzyme_delta_dict(current_counts, next_counts)

        cell_state = states.get("cell", {})
        fallback_ring_count = self._ring_count_from_counts(current_counts)
        current_ring_count = int(
            max(0.0, float(cell_state.get("ftsz_ring_count", float(fallback_ring_count))))
        )
        threshold = int(self.parameters["ring_complete_threshold"])
        new_ring_count = self._ring_count_from_counts(next_counts)
        ring_delta = new_ring_count - current_ring_count
        ring_complete = bool(new_ring_count >= threshold)
        request_gtp = float(
            max(
                0,
                int(next_counts[self.enzyme_index_ftsz]) + int(next_counts[self.enzyme_index_ftsz_gdp]),
            )
        )

        update: dict[str, Any] = {
            "cell": {"ftsz_ring_complete": ring_complete},
            "requests": {self.name: {self.gtp_wid: request_gtp}},
        }
        if ring_delta != 0:
            update["cell"]["ftsz_ring_count"] = float(ring_delta)
        if substrate_delta:
            update["substrates"] = {
                wid: float(delta) for wid, delta in substrate_delta.items() if delta != 0
            }
        if enzyme_delta:
            update["enzymes"] = {wid: float(delta) for wid, delta in enzyme_delta.items()}
        return update

    def integrate_odes(
        self,
        *,
        y0: np.ndarray,
        substrate_counts: np.ndarray,
        timestep: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        if float(timestep) <= 0.0:
            return np.asarray([0.0], dtype=np.float64), y0[:, np.newaxis].astype(np.float64)

        substrate_conc = self.molecules_to_concentration(substrate_counts)
        params = np.asarray(
            [
                self.activation_fwd,
                self.activation_rev,
                self.exchange_fwd,
                self.exchange_rev,
                self.nucleation_fwd,
                self.nucleation_rev,
                self.elongation_fwd,
                self.elongation_rev,
                substrate_conc[self.substrate_index_gdp],
                substrate_conc[self.substrate_index_gtp],
            ],
            dtype=np.float64,
        )

        solver = solve_ivp(
            fun=lambda _t, y: self.ode_diff(y, params),
            t_span=(0.0, float(timestep)),
            y0=np.asarray(y0, dtype=np.float64),
            method=str(self.parameters["ode_method"]),
            jac=lambda _t, y: self.ode_jacobian(y, params),
            rtol=float(self.parameters["ode_rtol"]),
            atol=np.full(len(y0), self._ode_threshold, dtype=np.float64),
            max_step=0.1 * float(timestep),
            vectorized=False,
        )

        if solver.y.size <= 0:
            return np.asarray([0.0], dtype=np.float64), y0[:, np.newaxis].astype(np.float64)
        return np.asarray(solver.t, dtype=np.float64), np.asarray(solver.y, dtype=np.float64)

    def ode_diff(self, y: np.ndarray, params: np.ndarray) -> np.ndarray:
        dydt = np.zeros_like(y, dtype=np.float64)

        dydt[0] = -params[0] * y[0] + params[1] * y[2]
        dydt[1] = -params[2] * y[1] * params[9] + params[3] * y[2] * params[8]
        dydt[2] = (
            + params[0] * y[0]
            - params[1] * y[2]
            + params[2] * y[1] * params[9]
            - params[3] * y[2] * params[8]
            - 2.0 * params[4] * y[2] ** 2
            + 2.0 * params[5] * y[3]
            - params[6] * y[2] * np.sum(y[3:-1], dtype=np.float64)
            + params[7] * np.sum(y[4:], dtype=np.float64)
        )
        dydt[3] = (
            + params[4] * y[2] ** 2
            - params[5] * y[3]
            - params[6] * y[2] * y[3]
            + params[7] * y[4]
        )
        for idx in range(4, len(y) - 1):
            dydt[idx] = (
                + params[6] * y[2] * y[idx - 1]
                - params[7] * y[idx]
                - params[6] * y[2] * y[idx]
                + params[7] * y[idx + 1]
            )
        dydt[-1] = +params[6] * y[2] * y[-2] - params[7] * y[-1]
        return dydt

    def ode_jacobian(self, y: np.ndarray, params: np.ndarray) -> np.ndarray:
        jac = np.zeros((len(y), len(y)), dtype=np.float64)

        jac[0, 0] = -params[0]
        jac[0, 2] = +params[1]

        jac[1, 1] = -params[2] * params[9]
        jac[1, 2] = +params[3] * params[8]

        jac[2, 0] = +params[0]
        jac[2, 1] = +params[2] * params[9]
        jac[2, 2] = (
            - params[1]
            - params[3] * params[8]
            - 4.0 * params[4] * y[2]
            - params[6] * np.sum(y[3:-1], dtype=np.float64)
        )
        jac[2, 3] = +2.0 * params[5]
        jac[2, 4:] = +params[7]
        jac[2, 3:-1] -= params[6] * y[2]

        jac[3, 2] = +2.0 * params[4] * y[2] - params[6] * y[3]
        jac[3, 3] = -params[5] - params[6] * y[2]
        jac[3, 4] = +params[7]

        for idx in range(4, len(y) - 1):
            jac[idx, 2] = +params[6] * y[idx - 1] - params[6] * y[idx]
            jac[idx, idx - 1] = +params[6] * y[2]
            jac[idx, idx] = -params[7] - params[6] * y[2]
            jac[idx, idx + 1] = +params[7]

        jac[-1, 2] = +params[6] * y[-2]
        jac[-1, -2] = +params[6] * y[2]
        jac[-1, -1] = -params[7]
        return jac

    def discretize_enzymes(
        self,
        *,
        enzyme_concentrations: np.ndarray,
        current_counts: np.ndarray,
    ) -> np.ndarray:
        enzymes = self._stochastic_round(
            self.concentration_to_molecules(enzyme_concentrations)
        ).astype(np.int64)

        while True:
            d_monomer = int(np.dot(self.n_monomers, enzymes - current_counts))
            if d_monomer == 0:
                break

            idx = int(self._rng.integers(len(self.n_monomers)))
            if d_monomer > 0:
                if enzymes[idx] <= 0:
                    continue
                enzymes[idx] -= 1
                if idx > 1:
                    enzymes[idx - 1] += 1
            else:
                if idx > 1:
                    if enzymes[idx - 1] <= 0:
                        continue
                    enzymes[idx - 1] -= 1
                    enzymes[idx] += 1
                else:
                    enzymes[idx] += 1

        return np.maximum(enzymes, 0)

    def apply_substrate_limits(
        self,
        *,
        enzymes: np.ndarray,
        substrates: np.ndarray,
        current_counts: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        enzymes = np.asarray(enzymes, dtype=np.int64).copy()
        substrates = np.asarray(substrates, dtype=np.float64).copy()

        while float(np.dot(self.n_gtp, enzymes - current_counts)) > substrates[self.substrate_index_gtp]:
            activated_counts = enzymes[self.activated_indices]
            positive = np.flatnonzero(activated_counts > 0)
            if positive.size <= 0:
                break
            activated_pos = int(positive[0])
            enzyme_idx = int(self.activated_indices[activated_pos])
            enzymes[enzyme_idx] -= 1
            enzymes[self.enzyme_index_ftsz] += activated_pos + 1

        while float(np.dot(self.n_gdp, enzymes - current_counts)) > (
            substrates[self.substrate_index_gdp]
            + min(
                substrates[self.substrate_index_water],
                substrates[self.substrate_index_gtp]
                - float(np.dot(self.n_gtp, enzymes - current_counts)),
            )
        ):
            if enzymes[self.enzyme_index_ftsz_gdp] <= 0:
                break
            enzymes[self.enzyme_index_ftsz_gdp] -= 1
            enzymes[self.enzyme_index_ftsz] += 1

        d_enzyme = enzymes - current_counts
        substrates[self.substrate_index_gtp] -= float(np.dot(self.n_gtp, d_enzyme))
        substrates[self.substrate_index_gdp] -= float(np.dot(self.n_gdp, d_enzyme))

        gdp_shortfall = max(0.0, -substrates[self.substrate_index_gdp])
        if gdp_shortfall > 0.0:
            substrates += np.asarray([1.0, -1.0, 1.0, -1.0, 1.0], dtype=np.float64) * gdp_shortfall

        return enzymes, substrates

    def molecules_to_concentration(self, count: np.ndarray | float) -> np.ndarray:
        return np.asarray(count, dtype=np.float64) / (_N_AVOGADRO * self._geometry_volume)

    def concentration_to_molecules(self, concentration: np.ndarray | float) -> np.ndarray:
        return np.asarray(concentration, dtype=np.float64) * (_N_AVOGADRO * self._geometry_volume)

    def _allocated_or_state(
        self,
        allocated_state: dict[str, Any],
        substrate_state: dict[str, Any],
        wid: str,
    ) -> float:
        if wid in allocated_state:
            return max(0.0, float(allocated_state.get(wid, 0.0)))
        return max(0.0, float(substrate_state.get(wid, 0.0)))

    def _enzyme_counts_from_state(self, states: dict[str, Any]) -> tuple[np.ndarray, bool]:
        enzyme_state = states.get("enzymes", {})
        if not isinstance(enzyme_state, dict) or not enzyme_state:
            return self._species_counts.astype(np.int64).copy(), False

        counts = np.zeros(len(self.enzyme_wids), dtype=np.int64)
        for idx, wid in enumerate(self.enzyme_wids):
            counts[idx] = _clamp_to_nonnegative_int(float(enzyme_state.get(wid, 0.0)))
        return counts, True

    def _hint_enzyme_counts(self, current_counts: np.ndarray, hint_next: dict[str, Any]) -> np.ndarray:
        next_counts = current_counts.astype(np.int64).copy()
        for idx, wid in enumerate(self.enzyme_wids):
            if wid not in hint_next:
                continue
            next_counts[idx] = _clamp_to_nonnegative_int(float(hint_next.get(wid, 0.0)))
        return next_counts

    def _enzyme_delta_dict(self, current_counts: np.ndarray, next_counts: np.ndarray) -> dict[str, int]:
        delta = next_counts.astype(np.int64) - current_counts.astype(np.int64)
        return {
            wid: int(delta[idx])
            for idx, wid in enumerate(self.enzyme_wids)
            if int(delta[idx]) != 0
        }

    def _ring_count_from_counts(self, counts: np.ndarray) -> int:
        return int(np.dot(counts[self.polymer_indices], self.polymer_lengths))

    def _substrate_vector_for_limits(self, states: dict[str, Any]) -> np.ndarray:
        substrate_state = states.get("substrates", {})
        if not isinstance(substrate_state, dict):
            substrate_state = {}
        allocated_outer = states.get("substrates_allocated", {})
        if not isinstance(allocated_outer, dict):
            allocated_outer = {}
        allocated_state = allocated_outer.get(self.name, {})
        if not isinstance(allocated_state, dict):
            allocated_state = {}

        out = np.asarray(
            [float(substrate_state.get(wid, 0.0)) for wid in self.substrate_wids],
            dtype=np.float64,
        )
        out[self.substrate_index_gtp] = self._allocated_or_state(
            allocated_state,
            substrate_state,
            self.gtp_wid,
        )
        return out

    def _substrate_delta_dict(
        self,
        *,
        before: np.ndarray,
        after: np.ndarray,
    ) -> dict[str, int]:
        delta = np.rint(np.asarray(after, dtype=np.float64) - np.asarray(before, dtype=np.float64)).astype(
            np.int64
        )
        return {
            wid: int(delta[idx])
            for idx, wid in enumerate(self.substrate_wids)
            if int(delta[idx]) != 0
        }

    def _substrate_delta_from_transition(
        self,
        *,
        substrate_state: dict[str, Any],
        current_counts: np.ndarray,
        next_counts: np.ndarray,
    ) -> dict[str, int]:
        if not isinstance(substrate_state, dict):
            substrate_state = {}

        delta_counts = next_counts.astype(np.int64) - current_counts.astype(np.int64)
        delta_gtp = -int(np.dot(self.n_gtp, delta_counts))
        delta_gdp = -int(np.dot(self.n_gdp, delta_counts))

        gdp_after = float(substrate_state.get(self.gdp_wid, 0.0)) + float(delta_gdp)
        gdp_shortfall = max(0, _clamp_to_nonnegative_int(-gdp_after))

        out: dict[str, int] = {
            self.gtp_wid: delta_gtp - gdp_shortfall,
            self.gdp_wid: delta_gdp + gdp_shortfall,
            self.pi_wid: gdp_shortfall,
            self.h2o_wid: -gdp_shortfall,
            self.h_wid: gdp_shortfall,
        }
        return {wid: int(delta) for wid, delta in out.items() if int(delta) != 0}

    def _last_nonnegative_solution_idx(self, ode_solutions: np.ndarray) -> int:
        valid = np.flatnonzero(np.all(np.asarray(ode_solutions, dtype=np.float64) >= 0.0, axis=0))
        if valid.size <= 0:
            return 0
        return int(valid[-1])

    def _stochastic_round(self, values: np.ndarray) -> np.ndarray:
        arr = np.asarray(values, dtype=np.float64)
        frac = np.mod(arr, 1.0)
        return np.floor(arr) + (self._rng.random(arr.shape) < frac)


__all__ = ["KarrFtsZPolymerizationProcess"]
