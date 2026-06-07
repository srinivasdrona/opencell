"""Vivarium Process port of Karr FtsZ polymerization (Karr-light v1).

This process models FtsZ monomer activation plus reversible nucleation and
elongation into 2-9mer GTP polymers. It emits a compact cytokinesis-coupling
state:

- ``cell.ftsz_ring_count``: polymerized FtsZ subunit count in 2-9mer species
- ``cell.ftsz_ring_complete``: true when ring count reaches threshold

Karr-light v1 scope:
- Uses fixture-calibrated rates and stochastic events.
- Tracks the 11 enzyme-state counts from the FtsZPolymerization fixture.
- Consumes GTP through the KarrAllocationStep request/allocation protocol.

Deferred to v2:
- Full MATLAB ODE/discretization scheme and geometry-coupled FtsZRing edges.
- Detailed hydrolysis bookkeeping beyond GTP activation demand.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/FtsZPolymerization_flat.mat"


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
        token = _coerce_scalar(raw)
        out.append(str(token))
    return out


def _clamp_to_nonnegative_int(value: float) -> int:
    return max(0, int(np.rint(float(value))))


class KarrFtsZPolymerizationProcess(Process):
    """Karr Process_FtsZPolymerization (light stochastic port)."""

    name = "karr_ftsz_polymerization"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        # Default from Karr trace tail mean (~392.3 polymerized subunits).
        "ring_complete_threshold": 392,
        # Rate scales tune fixture rates to per-second stochastic event counts.
        "activation_rate_scale": 1.0,
        "deactivation_rate_scale": 1.0,
        "nucleation_forward_scale": 1.2e8,
        "nucleation_reverse_scale": 80.0,
        "elongation_forward_scale": 8.0e8,
        "elongation_reverse_scale": 200.0,
        # Light homeostasis guard to keep ring count near Karr steady-state.
        "homeostasis_strength": 0.04,
        "homeostasis_cap": 8,
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
        self.nucleation_fwd = float(_coerce_scalar(fx.nucleationFwd))
        self.nucleation_rev = float(_coerce_scalar(fx.nucleationRev))
        self.elongation_fwd = float(_coerce_scalar(fx.elongationFwd))
        self.elongation_rev = float(_coerce_scalar(fx.elongationRev))
        self.exchange_fwd = float(_coerce_scalar(fx.exchangeFwd))
        self.exchange_rev = float(_coerce_scalar(fx.exchangeRev))

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

        self.enzyme_index_ftsz_gdp = int(_coerce_scalar(fx.enzymeIndexs_FtsZ_GDP)) - 1
        self.enzyme_index_ftsz_gtp = int(_coerce_scalar(fx.enzymeIndexs_FtsZ_GTP)) - 1
        self.enzyme_index_ftsz = int(_coerce_scalar(fx.enzymeIndexs_FtsZ)) - 1
        self.enzyme_index_ftsz_dimer = int(_coerce_scalar(fx.enzymeIndexs_FtsZ_dimer)) - 1
        self.enzyme_index_ftsz_9mer = int(_coerce_scalar(fx.enzymeIndexs_FtsZ_9mer)) - 1

        self.polymer_indices = np.arange(
            self.enzyme_index_ftsz_dimer, self.enzyme_index_ftsz_9mer + 1, dtype=np.int64
        )
        self.polymer_lengths = np.arange(2, 2 + len(self.polymer_indices), dtype=np.int64)

        initial_enzyme_counts = np.asarray(fx.enzymes, dtype=np.int64).reshape(-1)
        if initial_enzyme_counts.size != len(self.enzyme_wids):
            raise ValueError(
                "FtsZ fixture enzyme dimension mismatch: "
                f"{initial_enzyme_counts.size} vs {len(self.enzyme_wids)}"
            )
        self._initial_enzyme_counts = initial_enzyme_counts
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
                # Sole-writer boolean gate for downstream cytokinesis coupling.
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

        current_counts, counts_from_state = self._enzyme_counts_from_state(states)
        self._species_counts = current_counts.copy()

        next_counts = current_counts.copy()
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
            allocated_gtp = self._allocated_or_state(
                states.get("substrates_allocated", {}).get(self.name, {}),
                states.get("substrates", {}),
                self.gtp_wid,
            )
            gtp_budget = max(0, int(math.floor(allocated_gtp)))
            substrate_delta = {}
            self._apply_stochastic_transitions(
                dt=dt,
                gtp_budget=gtp_budget,
                substrate_delta=substrate_delta,
            )
            next_counts = self._species_counts.copy()
            if counts_from_state:
                substrate_delta = self._substrate_delta_from_transition(
                    substrate_state=states.get("substrates", {}),
                    current_counts=current_counts,
                    next_counts=next_counts,
                )

        self._species_counts = next_counts.copy()

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

    def _allocated_or_state(
        self,
        allocated_state: dict[str, Any],
        substrate_state: dict[str, Any],
        wid: str,
    ) -> float:
        # Canonical strict-zero pattern: explicit zero grant stays zero; only missing keys fall back.
        if wid in allocated_state:
            return float(allocated_state.get(wid, 0.0))
        return float(substrate_state.get(wid, 0.0))

    def _ring_count(self) -> int:
        return int(np.dot(self._species_counts[self.polymer_indices], self.polymer_lengths))

    def _ring_count_from_counts(self, counts: np.ndarray) -> int:
        return int(np.dot(counts[self.polymer_indices], self.polymer_lengths))

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
        out: dict[str, int] = {}
        for idx, wid in enumerate(self.enzyme_wids):
            step = int(delta[idx])
            if step != 0:
                out[wid] = step
        return out

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

        n_gtp = np.zeros(len(self.enzyme_wids), dtype=np.int64)
        n_gtp[self.enzyme_index_ftsz_gtp] = 1
        n_gtp[self.polymer_indices] = self.polymer_lengths
        n_gdp = np.zeros(len(self.enzyme_wids), dtype=np.int64)
        n_gdp[self.enzyme_index_ftsz_gdp] = 1

        delta_gtp = -int(np.dot(n_gtp, delta_counts))
        delta_gdp = -int(np.dot(n_gdp, delta_counts))

        gdp_before = float(substrate_state.get(self.gdp_wid, 0.0))
        gdp_after = gdp_before + float(delta_gdp)
        gdp_shortfall = max(0, _clamp_to_nonnegative_int(-gdp_after))

        out: dict[str, int] = {
            self.gtp_wid: delta_gtp - gdp_shortfall,
            self.gdp_wid: delta_gdp + gdp_shortfall,
            self.pi_wid: gdp_shortfall,
            self.h2o_wid: -gdp_shortfall,
            self.h_wid: gdp_shortfall,
        }
        return {wid: int(delta) for wid, delta in out.items() if int(delta) != 0}

    def _event_poisson(self, expected: float) -> int:
        if not np.isfinite(expected) or expected <= 0.0:
            return 0
        return int(self._rng.poisson(expected))

    def _apply_stochastic_transitions(
        self,
        *,
        dt: float,
        gtp_budget: int,
        substrate_delta: dict[str, int],
    ) -> None:
        s = self._species_counts
        idx_gdp = self.enzyme_index_ftsz_gdp
        idx_gtp = self.enzyme_index_ftsz_gtp

        # 1) Inactive -> GTP activation (allocation-bounded GTP consumption).
        idx_ftsz = self.enzyme_index_ftsz
        n_ftsz = int(max(0, s[idx_ftsz]))
        activate_expected = (
            self.activation_fwd
            * float(n_ftsz)
            * dt
            / float(self.parameters["activation_rate_scale"])
        )
        n_activate = min(self._event_poisson(activate_expected), n_ftsz, gtp_budget)
        if n_activate > 0:
            s[idx_ftsz] -= n_activate
            s[idx_gtp] += n_activate
            substrate_delta[self.gtp_wid] = substrate_delta.get(self.gtp_wid, 0) - n_activate
            gtp_budget -= n_activate

        # 2) Spontaneous deactivation (GTP monomer -> GDP monomer).
        n_gtp = int(max(0, s[idx_gtp]))
        deactivate_expected = (
            self.activation_rev
            * float(n_gtp)
            * dt
            / float(self.parameters["deactivation_rate_scale"])
        )
        n_deactivate = min(self._event_poisson(deactivate_expected), n_gtp)
        if n_deactivate > 0:
            s[idx_gtp] -= n_deactivate
            s[idx_ftsz] += n_deactivate

        # 3) Nucleation forward/reverse between monomers and dimers.
        n_gtp = int(max(0, s[idx_gtp]))
        idx_dimer = self.enzyme_index_ftsz_dimer
        n_dimers = int(max(0, s[idx_dimer]))

        if n_gtp >= 2:
            choose2 = n_gtp * (n_gtp - 1) / 2.0
            nuc_fwd_expected = (
                self.nucleation_fwd
                * choose2
                * dt
                / float(self.parameters["nucleation_forward_scale"])
            )
            n_nuc_fwd = min(self._event_poisson(nuc_fwd_expected), n_gtp // 2)
            if n_nuc_fwd > 0:
                s[idx_gtp] -= 2 * n_nuc_fwd
                s[idx_dimer] += n_nuc_fwd
                n_gtp -= 2 * n_nuc_fwd
                n_dimers += n_nuc_fwd

        nuc_rev_expected = (
            self.nucleation_rev
            * float(n_dimers)
            * dt
            / float(self.parameters["nucleation_reverse_scale"])
        )
        n_nuc_rev = min(self._event_poisson(nuc_rev_expected), n_dimers)
        if n_nuc_rev > 0:
            s[idx_dimer] -= n_nuc_rev
            s[idx_gtp] += 2 * n_nuc_rev

        # 4) Elongation forward (k-mer + monomer -> (k+1)-mer) and reverse.
        for idx in range(self.enzyme_index_ftsz_dimer, self.enzyme_index_ftsz_9mer):
            n_poly = int(max(0, s[idx]))
            n_gtp = int(max(0, s[idx_gtp]))
            if n_poly <= 0 or n_gtp <= 0:
                continue
            expected = (
                self.elongation_fwd
                * float(n_poly * n_gtp)
                * dt
                / float(self.parameters["elongation_forward_scale"])
            )
            n_fwd = min(self._event_poisson(expected), n_poly, n_gtp)
            if n_fwd <= 0:
                continue
            s[idx] -= n_fwd
            s[idx + 1] += n_fwd
            s[idx_gtp] -= n_fwd

        # Reverse elongation with a light homeostasis bias toward Karr steady-state.
        ring_count = self._ring_count()
        target = int(self.parameters["ring_complete_threshold"])
        bias_events = int(
            min(
                int(self.parameters["homeostasis_cap"]),
                max(0.0, (ring_count - target) * float(self.parameters["homeostasis_strength"])),
            )
        )
        if bias_events > 0:
            for idx in range(self.enzyme_index_ftsz_9mer, self.enzyme_index_ftsz_dimer, -1):
                available = int(max(0, s[idx]))
                if available <= 0:
                    continue
                step = min(available, bias_events)
                if step <= 0:
                    continue
                s[idx] -= step
                s[idx - 1] += step
                s[idx_gtp] += step
                bias_events -= step
                if bias_events <= 0:
                    break

        for idx in range(self.enzyme_index_ftsz_9mer, self.enzyme_index_ftsz_dimer, -1):
            n_poly = int(max(0, s[idx]))
            if n_poly <= 0:
                continue
            expected = (
                self.elongation_rev
                * float(n_poly)
                * dt
                / float(self.parameters["elongation_reverse_scale"])
            )
            n_rev = min(self._event_poisson(expected), n_poly)
            if n_rev <= 0:
                continue
            s[idx] -= n_rev
            s[idx - 1] += n_rev
            s[idx_gtp] += n_rev

        # Final safety clamp.
        np.clip(s, a_min=0, a_max=None, out=s)


__all__ = ["KarrFtsZPolymerizationProcess"]
