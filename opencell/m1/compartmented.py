"""Karr-native compartmented stoichiometry (Phase D.1).

Loads `data/karr_fixtures/karr_native_m1_compartmented.{json,npz}` and
provides:

  * `CompartmentedStoichiometryModel` -- typed wrapper around the
    (585 substrates x 645 reactions x 3 compartments) signed integer
    stoichiometry matrix produced by Karr's KB.

  * `compute_lp_supply_baseline(model_m1, *, condition=1, growth_per_s=None)`
    -- supply-side calibration helper that takes the Karr FBA solution
    `v` (504 cols, units mmol/gDW/h) and returns the per-substrate-WCM,
    per-compartment net production rate in molecules/s/cell. Used as
    a cross-check on Phase C.4's demand-side calibrated baseline.

The helper is intentionally a one-shot SS calibration; the spike in
Phase D.1 (see scripts/_d1_spike.py history) confirmed that Karr's FBA
submodel does NOT model NTP/AA supply (those go through non-FBA
processes M4-M28), so a per-tick LP-derived replenishment would yield
zero signal for the substrates the chassis actually cares about. The
SS calibration is honest and useful as a sanity check.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

DEFAULT_FIXTURE_JSON = (
    Path(__file__).resolve().parents[2]
    / "data" / "karr_fixtures" / "karr_native_m1_compartmented.json"
)

SCHEMA_VERSION = "karr_native_m1_compartmented__v1"

# mmol/gDW/h -> molecules/s/cell conversion at SS dry mass.
AVOGADRO = 6.02214076e23
SECONDS_PER_HOUR = 3600.0


@dataclass
class CompartmentedStoichiometryModel:
    S: np.ndarray  # (585, 645, 3) int16
    S_aggregate: np.ndarray  # (585, 645) int16/int32
    substrate_wids_585: list[str]
    reaction_wids_645: list[str]
    compartment_wids_3: list[str]
    compartment_index_map: dict[str, int]
    cell_dry_mass_g: float
    stats: dict
    raw: dict = field(repr=False)

    # ---- shape & basic queries ----

    @property
    def n_substrates(self) -> int:
        return self.S.shape[0]

    @property
    def n_reactions(self) -> int:
        return self.S.shape[1]

    @property
    def n_compartments(self) -> int:
        return self.S.shape[2]

    def substrate_index(self, wid: str) -> int:
        return self.substrate_wids_585.index(wid)

    def reaction_index(self, wid: str) -> int:
        return self.reaction_wids_645.index(wid)

    def compartment_index(self, wid: str) -> int:
        if wid not in self.compartment_index_map:
            raise KeyError(
                f"unknown compartment {wid!r}; valid: {list(self.compartment_index_map)}"
            )
        return self.compartment_index_map[wid]

    def stoich(self, substrate_wid: str, reaction_wid: str, compartment_wid: str) -> int:
        si = self.substrate_index(substrate_wid)
        ri = self.reaction_index(reaction_wid)
        ci = self.compartment_index(compartment_wid)
        return int(self.S[si, ri, ci])

    # ---- conversion helpers ----

    def mmol_per_gdwh_to_molecules_per_s(self, x: float | np.ndarray) -> float | np.ndarray:
        """mmol/gDW/h * (g_dry_per_cell) * (mol/mmol=1e-3) * N_A / (s/h=3600)."""
        return x * 1e-3 * AVOGADRO * self.cell_dry_mass_g / SECONDS_PER_HOUR


def load_default(path: str | Path | None = None) -> CompartmentedStoichiometryModel:
    p = Path(path) if path is not None else DEFAULT_FIXTURE_JSON
    if not p.exists():
        raise FileNotFoundError(
            f"Run `python scripts/karr_native_ingest_compartmented.py` first; missing {p}"
        )
    raw = json.loads(p.read_text())
    if raw["schema_version"] != SCHEMA_VERSION:
        raise ValueError(
            f"Schema version mismatch: fixture={raw['schema_version']!r} "
            f"expected={SCHEMA_VERSION!r}"
        )
    npz_path = (p.parent / Path(raw["matrix_npz"]).name)
    npz = np.load(npz_path)
    S = np.asarray(npz["S_compartmented"])
    S_agg = np.asarray(npz["S_aggregate"])
    return CompartmentedStoichiometryModel(
        S=S,
        S_aggregate=S_agg,
        substrate_wids_585=[str(s) for s in raw["ids"]["substrate_wcm_585"]],
        reaction_wids_645=[str(s) for s in raw["ids"]["reaction_wcm_645"]],
        compartment_wids_3=[str(s) for s in raw["compartment_wids_3"]],
        compartment_index_map={k: int(v) for k, v in raw["compartment_index_map"].items()},
        cell_dry_mass_g=float(raw["cell_dry_mass_g"]),
        stats=dict(raw.get("stats", {})),
        raw=raw,
    )


# ---- supply-side calibration helper ----

def compute_lp_supply_baseline(
    model_m1,
    *,
    compartmented=None,
    condition: int = 1,
    bounds_mode: str = "no_protein",
) -> dict[tuple[str, str], float]:
    """Return per-(substrate_wid, compartment_wid) net SS supply rate
    in molecules/s/cell, derived from the FBA solution at snapshot.

    Args:
        model_m1: KarrMetabolismModel (from opencell.m1.karr_metabolism).
        compartmented: optional preloaded CompartmentedStoichiometryModel.
        condition: not currently used (placeholder for future
                   condition-aware variants of the LP).
        bounds_mode: "no_protein" or "with_protein"; selects which
                     calcFluxBounds output to use.

    Returns:
        Dict mapping (substrate_wid, compartment_wid) -> molecules/s.
        Only nonzero entries are included. Positive values mean the
        FBA submodel is a *net producer* of that substrate in that
        compartment at SS; negative means net consumer.

    Notes:
        * At SS, FBA mass balance enforces S_internal @ v ~= 0 across the
          376 internal substrate rows. The compartmented S is over the
          full 585-substrate vocabulary, so non-zero entries here come
          from boundary/exchange/biomass cols and from the residual of
          the internal-exchange and external-exchange columns hitting
          substrates outside the strict 376 internal set.
        * NTPs (ATP/CTP/GTP/UTP) typically come out at zero or biomass-
          consumption rate, NOT at synthesis rate -- their synthesis
          lives in non-FBA processes. See module docstring.
    """
    if compartmented is None:
        compartmented = load_default()

    # Solve LP at snapshot using existing solver with dynamic bounds.
    from opencell.m1.karr_metabolism import solve_fba

    dyn_npz = np.load(
        Path(__file__).resolve().parents[2]
        / "data" / "karr_fixtures" / "karr_native_m1_dynamics.npz"
    )
    bounds_key = (
        "bounds_dynamic_no_protein" if bounds_mode == "no_protein"
        else "bounds_dynamic_with_protein"
    )
    bounds = np.asarray(dyn_npz[bounds_key])
    v_504, _info = solve_fba(
        model_m1,
        lb_override=bounds[:, 0],
        ub_override=bounds[:, 1],
    )

    # Expand 504 -> 645 via fba_col_to_reaction_wcm mapping.
    rxn_wids_645 = compartmented.reaction_wids_645
    fba_col_rxn = list(model_m1.fba_col_rxn_wcm)
    if len(fba_col_rxn) != v_504.size:
        raise RuntimeError(
            f"fba_col_rxn_wcm len={len(fba_col_rxn)} != v.size={v_504.size}"
        )

    v_645 = np.zeros(645, dtype=np.float64)
    for col, wid in enumerate(fba_col_rxn):
        if wid is None:
            continue  # biomass virtual rxn / no 645-space identity
        try:
            r_idx = rxn_wids_645.index(wid)
        except ValueError:
            continue
        v_645[r_idx] += v_504[col]

    # Compute per-substrate per-compartment net flux: S[s, r, k] @ v[r]
    # -> shape (585, 3), in mmol/gDW/h.
    net_flux_per_s_per_k = np.einsum("srk,r->sk", compartmented.S.astype(np.float64), v_645)

    # Convert to molecules/s/cell.
    net_flux_molecules_per_s = compartmented.mmol_per_gdwh_to_molecules_per_s(
        net_flux_per_s_per_k
    )

    out: dict[tuple[str, str], float] = {}
    nz = np.argwhere(np.abs(net_flux_molecules_per_s) > 1e-9)
    for si, ki in nz:
        sub_wid = compartmented.substrate_wids_585[si]
        cmp_wid = compartmented.compartment_wids_3[ki]
        out[(sub_wid, cmp_wid)] = float(net_flux_molecules_per_s[si, ki])
    return out
