#!/usr/bin/env python3
"""Empirical probe for V4 MF4 admission at sample (seed=0, tick=1).

This script is investigation-only. It does not modify any implementation code
or fixtures. It produces one JSON report at ``tmp/v4_probe_results.json`` and
exits 0 when all probe sections ran, even if the measured LP / mutation results
do not pass their respective criteria. It exits 1 only on hard errors such as a
missing required file or a solver/runtime failure that prevents the probe from
running.
"""

from __future__ import annotations

import json
import math
import sys
import traceback
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.io import loadmat

from opencell.m1.karr_metabolism import KarrMetabolismModel, solve_fba
from opencell.m1.karr_metabolism_writeback import (
    KarrWritebackFixture,
    apply_karr_substrate_writeback,
)
from opencell.vivarium.karr_protein_decay_light import _Mcg16807

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "data" / "karr_fixtures" / "per_process" / "Metabolism_flat.mat"
GROUND_TRUTH_PATH = (
    ROOT
    / "data"
    / "karr_fixtures"
    / "matlab_ground_truth"
    / "metab_flux_allocated_state_s000_tick1.mat"
)
TRACE_PATH = (
    ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "per_process_traces_v2_s000"
    / "Metabolism_100ticks.mat"
)
REPORT_PATH = ROOT / "tmp" / "v4_probe_results.json"

TOP17_WIDS = [
    "OCDCEA",
    "H2O2",
    "O2",
    "TRP",
    "TRIOLEIN",
    "TYR",
    "GL",
    "AC",
    "PHE",
    "TrpTrp",
    "H2O",
    "TyrTyr",
    "GLC",
    "ACAL",
    "AEPP",
    "CAP",
    "PhePhe",
]
ALPHAS = [1.0, 0.75, 0.5, 0.25, 0.10, 0.05, 0.01]
TAU_FORMULAS = {
    "tau_A": lambda x: max(1.0, 3e-4 * abs(x)),
    "tau_B": lambda x: max(40.0, 0.03 * abs(x)),
    "tau_C": lambda x: max(100.0, 0.10 * abs(x)),
}
WRITEBACK_SEED = 12345
MUTATION_SHUFFLE_SEED = 99
TOP27_COUNT = 27
I4_SPEARMAN_THRESHOLD = 0.95
I4_SIGN_THRESHOLD = 15
I6_SIGN_SHARE_THRESHOLD = 0.80


class HardProbeError(RuntimeError):
    """Raised for hard probe failures that should exit with status 1."""


def _require_file(path: Path) -> Path:
    if not path.exists():
        raise HardProbeError(f"required file missing: {path}")
    return path


def load_fixture_mat(path: Path) -> Any:
    _require_file(path)
    return loadmat(str(path), squeeze_me=True, struct_as_record=False)["data"].fixture


def load_ground_truth(path: Path) -> dict[str, np.ndarray]:
    _require_file(path)
    with h5py.File(path, "r") as handle:
        return {
            "flux": np.asarray(handle["flux"], dtype=np.float64).reshape(-1),
            "bounds": np.asarray(handle["bounds"], dtype=np.float64),
            "delta": np.asarray(handle["delta"], dtype=np.float64).T,
            "growth": np.asarray(handle["growth"], dtype=np.float64).reshape(-1)[0],
            "pre_sub": np.asarray(handle["pre_sub"], dtype=np.float64).T,
            "post_sub": np.asarray(handle["post_sub"], dtype=np.float64).T,
        }


def build_report_shell() -> dict[str, Any]:
    return {
        "sample": {"seed": 0, "tick": 1},
        "paths": {
            "fixture_mat": str(FIXTURE_PATH),
            "ground_truth_mat": str(GROUND_TRUTH_PATH),
            "trace_mat": str(TRACE_PATH),
            "report_json": str(REPORT_PATH),
        },
        "constants": {
            "top17_wids": TOP17_WIDS,
            "alphas": ALPHAS,
            "writeback_seed": WRITEBACK_SEED,
            "tau_formulas": {
                "tau_A": "max(1, 3e-4 * |karr_delta_j|)",
                "tau_B": "max(40, 0.03 * |karr_delta_j|)",
                "tau_C": "max(100, 0.10 * |karr_delta_j|)",
            },
        },
        "sections": {
            "precheck": {},
            "karr_feasibility": {},
            "joint_lp": {},
            "line_search": {},
            "surrogate_accuracy": {},
            "mutation_matrix": {},
        },
        "assumptions": [],
        "errors": [],
    }


def main() -> int:
    try:
        report = build_report_shell()
        fixture = load_fixture_mat(FIXTURE_PATH)
        ground_truth = load_ground_truth(GROUND_TRUTH_PATH)

        report["fixture_shapes"] = {
            "S": list(np.asarray(fixture.fbaReactionStoichiometryMatrix).shape),
            "bounds": list(np.asarray(fixture.fbaReactionBounds).shape),
            "objective": list(np.asarray(fixture.fbaObjective).shape),
            "delta": list(ground_truth["delta"].shape),
            "pre_sub": list(ground_truth["pre_sub"].shape),
            "post_sub": list(ground_truth["post_sub"].shape),
        }

        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except HardProbeError as exc:
        sys.stderr.write(f"HARD ERROR: {exc}\n")
        return 1
    except Exception as exc:  # pragma: no cover - investigation hard-stop path
        sys.stderr.write(f"HARD ERROR: {exc}\n")
        sys.stderr.write(traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
