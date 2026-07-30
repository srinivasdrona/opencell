"""H12 machine evidence framework for PRIMARY_CHANNEL_DETERMINISTIC_CONVERGENCE rows.

Produces genuine, independently-derived machine evidence that a process's OC
closed-form path converges on Karr's stochastic algorithm *because the Karr
algorithm itself becomes provably deterministic in the observed regime*, not
because of oracle leakage ("laundering").

======================================================================
ANTI-LAUNDERING CONTRACT — READ BEFORE EDITING THIS FILE
======================================================================
Every ``predict_<process>`` function in this module implements the PREDICT
phase of a strict two-phase protocol:

    PREDICT phase (this file, ``predict_*`` functions):
        Inputs:  ``states_before`` (one tick's pre-tick state vectors, read
                 from the raw Karr oracle trace) and ``fixture`` (static,
                 versioned Karr knowledge-base parameters: stoichiometry
                 matrices, rate constants, index maps — loaded once from
                 ``data/karr_fixtures/per_process/<Process>_flat.mat``).
        Forbidden: importing any ``opencell.vivarium.*`` SUT module, calling
                 ``next_update``/``run_oc_tick``, reading ``states_after``,
                 reading any ``result.json``/evidence-bundle output, or
                 otherwise touching anything derived from an OC run or a
                 previously-computed verdict. Formulas here are transcribed
                 directly from the Karr MATLAB source (citations recorded in
                 each predictor's docstring) — never reverse-engineered from
                 observed outcomes.

    COMPARE phase (``compare_predictions`` below, called strictly after
    ``predict_*`` has returned and its output has been frozen):
        Inputs: the frozen predictions plus ``states_after`` (read only
                 here, never inside a ``predict_*`` function).

This module is scanned by ``tests/scripts/test_h12_anticheat.py`` for
forbidden imports/identifiers inside ``predict_*`` function bodies. Do not
work around that test; if a formula genuinely cannot be derived without
consulting ``states_after``/the SUT, that process should be reported
H12_FAIL, not laundered.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import h5py
import numpy as np
from scipy.io import loadmat

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "data" / "karr_fixtures" / "per_process"
ORACLE_ROOT = REPO_ROOT / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2"
OUT_ROOT = REPO_ROOT / "docs" / "phase_f" / "l2_2_design_a" / "h12"

FORMULA_VERSION = "1.0.0"

# Catalog N_seeds/M_ticks for the 5 target processes (docs/phase_f/l2_2_design_a/
# PROCESS_CATALOG.yaml, read-only citation — do not edit that file from here).
CATALOG_N_M = {
    "tRNAAminoacylation": (50, 50),
    "ProteinProcessingII": (50, 20),
    "ProteinFolding": (50, 100),
    "MacromolecularComplexation": (50, 100),
    "ProteinProcessingI": (50, 20),
}

# Highest-risk-first run order mandated by the task.
RISK_ORDER = [
    "tRNAAminoacylation",
    "ProteinProcessingII",
    "ProteinFolding",
    "MacromolecularComplexation",
    "ProteinProcessingI",
]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_array(arr: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest()


# ---------------------------------------------------------------------------
# Fixture loading (static Karr knowledge-base parameters; scipy.io.loadmat
# only — these .mat files are NOT MATLAB v7.3/HDF5). No SUT imports.
# ---------------------------------------------------------------------------


def _mat_struct(process: str):
    path = FIXTURE_ROOT / f"{process}_flat.mat"
    return loadmat(str(path))["data"]["fixture"][0, 0], path


def _field(struct, name: str) -> np.ndarray:
    return np.asarray(struct[name][0, 0])


def load_fixture(process: str) -> dict:
    """Load the static Karr fixture parameters this process's predictor needs.

    Returns a dict with a reserved ``__fixture_path__``/``__fixture_sha256__``
    pair (provenance) plus process-specific numpy arrays. 1-based MATLAB
    indices are converted to 0-based on load, clearly suffixed ``_0b``.
    """
    struct, path = _mat_struct(process)
    sha = _sha256_file(path)
    out: dict = {"__fixture_path__": str(path.relative_to(REPO_ROOT)), "__fixture_sha256__": sha}

    if process == "MacromolecularComplexation":
        out["complexComposition"] = _field(struct, "complexComposition").astype(np.int64)
        out["substrates2complexNetworks"] = _field(struct, "substrates2complexNetworks").astype(np.int64).ravel()
        out["complexs2complexNetworks"] = _field(struct, "complexs2complexNetworks").astype(np.int64).ravel()

    elif process == "ProteinProcessingI":
        out["substrateIndexs_water_0b"] = int(_field(struct, "substrateIndexs_water").ravel()[0]) - 1
        out["substrateIndexs_hydrogen_0b"] = int(_field(struct, "substrateIndexs_hydrogen").ravel()[0]) - 1
        out["substrateIndexs_methionine_0b"] = int(_field(struct, "substrateIndexs_methionine").ravel()[0]) - 1
        out["substrateIndexs_formate_0b"] = int(_field(struct, "substrateIndexs_formate").ravel()[0]) - 1
        out["enzymeIndexs_deformylase_0b"] = int(_field(struct, "enzymeIndexs_deformylase").ravel()[0]) - 1
        out["enzymeIndexs_methionineAminoPeptidase_0b"] = (
            int(_field(struct, "enzymeIndexs_methionineAminoPeptidase").ravel()[0]) - 1
        )
        out["deformylaseSpecificRate"] = float(_field(struct, "deformylaseSpecificRate").ravel()[0])
        out["methionineAminoPeptidaseSpecificRate"] = float(
            _field(struct, "methionineAminoPeptidaseSpecificRate").ravel()[0]
        )
        out["stepSizeSec"] = float(_field(struct, "stepSizeSec").ravel()[0])
        out["cleavage_mask"] = _field(struct, "nascentMonomerNTerminalMethionineCleavages").astype(bool).ravel()

    elif process == "ProteinProcessingII":
        out["substrateIndexs_water_0b"] = int(_field(struct, "substrateIndexs_water").ravel()[0]) - 1
        out["substrateIndexs_hydrogen_0b"] = int(_field(struct, "substrateIndexs_hydrogen").ravel()[0]) - 1
        out["substrateIndexs_PG160_0b"] = int(_field(struct, "substrateIndexs_PG160").ravel()[0]) - 1
        out["substrateIndexs_SNGLYP_0b"] = int(_field(struct, "substrateIndexs_SNGLYP").ravel()[0]) - 1
        out["enzymeIndexs_signalPeptidase_0b"] = int(_field(struct, "enzymeIndexs_signalPeptidase").ravel()[0]) - 1
        out["enzymeIndexs_diacylglycerylTransferase_0b"] = (
            int(_field(struct, "enzymeIndexs_diacylglycerylTransferase").ravel()[0]) - 1
        )
        out["lipoproteinSignalPeptidaseSpecificRate"] = float(
            _field(struct, "lipoproteinSignalPeptidaseSpecificRate").ravel()[0]
        )
        out["lipoproteinDiacylglycerylTransferaseSpecificRate"] = float(
            _field(struct, "lipoproteinDiacylglycerylTransferaseSpecificRate").ravel()[0]
        )
        out["stepSizeSec"] = float(_field(struct, "stepSizeSec").ravel()[0])
        out["unprocessedMonomerIndexs_0b"] = _field(struct, "unprocessedMonomerIndexs").astype(np.int64).ravel() - 1
        out["lipoproteinMonomerIndexs_0b"] = _field(struct, "lipoproteinMonomerIndexs").astype(np.int64).ravel() - 1
        out["secretedMonomerIndexs_0b"] = _field(struct, "secretedMonomerIndexs").astype(np.int64).ravel() - 1

    elif process == "ProteinFolding":
        out["substrateIndexs_water_0b"] = int(_field(struct, "substrateIndexs_water").ravel()[0]) - 1
        out["substrateIndexs_hydrogen_0b"] = int(_field(struct, "substrateIndexs_hydrogen").ravel()[0]) - 1
        out["proteinProstheticGroupMatrix"] = _field(struct, "proteinProstheticGroupMatrix").astype(np.float64)
        out["monomerComplexIndexs_folded_0b"] = (
            _field(struct, "monomerComplexIndexs_folded").astype(np.int64).ravel() - 1
        )
        out["complexIndexs_folding_0b"] = _field(struct, "complexIndexs_folding").astype(np.int64).ravel() - 1
        out["complexIndexs_notFolding_0b"] = _field(struct, "complexIndexs_notFolding").astype(np.int64).ravel() - 1
        out["speciesIndexs_monomers_0b"] = _field(struct, "speciesIndexs_monomers").astype(np.int64).ravel() - 1
        out["speciesIndexs_complexs_0b"] = _field(struct, "speciesIndexs_complexs").astype(np.int64).ravel() - 1

    elif process == "tRNAAminoacylation":
        out["substrateIndexs_water_0b"] = int(_field(struct, "substrateIndexs_water").ravel()[0]) - 1
        out["substrateIndexs_hydrogen_0b"] = int(_field(struct, "substrateIndexs_hydrogen").ravel()[0]) - 1
        out["speciesIndexs_enzymes_0b"] = _field(struct, "speciesIndexs_enzymes").astype(np.int64).ravel() - 1
        out["speciesReactantByproductMatrix"] = _field(struct, "speciesReactantByproductMatrix").astype(np.float64)
        out["reactionStoichiometryMatrix"] = _field(struct, "reactionStoichiometryMatrix").astype(np.float64)
        out["reactionModificationMatrix"] = _field(struct, "reactionModificationMatrix").astype(np.float64)

    else:
        raise ValueError(f"unknown process {process!r}")

    return out


# ---------------------------------------------------------------------------
# Oracle trace loading (raw Karr per-tick traces; MATLAB v7.3/HDF5 -> h5py
# only). We deliberately do NOT import tests/vivarium/_l2_2_design_a_runner_
# helpers.py (the harness's own oracle loader) to keep this reading path
# independent, even though it means re-deriving the same HDF5-dereference
# pattern here.
# ---------------------------------------------------------------------------


def _resolve_oracle_path(process: str, seed: int) -> Path:
    if seed == 0:
        candidate = ORACLE_ROOT / f"{process}_100ticks.mat"
        if candidate.exists():
            return candidate
    candidate = ORACLE_ROOT.parent / f"per_process_traces_v2_s{seed:03d}" / f"{process}_100ticks.mat"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"no oracle trace for process={process} seed={seed}")


def load_oracle_seed(process: str, seed: int, n_ticks: int) -> tuple[dict, dict, str]:
    """Load ``states_before``/``states_after`` channel arrays for one seed.

    Returns ``(before, after, file_sha256)`` where ``before``/``after`` map
    channel name -> array of shape (n_ticks, width). Only the first
    ``n_ticks`` ticks (catalog M) are loaded.
    """
    path = _resolve_oracle_path(process, seed)
    sha = _sha256_file(path)
    before: dict = {}
    after: dict = {}
    with h5py.File(path, "r") as handle:
        avail_ticks = int(np.asarray(handle["metadata"]["n_ticks"][()]).ravel()[0])
        use_ticks = min(n_ticks, avail_ticks)
        for phase_name, phase_dict in (("states_before", before), ("states_after", after)):
            group = handle[phase_name]
            for channel in group.keys():
                refs = group[channel][0, :use_ticks]
                rows = [np.asarray(handle[ref][()]).ravel() for ref in refs]
                phase_dict[channel] = np.stack(rows, axis=0)
    return before, after, sha


# ---------------------------------------------------------------------------
# Prediction result container
# ---------------------------------------------------------------------------


@dataclass
class UnitPrediction:
    """One independently-verifiable (seed, tick, unit) prediction."""

    seed: int
    tick: int
    unit: str
    regime_valid: bool
    regime_reason: str
    nontrivial: bool
    predicted_delta: dict = field(default_factory=dict)  # channel -> np.ndarray (full-width delta)


# ---------------------------------------------------------------------------
# Predictors
#
# Each predict_<process> function:
#   - receives `before`: dict[channel] -> np.ndarray shape (n_ticks, width) for
#     ONE seed (states_before only)
#   - receives `fixture`: dict from load_fixture(process)
#   - returns a list[UnitPrediction], one (or more) entries per tick
#
# No predict_* function may reference `after`/states_after/any SUT module.
# ---------------------------------------------------------------------------


def predict_macromolecular_complexation(seed: int, before: dict, fixture: dict) -> list[UnitPrediction]:
    """MacromolecularComplexation.m evolveState (source lines ~290-315) +
    buildProteinComplexs_bounds (line ~390-391):

        newComplexs(complexs2complexNetworks==1) = buildProteinComplexs_bounds(
            substrates(substrates2complexNetworks==1), complexNetworks{1})
        ub = floor(min(totalProteinMonomers ./ proteinComplexMatrix, [], 1))

    Network 1 ("no competition") is Karr's OWN deterministic ground truth —
    not an approximation of a stochastic process. For network>=2 (genuine
    Monte Carlo competition, buildProteinComplexs_montecarlokinetic, lines
    ~334-358), the same upper-bound formula applies; per-tick substrate
    consumption for a network's rows can only shrink `ub` monotonically
    within a tick (never grow it), so if pre-tick `ub[c]==0` for every
    complex in a connected network component, that component is *provably*
    guaranteed to build 0 new complexes this tick, regardless of RNG path.
    If any `ub[c]>0` in a network>=2 component, the outcome is genuinely
    stochastic and that component's samples are excluded (regime_valid=False).
    """
    comp = fixture["complexComposition"]  # (n_substrates, n_complexes)
    sub_net = fixture["substrates2complexNetworks"]  # (n_substrates,)
    cx_net = fixture["complexs2complexNetworks"]  # (n_complexes,)
    n_ticks = before["substrates"].shape[0]
    n_complexes = comp.shape[1]

    networks = sorted(set(int(n) for n in cx_net if n > 0))
    out: list[UnitPrediction] = []

    for tick in range(n_ticks):
        substrates_before = before["substrates"][tick].astype(np.float64)
        for net in networks:
            cx_mask = cx_net == net
            sub_mask = sub_net == net
            sub_idx = np.where(sub_mask)[0]
            cx_idx = np.where(cx_mask)[0]
            if sub_idx.size == 0 or cx_idx.size == 0:
                continue
            block = comp[np.ix_(sub_idx, cx_idx)].astype(np.float64)
            pool = substrates_before[sub_idx]
            with np.errstate(divide="ignore", invalid="ignore"):
                ratio = np.where(block > 0, pool[:, None] / np.where(block > 0, block, 1.0), np.inf)
            ub = np.floor(np.min(ratio, axis=0))
            ub = np.where(np.isfinite(ub), ub, 0.0)
            ub = np.maximum(ub, 0.0)

            complexs_delta = np.zeros(n_complexes, dtype=np.float64)
            substrates_delta = np.zeros(comp.shape[0], dtype=np.float64)

            if net == 1:
                # Karr's own literal ground truth for this network — always valid.
                complexs_delta[cx_idx] = ub
                substrates_delta[sub_idx] = -(block @ ub)
                nontrivial = bool(np.any(ub > 0))
                out.append(
                    UnitPrediction(
                        seed=seed,
                        tick=tick,
                        unit=f"network_{net}",
                        regime_valid=True,
                        regime_reason="network_1_karr_ground_truth_no_competition",
                        nontrivial=nontrivial,
                        predicted_delta={"complexs": complexs_delta, "substrates": substrates_delta},
                    )
                )
            else:
                if np.all(ub == 0):
                    out.append(
                        UnitPrediction(
                            seed=seed,
                            tick=tick,
                            unit=f"network_{net}",
                            regime_valid=True,
                            regime_reason="network_ge2_all_bounds_zero_monotonic_guarantee",
                            nontrivial=False,
                            predicted_delta={"complexs": complexs_delta, "substrates": substrates_delta},
                        )
                    )
                else:
                    out.append(
                        UnitPrediction(
                            seed=seed,
                            tick=tick,
                            unit=f"network_{net}",
                            regime_valid=False,
                            regime_reason="network_ge2_nonzero_bound_genuine_monte_carlo_competition",
                            nontrivial=False,
                            predicted_delta={},
                        )
                    )
    return out


def predict_protein_processing_i(seed: int, before: dict, fixture: dict) -> list[UnitPrediction]:
    """ProteinProcessingI.m evolveState (source lines 236-320).

    deformylaseLimit = enzymes[deformylase] * deformylaseSpecificRate * stepSizeSec
    cleavageLimit     = enzymes[metAP]       * methionineAminoPeptidaseSpecificRate * stepSizeSec

    If deformylaseLimit >= sum(unprocessedMonomers) AND
       cleavageLimit    >= sum(unprocessedMonomers[cleavage_mask]) (or that
       sum is 0) AND water >= sum(all) + sum(cleavage_mask):
    then block 1's per-species scale factors are both exactly 1, so
    stochasticRound() acts on already-integer values (no-op, p=1), the water
    mnrnd-rationing branch's `if` guard is false (skipped), and ALL
    unprocessedMonomers are processed this tick — deterministically,
    regardless of RNG. Block 2 (lines 298-318) then sees an all-zero
    remainder and is a no-op.
    """
    water_0b = fixture["substrateIndexs_water_0b"]
    hydrogen_0b = fixture["substrateIndexs_hydrogen_0b"]
    methionine_0b = fixture["substrateIndexs_methionine_0b"]
    formate_0b = fixture["substrateIndexs_formate_0b"]
    deform_0b = fixture["enzymeIndexs_deformylase_0b"]
    metap_0b = fixture["enzymeIndexs_methionineAminoPeptidase_0b"]
    rate_deform = fixture["deformylaseSpecificRate"]
    rate_metap = fixture["methionineAminoPeptidaseSpecificRate"]
    dt = fixture["stepSizeSec"]
    cleavage_mask = fixture["cleavage_mask"]

    n_ticks = before["unprocessedMonomers"].shape[0]
    out: list[UnitPrediction] = []
    for tick in range(n_ticks):
        unproc = before["unprocessedMonomers"][tick].astype(np.float64)
        enzymes = before["enzymes"][tick].astype(np.float64)
        water = float(before["substrates"][tick][water_0b])

        total = float(unproc.sum())
        cleave_sum = float(unproc[cleavage_mask].sum())
        deform_limit = float(enzymes[deform_0b] * rate_deform * dt)
        cleave_limit = float(enzymes[metap_0b] * rate_metap * dt)

        regime_valid = (
            deform_limit >= total
            and (cleave_sum == 0.0 or cleave_limit >= cleave_sum)
            and water >= (total + cleave_sum)
        )
        nontrivial = total > 0.0
        if not regime_valid:
            out.append(
                UnitPrediction(
                    seed=seed,
                    tick=tick,
                    unit="all",
                    regime_valid=False,
                    regime_reason="capacity_or_water_guard_failed",
                    nontrivial=False,
                    predicted_delta={},
                )
            )
            continue

        n_substrates = before["substrates"].shape[1]
        substrates_delta = np.zeros(n_substrates, dtype=np.float64)
        substrates_delta[water_0b] -= total + cleave_sum
        substrates_delta[formate_0b] += total
        substrates_delta[hydrogen_0b] += total
        substrates_delta[methionine_0b] += cleave_sum

        out.append(
            UnitPrediction(
                seed=seed,
                tick=tick,
                unit="all",
                regime_valid=True,
                regime_reason="full_saturating_closed_form",
                nontrivial=nontrivial,
                predicted_delta={
                    "unprocessedMonomers": -unproc,
                    "processedMonomers": unproc.copy(),
                    "substrates": substrates_delta,
                    "enzymes": np.zeros_like(enzymes),
                },
            )
        )
    return out


def predict_protein_processing_ii(seed: int, before: dict, fixture: dict) -> list[UnitPrediction]:
    """ProteinProcessingII.m evolveState (source lines 348-440).

    Unconditional pass-through of `unprocessedMonomerIndexs` (no processing
    needed) always happens first, deterministically. The remaining
    lipoprotein (`transferaseIndexs`) + secreted (`peptidaseIndexs`) pools
    are then processed via two sequential blocks gated by
    peptidaseLimit/transferaseLimit + water/PG160. If the aggregate
    peptidase and transferase capacities meet or exceed the aggregate
    demand from BOTH indices sets, and water/PG160 both meet or exceed
    consumption, block 1's scale factors are exactly 1 (stochasticRound
    no-op) and block 1 fully processes everything; block 2 then sees an
    all-zero remainder (no-op).
    """
    water_0b = fixture["substrateIndexs_water_0b"]
    hydrogen_0b = fixture["substrateIndexs_hydrogen_0b"]
    pg160_0b = fixture["substrateIndexs_PG160_0b"]
    snglyp_0b = fixture["substrateIndexs_SNGLYP_0b"]
    peptidase_enz_0b = fixture["enzymeIndexs_signalPeptidase_0b"]
    transferase_enz_0b = fixture["enzymeIndexs_diacylglycerylTransferase_0b"]
    rate_peptidase = fixture["lipoproteinSignalPeptidaseSpecificRate"]
    rate_transferase = fixture["lipoproteinDiacylglycerylTransferaseSpecificRate"]
    dt = fixture["stepSizeSec"]
    passthrough_idx = fixture["unprocessedMonomerIndexs_0b"]
    lipoprotein_idx = fixture["lipoproteinMonomerIndexs_0b"]
    secreted_idx = fixture["secretedMonomerIndexs_0b"]
    peptidase_idx = np.concatenate([lipoprotein_idx, secreted_idx])
    transferase_idx = lipoprotein_idx

    n_ticks = before["unprocessedMonomers"].shape[0]
    out: list[UnitPrediction] = []
    for tick in range(n_ticks):
        unproc = before["unprocessedMonomers"][tick].astype(np.float64)
        enzymes = before["enzymes"][tick].astype(np.float64)
        water = float(before["substrates"][tick][water_0b])
        pg160 = float(before["substrates"][tick][pg160_0b])

        # unconditional pass-through is always deterministic, independent of guard
        passthrough_delta = np.zeros_like(unproc)
        passthrough_delta[passthrough_idx] = unproc[passthrough_idx]

        peptidase_demand = float(unproc[peptidase_idx].sum())
        transferase_demand = float(unproc[transferase_idx].sum())
        peptidase_limit = float(enzymes[peptidase_enz_0b] * rate_peptidase * dt)
        transferase_limit = float(enzymes[transferase_enz_0b] * rate_transferase * dt)

        regime_valid = (
            peptidase_limit >= peptidase_demand
            and (transferase_demand == 0.0 or transferase_limit >= transferase_demand)
            and water >= peptidase_demand
            and (transferase_demand == 0.0 or pg160 >= transferase_demand)
        )
        nontrivial = (peptidase_demand + float(unproc[passthrough_idx].sum())) > 0.0

        if not regime_valid:
            out.append(
                UnitPrediction(
                    seed=seed,
                    tick=tick,
                    unit="all",
                    regime_valid=False,
                    regime_reason="capacity_or_metabolite_guard_failed",
                    nontrivial=False,
                    predicted_delta={},
                )
            )
            continue

        n_substrates = before["substrates"].shape[1]
        substrates_delta = np.zeros(n_substrates, dtype=np.float64)
        substrates_delta[water_0b] -= peptidase_demand
        substrates_delta[pg160_0b] -= transferase_demand
        substrates_delta[snglyp_0b] += transferase_demand
        substrates_delta[hydrogen_0b] += transferase_demand

        unproc_delta = -unproc.copy()
        processed_delta = unproc.copy()
        signal_delta = np.zeros_like(unproc)
        signal_delta[peptidase_idx] = unproc[peptidase_idx]
        # passthrough species are not signal-cleaved
        signal_delta[passthrough_idx] = 0.0

        out.append(
            UnitPrediction(
                seed=seed,
                tick=tick,
                unit="all",
                regime_valid=True,
                regime_reason="full_saturating_closed_form",
                nontrivial=nontrivial,
                predicted_delta={
                    "unprocessedMonomers": unproc_delta,
                    "processedMonomers": processed_delta,
                    "signalSequenceMonomers": signal_delta,
                    "substrates": substrates_delta,
                    "enzymes": np.zeros_like(enzymes),
                },
            )
        )
    return out


def predict_protein_folding(seed: int, before: dict, fixture: dict) -> list[UnitPrediction]:
    """ProteinFolding.m evolveState (source lines 519-575).

    `complexIndexs_notFolding` complexes pass through unconditionally
    (lines 520-523, always deterministic). For the 487 folding-eligible
    species (all 482 monomers + 5 folding complexes), Karr's own species
    vector treats chaperones as non-limiting by construction
    (`this.enzymes * Inf`; a zero-count required chaperone yields NaN,
    which MATLAB's min() ignores unless every column is NaN/Inf — line
    535). Only the 11 prosthetic-group substrate columns (excluding water
    [NaN'd at line 546] and hydrogen [line 547]) can be genuinely limiting.
    If, for every prosthetic-group substrate column (excl. water/H), the
    aggregate demand from folding ALL unfolded species this tick does not
    exceed the pre-tick available amount, the resource never reaches zero
    before every species' own self-column (its unfolded count) does —
    guaranteeing full folding of the entire unfolded pool this tick,
    regardless of RNG path (see H12 derivation notes for the invariant
    argument).
    """
    water_0b = fixture["substrateIndexs_water_0b"]
    hydrogen_0b = fixture["substrateIndexs_hydrogen_0b"]
    ppg = fixture["proteinProstheticGroupMatrix"]  # (683, 11) rows = ALL monomers+complexes
    folded_rows = fixture["monomerComplexIndexs_folded_0b"]  # (487,) into the 683-row space
    complex_folding_0b = fixture["complexIndexs_folding_0b"]  # (5,) into 201-complex space
    complex_notfolding_0b = fixture["complexIndexs_notFolding_0b"]  # (196,)
    species_idx_monomers = fixture["speciesIndexs_monomers_0b"]  # (482,) positions within the 487-row block
    species_idx_complexs = fixture["speciesIndexs_complexs_0b"]  # (5,)

    ppg_folded = ppg[folded_rows, :]  # (487, 11)
    n_substrate_cols = ppg.shape[1]
    guard_cols = [c for c in range(n_substrate_cols) if c not in (water_0b, hydrogen_0b)]

    n_ticks = before["unfoldedMonomers"].shape[0]
    out: list[UnitPrediction] = []
    for tick in range(n_ticks):
        unfolded_monomers = before["unfoldedMonomers"][tick].astype(np.float64)
        unfolded_complexs = before["unfoldedComplexs"][tick].astype(np.float64)
        substrates_before = before["substrates"][tick].astype(np.float64)

        flux = np.zeros(len(folded_rows), dtype=np.float64)
        flux[species_idx_monomers] = unfolded_monomers
        flux[species_idx_complexs] = unfolded_complexs[complex_folding_0b]

        demand = ppg_folded.T @ flux  # (11,)
        regime_valid = all(demand[c] <= substrates_before[c] for c in guard_cols)
        nontrivial = bool(np.any(flux > 0))

        # notFolding complexes pass through unconditionally regardless of guard
        complexs_delta = np.zeros_like(unfolded_complexs)
        complexs_delta[complex_notfolding_0b] = 0.0  # tracked via foldedComplexs below

        if not regime_valid:
            out.append(
                UnitPrediction(
                    seed=seed,
                    tick=tick,
                    unit="all",
                    regime_valid=False,
                    regime_reason="prosthetic_group_guard_failed",
                    nontrivial=False,
                    predicted_delta={
                        # only the unconditional not-folding passthrough is safe to assert
                        "unfoldedComplexs_notfolding_only": complex_notfolding_0b,
                    },
                )
            )
            continue

        substrates_delta = np.zeros_like(substrates_before)
        substrates_delta[:] = -(ppg_folded.T @ flux)

        unfolded_complexs_delta = np.zeros_like(unfolded_complexs)
        unfolded_complexs_delta[complex_folding_0b] = -flux[species_idx_complexs]
        unfolded_complexs_delta[complex_notfolding_0b] = -unfolded_complexs[complex_notfolding_0b]

        folded_complexs_delta = np.zeros_like(unfolded_complexs)
        folded_complexs_delta[complex_folding_0b] = flux[species_idx_complexs]
        folded_complexs_delta[complex_notfolding_0b] = unfolded_complexs[complex_notfolding_0b]

        out.append(
            UnitPrediction(
                seed=seed,
                tick=tick,
                unit="all",
                regime_valid=True,
                regime_reason="full_saturating_closed_form_chaperones_nonlimiting",
                nontrivial=nontrivial,
                predicted_delta={
                    "unfoldedMonomers": -unfolded_monomers,
                    "foldedMonomers": unfolded_monomers.copy(),
                    "unfoldedComplexs": unfolded_complexs_delta,
                    "foldedComplexs": folded_complexs_delta,
                    "substrates": substrates_delta,
                    "enzymes": np.zeros_like(before["enzymes"][tick]),
                },
            )
        )
    return out


def predict_trna_aminoacylation(seed: int, before: dict, fixture: dict) -> list[UnitPrediction]:
    """tRNAAminoacylation.m evolveState (source lines 387-460).

    species = [substrates; enzymes[speciesIndexs_enzymes]; freeRNAs]
    Per-tick loop repeatedly consumes `speciesReactantByproductMatrix` rows
    (one row per tRNA) until `reactionLimits` (capacity ratios, water/H
    exempted) hit zero. Because the tRNA's own free-count column is itself
    one of the ratio columns (identity-like diagonal), a resource other
    than the tRNA's own free-count can only zero out `reactionLimits[j]`
    prematurely if that OTHER resource's total pre-tick supply is smaller
    than the aggregate demand summed across every tRNA/enzyme-budget column
    (substrates, and enzyme "budget" -- enzymes are consumed as a
    within-tick throughput budget, not physically depleted; see citation).
    If, for every non-(water/hydrogen) column, aggregate demand
    (sum_j byproduct[j, c] * freeRNAs_before[j]) does not exceed pre-tick
    supply, every freeRNA gets aminoacylated this tick deterministically
    (empirically spot-verified against real oracle data: seed 0 tick 0).
    Substrate deltas then follow the (separately documented, non-loop)
    bookkeeping formula at lines 458-462:
        substrates += reactionStoichiometryMatrix @ reactionModificationMatrix @ reactionFluxes
    with reactionFluxes == freeRNAs_before (full saturation).
    """
    water_0b = fixture["substrateIndexs_water_0b"]
    hydrogen_0b = fixture["substrateIndexs_hydrogen_0b"]
    enz_cols_0b = fixture["speciesIndexs_enzymes_0b"]  # (21,) column positions in the 88-col species space
    byproduct = fixture["speciesReactantByproductMatrix"]  # (37, 88)
    reaction_stoich = fixture["reactionStoichiometryMatrix"]  # (30, 39)
    reaction_mod = fixture["reactionModificationMatrix"]  # (39, 37)

    n_substrates = reaction_stoich.shape[0]
    n_enz = len(enz_cols_0b)
    enz_col_start = n_substrates  # substrates block occupies cols [0, n_substrates)
    freerna_col_start = n_substrates + n_enz

    guard_cols = [c for c in range(byproduct.shape[1]) if c not in (water_0b, hydrogen_0b, *range(freerna_col_start, byproduct.shape[1]))]

    n_ticks = before["freeRNAs"].shape[0]
    out: list[UnitPrediction] = []
    for tick in range(n_ticks):
        free_rnas = before["freeRNAs"][tick].astype(np.float64)
        aminoacylated = before["aminoacylatedRNAs"][tick].astype(np.float64)
        substrates_before = before["substrates"][tick].astype(np.float64)
        enzymes_before = before["enzymes"][tick].astype(np.float64)

        species_before = np.concatenate([substrates_before, enzymes_before[: n_enz], np.zeros(0)])
        # column-wise available supply for the guard: substrates + enzyme-budget columns
        supply = np.concatenate([substrates_before, enzymes_before[:n_enz]])

        demand = byproduct[:, : freerna_col_start].T @ free_rnas  # (n_substrates+n_enz,)
        regime_valid = all(demand[c] <= supply[c] for c in guard_cols)
        nontrivial = bool(np.any(free_rnas > 0))

        if not regime_valid:
            out.append(
                UnitPrediction(
                    seed=seed,
                    tick=tick,
                    unit="all",
                    regime_valid=False,
                    regime_reason="resource_guard_failed",
                    nontrivial=False,
                    predicted_delta={},
                )
            )
            continue

        reaction_fluxes = free_rnas.copy()  # (37,) per-RNA meta-reaction fluxes
        substrates_delta = reaction_stoich @ (reaction_mod @ reaction_fluxes)

        out.append(
            UnitPrediction(
                seed=seed,
                tick=tick,
                unit="all",
                regime_valid=True,
                regime_reason="full_saturating_closed_form",
                nontrivial=nontrivial,
                predicted_delta={
                    "freeRNAs": -free_rnas,
                    "aminoacylatedRNAs": free_rnas.copy(),
                    "substrates": substrates_delta,
                    "enzymes": np.zeros_like(enzymes_before),
                },
            )
        )
    return out


PREDICTORS: dict[str, Callable[[int, dict, dict], list]] = {
    "MacromolecularComplexation": predict_macromolecular_complexation,
    "ProteinProcessingI": predict_protein_processing_i,
    "ProteinProcessingII": predict_protein_processing_ii,
    "ProteinFolding": predict_protein_folding,
    "tRNAAminoacylation": predict_trna_aminoacylation,
}


# ---------------------------------------------------------------------------
# Compare phase — the ONLY place states_after is read.
# ---------------------------------------------------------------------------


def compare_predictions(process: str, predictions: list[UnitPrediction], after: dict, before: dict) -> dict:
    """Compare frozen predictions against states_after. Never called before
    predictions are fully computed; states_after must not leak into predict_*.
    """
    total = 0
    nontrivial = 0
    exact_match = 0
    mismatches = []

    by_tick: dict[int, list[UnitPrediction]] = {}
    for p in predictions:
        by_tick.setdefault(p.tick, []).append(p)

    for tick, units in by_tick.items():
        for u in units:
            total += 1
            if not u.regime_valid:
                continue
            if not u.nontrivial:
                # still verify trivial (all-zero) predictions to catch guard bugs,
                # but exclude from the headline nontrivial_sample_count.
                ok = True
                for channel, delta in u.predicted_delta.items():
                    if channel.endswith("_only"):
                        continue
                    actual = after[channel][tick] - before[channel][tick]
                    if not np.array_equal(actual, delta):
                        ok = False
                        break
                if not ok and len(mismatches) < 10:
                    mismatches.append({"seed": u.seed, "tick": tick, "unit": u.unit, "trivial": True})
                continue

            nontrivial += 1
            ok = True
            for channel, delta in u.predicted_delta.items():
                if channel.endswith("_only"):
                    continue
                actual = after[channel][tick] - before[channel][tick]
                if not np.array_equal(actual, delta):
                    ok = False
                    if len(mismatches) < 10:
                        idx = np.where(actual != delta)[0][:5]
                        mismatches.append(
                            {
                                "seed": u.seed,
                                "tick": tick,
                                "unit": u.unit,
                                "channel": channel,
                                "mismatch_indices": idx.tolist(),
                                "predicted": delta[idx].tolist(),
                                "actual": actual[idx].tolist(),
                            }
                        )
                    break
            if ok:
                exact_match += 1

    return {
        "total_sample_count": total,
        "nontrivial_sample_count": nontrivial,
        "exact_match_count": exact_match,
        "exact_match_rate": (exact_match / nontrivial) if nontrivial > 0 else None,
        "mismatch_examples": mismatches,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def decide_verdict(nontrivial: int, exact_match: int, exact_match_rate: float | None) -> tuple[str, str]:
    """Pure H12 verdict decision, factored out of `run_h12` so it is
    independently unit-testable without oracle/fixture I/O (see
    `tests/scripts/test_h12_artifact.py`).

    H12_CONFIRMED requires BOTH `nontrivial_sample_count > 0` AND a 100%
    exact match on those nontrivial samples -- no tolerance, per the task's
    "no tolerance unless source defines integer/float tolerance
    pre-registered" rule (no process here defines one).
    """
    if nontrivial > 0 and exact_match == nontrivial:
        return "H12_CONFIRMED", "nontrivial_sample_count>0 and 100% exact match"
    if nontrivial == 0:
        return "H12_FAIL", "nontrivial_sample_count==0 (no samples exercised the guard-satisfied regime)"
    return "H12_FAIL", f"exact_match_rate={exact_match_rate:.6f} < 1.0"


def run_h12(process: str, n_seeds: int, m_ticks: int) -> dict:
    fixture = load_fixture(process)
    predictor = PREDICTORS[process]

    all_predictions: list[UnitPrediction] = []
    oracle_hashes: dict[str, str] = {}
    prediction_hash_parts = []

    for seed in range(n_seeds):
        before, after, sha = load_oracle_seed(process, seed, m_ticks)
        oracle_hashes[str(seed)] = sha
        preds = predictor(seed, before, fixture)
        all_predictions.extend(preds)
        for p in preds:
            prediction_hash_parts.append(
                f"{p.seed}:{p.tick}:{p.unit}:{p.regime_valid}:{p.nontrivial}:"
                + ",".join(f"{k}={_sha256_array(v)}" for k, v in sorted(p.predicted_delta.items()) if isinstance(v, np.ndarray))
            )
        # release `after` reference for this seed; comparisons happen below,
        # re-loading is avoided by comparing per-seed immediately instead.

    raw_prediction_hash = _sha256_bytes("\n".join(prediction_hash_parts).encode("utf-8"))

    # Compare phase: reload per-seed (states_after untouched until here)
    total = nontrivial = exact_match = 0
    mismatches: list = []
    preds_by_seed: dict[int, list[UnitPrediction]] = {}
    for p in all_predictions:
        preds_by_seed.setdefault(p.seed, []).append(p)

    for seed in range(n_seeds):
        before, after, _sha = load_oracle_seed(process, seed, m_ticks)
        result = compare_predictions(process, preds_by_seed.get(seed, []), after, before)
        total += result["total_sample_count"]
        nontrivial += result["nontrivial_sample_count"]
        exact_match += result["exact_match_count"]
        if len(mismatches) < 10:
            mismatches.extend(result["mismatch_examples"][: 10 - len(mismatches)])

    exact_match_rate = (exact_match / nontrivial) if nontrivial > 0 else None
    verdict, verdict_reason = decide_verdict(nontrivial, exact_match, exact_match_rate)

    module_path = Path(__file__).resolve()
    artifact = {
        "process": process,
        "formula_version": FORMULA_VERSION,
        "predictor_source_path": str(module_path.relative_to(REPO_ROOT)),
        "predictor_source_sha256": _sha256_file(module_path),
        "fixture_path": fixture["__fixture_path__"],
        "fixture_sha256": fixture["__fixture_sha256__"],
        "oracle_seed_file_sha256": oracle_hashes,
        "n_seeds": n_seeds,
        "m_ticks": m_ticks,
        "catalog_n_seeds": CATALOG_N_M[process][0],
        "catalog_m_ticks": CATALOG_N_M[process][1],
        "total_sample_count": total,
        "nontrivial_sample_count": nontrivial,
        "exact_match_count": exact_match,
        "exact_match_rate": exact_match_rate,
        "mismatch_examples": mismatches,
        "raw_prediction_hash": raw_prediction_hash,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "anti_laundering_attestation": {
            "predictor_inputs": ["states_before", "static_fixture_params"],
            "states_after_access": "compare_phase_only",
            "no_sut_import": True,
            "no_result_json_access": True,
        },
    }
    return artifact


def write_artifact(artifact: dict, out_dir: Path = OUT_ROOT) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{artifact['process']}_h12.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2, sort_keys=False)
        fh.write("\n")
    return out_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run H12 machine evidence for a process")
    parser.add_argument("process", choices=list(PREDICTORS.keys()) + ["all"])
    parser.add_argument("--n-seeds", type=int, default=None)
    parser.add_argument("--m-ticks", type=int, default=None)
    args = parser.parse_args(argv)

    processes = RISK_ORDER if args.process == "all" else [args.process]
    for process in processes:
        cat_n, cat_m = CATALOG_N_M[process]
        n_seeds = args.n_seeds or cat_n
        m_ticks = args.m_ticks or cat_m
        print(f"[h12] running {process} n_seeds={n_seeds} m_ticks={m_ticks}", file=sys.stderr)
        artifact = run_h12(process, n_seeds, m_ticks)
        path = write_artifact(artifact)
        print(
            f"[h12] {process}: verdict={artifact['verdict']} "
            f"nontrivial={artifact['nontrivial_sample_count']} "
            f"match_rate={artifact['exact_match_rate']} -> {path}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
