from __future__ import annotations

import json
import sys
from collections import Counter
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


def _project_round_trip(
    *,
    process: object,
    vector: np.ndarray,
    wids: list[str],
) -> np.ndarray:
    runtime_state = runner_helpers.build_state_template(process)
    runner_helpers.overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="RNAs",
        vector=np.asarray(vector, dtype=np.float64),
        wids=wids,
        store_path_override=runner_helpers._RNA_STORE_PATH_OVERRIDE,
    )
    return np.asarray(
        runner_helpers.project_observable_from_state(
            process=process,
            state=runtime_state,
            observable="RNAs",
            wids=wids,
            bound_enzymes_before=np.zeros(len(process.enzyme_wids), dtype=np.float64),
            store_path_override=runner_helpers._RNA_STORE_PATH_OVERRIDE,
        ),
        dtype=np.float64,
    )


def main() -> int:
    oracle = runner_helpers.load_karr_oracle("RNADecay")
    process = runner_helpers._rna_decay_process(0)
    rna_wids = [str(x) for x in getattr(process, "gene_ids", getattr(process, "rna_wids", ()))]
    counts = Counter(rna_wids)

    before_all = np.asarray(oracle["before_rnas"], dtype=np.float64)[0]
    after_all = np.asarray(oracle["after_rnas"], dtype=np.float64)[0]
    tick0_before = before_all[0]
    tick0_round_trip = _project_round_trip(process=process, vector=tick0_before, wids=rna_wids)
    round_trip_all = np.asarray(
        [
            _project_round_trip(process=process, vector=before_all[tick], wids=rna_wids)
            for tick in range(int(before_all.shape[0]))
        ],
        dtype=np.float64,
    )

    report = {
        "process": "RNADecay",
        "probe": "duplicate_wid_round_trip",
        "oracle_path": str(runner_helpers._RNA_DECAY_ORACLE_PATH.relative_to(REPO_ROOT)),
        "rna_wids_total": int(len(rna_wids)),
        "rna_wids_unique": int(len(counts)),
        "rna_wids_with_duplicates": int(sum(1 for n in counts.values() if n > 1)),
        "tick0": {
            "mean_raw_before": float(np.mean(tick0_before)),
            "mean_round_trip": float(np.mean(tick0_round_trip)),
            "max_abs_diff": float(np.max(np.abs(tick0_round_trip - tick0_before))),
            "mismatch_count": int(np.count_nonzero(tick0_round_trip != tick0_before)),
        },
        "all_ticks": {
            "n_ticks": int(before_all.shape[0]),
            "mean_raw_before": float(np.mean(before_all)),
            "mean_round_trip_before": float(np.mean(round_trip_all)),
            "mean_w1_round_trip_before_vs_after": float(
                np.mean(
                    [
                        runner_helpers.compute_w1(round_trip_all[tick], after_all[tick])
                        for tick in range(int(before_all.shape[0]))
                    ]
                )
            ),
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
