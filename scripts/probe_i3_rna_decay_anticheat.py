from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests" / "vivarium"
for candidate in (REPO_ROOT, TESTS_DIR):
    text = str(candidate)
    if text not in sys.path:
        sys.path.insert(0, text)

if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402


def main() -> int:
    oracle = runner_helpers.load_karr_oracle("RNADecay")
    process = runner_helpers._rna_decay_process(0)
    substrate_wids = list(process.substrate_wids)
    enzyme_wids = list(process.enzyme_wids)
    rna_wids = [str(x) for x in getattr(process, "gene_ids", getattr(process, "rna_wids", ()))]

    tick = 0
    honest_state = {
        "substrate_wids": substrate_wids,
        "enzyme_wids": enzyme_wids,
        "rna_wids": rna_wids,
        "oracle_before_substrates": np.asarray(oracle["before_substrates"], dtype=np.float64)[0, tick],
        "oracle_after_substrates": np.asarray(oracle["after_substrates"], dtype=np.float64)[0, tick],
        "oracle_before_enzymes": np.asarray(oracle["before_enzymes"], dtype=np.float64)[0, tick],
        "oracle_before_bound_enzymes": np.asarray(oracle["before_bound_enzymes"], dtype=np.float64)[0, tick],
        "oracle_before_rnas": np.asarray(oracle["before_rnas"], dtype=np.float64)[0, tick],
        "oracle_after_rnas": np.asarray(oracle["after_rnas"], dtype=np.float64)[0, tick],
    }
    cheated_state = dict(honest_state)
    cheated_state["oracle_after_substrates"] = np.zeros_like(honest_state["oracle_after_substrates"], dtype=np.float64)
    cheated_state["oracle_after_rnas"] = np.zeros_like(honest_state["oracle_after_rnas"], dtype=np.float64)

    runner_helpers._rna_decay_process.cache_clear()
    honest = runner_helpers._run_rna_decay_tick(0, tick, honest_state)
    runner_helpers._rna_decay_process.cache_clear()
    cheated = runner_helpers._run_rna_decay_tick(0, tick, cheated_state)
    honest_rnas = np.asarray(honest["RNAs"], dtype=np.float64)
    cheated_rnas = np.asarray(cheated["RNAs"], dtype=np.float64)

    report = {
        "process": "RNADecay",
        "probe": "anti_laundering_zero_after_payload",
        "tick": tick,
        "honest_rna_sum": float(np.sum(honest_rnas)),
        "cheated_rna_sum": float(np.sum(cheated_rnas)),
        "cheated_is_all_zero": bool(np.count_nonzero(cheated_rnas) == 0),
        "max_abs_diff_honest_vs_cheated": float(np.max(np.abs(honest_rnas - cheated_rnas))),
        "outputs_match_exactly": bool(np.array_equal(honest_rnas, cheated_rnas)),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
