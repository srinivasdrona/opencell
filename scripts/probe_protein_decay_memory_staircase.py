"""Memory staircase profiler for the ProteinDecay Design-A per-tick harness.

Reproduces the reported ~0.78 GiB/min unbounded RSS growth at N=50/M=200 by
driving `_run_protein_decay_tick` directly (bypassing the sweep subprocess)
across an N/M staircase, tracking RSS (`resource.getrusage`), the seed-keyed
process-constructor `lru_cache` size (`cache_info().currsize`), and live
instance counts via `gc`. Read-only diagnostic; does not modify runner
behavior. Run with `bin\\oc-py scripts\\probe_protein_decay_memory_staircase.py`.
"""

from __future__ import annotations

import gc
import resource
import sys
import time
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.vivarium import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402


def _rss_mb() -> float:
    # ru_maxrss is KB on Linux.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _live_instance_count(cls_name: str) -> int:
    return sum(1 for obj in gc.get_objects() if type(obj).__name__ == cls_name)


def _build_state(process) -> dict[str, object]:
    substrate_wids = list(process.substrate_wids)
    enzyme_wids = list(process.enzyme_wids)
    monomer_wids = list(process.protein_wids)
    complex_wids = list(process.complex_wids)
    return {
        "substrate_wids": substrate_wids,
        "enzyme_wids": enzyme_wids,
        "monomer_wids": monomer_wids,
        "complex_wids": complex_wids,
        "oracle_before_substrates": np.zeros(len(substrate_wids), dtype=np.float64),
        "oracle_before_enzymes": np.zeros(len(enzyme_wids), dtype=np.float64),
        "oracle_before_monomers": np.zeros(len(monomer_wids), dtype=np.float64),
        "oracle_before_complexs": np.zeros(len(complex_wids), dtype=np.float64),
        "oracle_after_substrates": np.full(len(substrate_wids), 17.0, dtype=np.float64),
        "oracle_after_monomers": np.full(len(monomer_wids), 100.0, dtype=np.float64),
        "oracle_after_complexs": np.full(len(complex_wids), 23.0, dtype=np.float64),
    }


def run_step(n_seeds: int, m_ticks: int) -> None:
    runner_helpers._protein_decay_process.cache_clear()
    gc.collect()
    rss_before = _rss_mb()
    t0 = time.time()

    # A representative state is shared across ticks: it only depends on
    # process wid ordering, which is identical across process instances.
    seed0_process = runner_helpers._protein_decay_process(runner_helpers._sample_seed(0, 0))
    state = _build_state(seed0_process)

    n_calls = 0
    for seed in range(n_seeds):
        for tick in range(m_ticks):
            runner_helpers._run_protein_decay_tick(seed, tick, state)
            n_calls += 1

    elapsed = time.time() - t0
    gc.collect()
    rss_after = _rss_mb()
    cache_info = runner_helpers._protein_decay_process.cache_info()
    live = _live_instance_count("ProteinDecayLightProcess")
    print(
        f"N={n_seeds:3d} M={m_ticks:4d} calls={n_calls:6d} "
        f"rss_before={rss_before:9.1f}MiB rss_after={rss_after:9.1f}MiB "
        f"delta={rss_after - rss_before:9.1f}MiB "
        f"cache_currsize={cache_info.currsize:6d} live_instances={live:6d} "
        f"elapsed_s={elapsed:6.2f} MiB_per_call={(rss_after - rss_before) / max(n_calls, 1):8.4f}"
    )


def main() -> None:
    print("--- ProteinDecay per-tick memory staircase (_protein_decay_process lru_cache) ---")
    for n_seeds, m_ticks in ((1, 20), (5, 50), (10, 100)):
        run_step(n_seeds, m_ticks)


if __name__ == "__main__":
    main()
