"""Vivarium Process for Karr D.2 macromolecular complexation.

This ports the per-tick complex formation logic from Karr's
MacromolecularComplexation process into a Vivarium Process.

TODO (Phase B): ribosome-assembly specific enzyme/GTP coupling is deferred.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from vivarium.core.process import Process

_DEFAULT_FIXTURE_PATH = "data/karr_fixtures/per_process/MacromolecularComplexation_flat.mat"
_MC_ITERATION_LIMIT = 10_000


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


def _load_fixture(path: str | Path) -> dict[str, Any]:
    resolved = _resolve_fixture_path(path)
    mat = loadmat(str(resolved))
    fx = mat["data"]["fixture"][0, 0]

    substrate_wids = _extract_wids(fx["substrateWholeCellModelIDs"])
    complex_wids = _extract_wids(fx["complexWholeCellModelIDs"])
    complex_composition = np.asarray(fx["complexComposition"][0, 0], dtype=np.int64)

    cn_outer = fx["complexNetworks"][0, 0]
    networks = [np.asarray(cn_outer[idx, 0], dtype=np.int64) for idx in range(cn_outer.shape[0])]

    substrates2net = np.asarray(fx["substrates2complexNetworks"][0, 0], dtype=np.int64).reshape(-1)
    complexes2net = np.asarray(fx["complexs2complexNetworks"][0, 0], dtype=np.int64).reshape(-1)

    return {
        "substrate_wids": substrate_wids,
        "complex_wids": complex_wids,
        "complex_composition": complex_composition,
        "substrates2net": substrates2net,
        "complexes2net": complexes2net,
        "networks": networks,
    }


def _closed_form_bounds(sub_avail: np.ndarray, stoich: np.ndarray) -> np.ndarray:
    """Upper-bound formability per complex from current subunit availability."""
    n_cpx = stoich.shape[1]
    out = np.zeros(n_cpx, dtype=np.int64)
    for cidx in range(n_cpx):
        col = stoich[:, cidx]
        active = col > 0
        if not np.any(active):
            continue
        out[cidx] = int(np.min(sub_avail[active] // col[active]))
    return out


def _per_cluster_mc(
    sub_avail: np.ndarray,
    stoich: np.ndarray,
    rng: np.random.Generator,
    rate_constant: float,
) -> np.ndarray:
    """Collision-theory Monte Carlo assembly for one disconnected network."""
    available = np.asarray(sub_avail, dtype=np.int64).copy()
    n_cpx = stoich.shape[1]
    formed = np.zeros(n_cpx, dtype=np.int64)

    for _ in range(_MC_ITERATION_LIMIT):
        ub = _closed_form_bounds(available, stoich)
        if not np.any(ub > 0):
            break

        mean_sub = max(1.0, float(np.mean(available)))
        rates = np.zeros(n_cpx, dtype=np.float64)
        for cidx in range(n_cpx):
            if ub[cidx] <= 0:
                continue
            col = stoich[:, cidx]
            active = col > 0
            if not np.any(active):
                continue
            norm = available[active] / mean_sub
            if np.any(norm <= 0.0):
                rates[cidx] = 0.0
                continue
            rates[cidx] = rate_constant * float(
                np.prod(np.power(norm, col[active], dtype=np.float64))
            )

        # Required Karr safety filter: if a complex has no feasible upper bound,
        # its rate must be forced to zero.
        rates[ub == 0] = 0.0

        total_rate = float(np.sum(rates))
        if total_rate <= 0.0:
            break

        chosen = int(rng.choice(n_cpx, p=(rates / total_rate)))
        sampled = int(rng.poisson(rates[chosen]))
        n_form = min(sampled, int(ub[chosen]))
        if n_form <= 0 and ub[chosen] > 0:
            n_form = 1

        if n_form <= 0:
            break

        formed[chosen] += n_form
        available -= stoich[:, chosen] * n_form
    else:
        raise RuntimeError("D2 per-cluster Monte Carlo exceeded iteration limit")

    return formed


class MacromolecularComplexationProcess(Process):
    """Real D.2 process: complexation from free subunit pools."""

    name = "karr_macromolecular_complexation"
    defaults: dict[str, Any] = {
        "fixture_path": _DEFAULT_FIXTURE_PATH,
        "rng_seed": 0,
        "time_step": 1.0,
        "rate_constant": 0.05,
    }

    def __init__(self, parameters: dict[str, Any] | None = None) -> None:
        super().__init__(parameters)
        fixture = _load_fixture(self.parameters["fixture_path"])

        self.substrate_wids: list[str] = fixture["substrate_wids"]
        self.complex_wids: list[str] = fixture["complex_wids"]
        self.complex_composition: np.ndarray = fixture["complex_composition"]
        self.substrates2net: np.ndarray = fixture["substrates2net"]
        self.complexes2net: np.ndarray = fixture["complexes2net"]
        self.networks: list[np.ndarray] = fixture["networks"]

        self._rng = np.random.default_rng(self.parameters["rng_seed"])

    def ports_schema(self) -> dict[str, Any]:
        return {
            "substrates": {
                wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
                for wid in self.substrate_wids
            },
            "complex": {
                "counts": {
                    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": True}
                    for wid in self.complex_wids
                }
            },
            "requests": {
                self.name: {
                    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
                    for wid in self.substrate_wids
                }
            },
            "substrates_allocated": {
                self.name: {
                    wid: {"_default": 0.0, "_emit": False}
                    for wid in self.substrate_wids
                }
            },
        }

    def next_update(self, timestep: float, states: dict[str, Any]) -> dict[str, Any]:
        del timestep
        allocated_state = states.get("substrates_allocated", {}).get(self.name, {})

        sub_counts = np.array(
            [float(allocated_state.get(wid, 0.0)) for wid in self.substrate_wids],
            dtype=np.float64,
        )
        sub_counts = np.floor(np.clip(sub_counts, a_min=0.0, a_max=None)).astype(np.int64)
        if not np.any(sub_counts > 0):
            return {"substrates": {}, "complex": {"counts": {}}}

        new_complexes = np.zeros(len(self.complex_wids), dtype=np.int64)

        for cluster_idx, _ in enumerate(self.networks, start=1):
            sub_indices = np.flatnonzero(self.substrates2net == cluster_idx)
            cpx_indices = np.flatnonzero(self.complexes2net == cluster_idx)
            if cpx_indices.size == 0:
                continue

            stoich = self.complex_composition[np.ix_(sub_indices, cpx_indices)]
            sub_avail = sub_counts[sub_indices].copy()
            if cluster_idx == 1:
                in_cluster = _closed_form_bounds(sub_avail, stoich)
                # Safety hedge: if assumptions are violated, fall back to MC.
                if np.any((stoich @ in_cluster) > sub_avail):
                    in_cluster = _per_cluster_mc(
                        sub_avail, stoich, self._rng, self.parameters["rate_constant"]
                    )
            else:
                in_cluster = _per_cluster_mc(
                    sub_avail, stoich, self._rng, self.parameters["rate_constant"]
                )

            consumed = stoich @ in_cluster
            sub_counts[sub_indices] -= consumed
            new_complexes[cpx_indices] = in_cluster

        delta_substrates = -(self.complex_composition @ new_complexes)
        return {
            "substrates": {
                wid: float(delta_substrates[idx])
                for idx, wid in enumerate(self.substrate_wids)
                if delta_substrates[idx] != 0
            },
            "complex": {
                "counts": {
                    wid: float(new_complexes[idx])
                    for idx, wid in enumerate(self.complex_wids)
                    if new_complexes[idx] > 0
                }
            },
        }


__all__ = [
    "MacromolecularComplexationProcess",
    "_closed_form_bounds",
    "_load_fixture",
    "_per_cluster_mc",
]
