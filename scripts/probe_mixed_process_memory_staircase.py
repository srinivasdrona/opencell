"""Mixed-process memory staircase profiler for scope-C1's 18 per-tick
process factories (Opus5 review of commit 8eaa927).

Unlike `probe_protein_decay_memory_staircase.py` (which exercises one
process's full tick pipeline), this profiler drives the process
*factories* directly across an N/M staircase for a representative subset
spanning every family in the helper module: Metabolism (heaviest process,
depends on separately-cached model/dynamics singletons), one RNA-family
process (Transcription), one protein-family process (ProteinFolding), the
two "shared metadata cache" processes (MacromolecularComplexation,
Cytokinesis), and two DNA-family processes (DNARepair,
ReplicationInitiation). Calling factories directly (rather than full
`_run_*_tick`) avoids needing to fabricate a valid `ChromosomeStore` for
the DNA family while still exercising the exact construction path that
was previously leaking (`@lru_cache(maxsize=None)` keyed on
`_sample_seed(seed, tick)`).

Read-only diagnostic; does not modify runner behavior. Run with
`bin\\oc-py scripts\\probe_mixed_process_memory_staircase.py`.
"""

from __future__ import annotations

import gc
import resource
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.vivarium import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402


# (factory attribute name, constructed class name for gc live-instance count)
_PROFILED_FACTORIES: tuple[tuple[str, str], ...] = (
    ("_metabolism_process", "KarrMetabolismProcess"),
    ("_transcription_process", "KarrTranscriptionProcess"),
    ("_protein_folding_process", "KarrProteinFoldingProcess"),
    ("_macromol_process", "MacromolecularComplexationProcess"),
    ("_cytokinesis_process", "KarrCytokinesisProcess"),
    ("_dna_repair_process", "KarrDNARepairProcess"),
    ("_replication_initiation_process", "KarrReplicationInitiationProcess"),
)


def _current_rss_mb() -> float:
    """Current resident set size in MiB, read from /proc/self/status'
    `VmRSS:` line (Linux/WSL only). This is the correct metric for a
    before/after-this-step comparison: unlike `ru_maxrss` (see
    `_high_water_rss_mb` below), it can go up *or* down between two
    readings, reflecting what is actually live right now."""
    with open("/proc/self/status", "r", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("VmRSS:"):
                # Format: "VmRSS:	   12345 kB"
                return float(line.split()[1]) / 1024.0
    raise RuntimeError("VmRSS not found in /proc/self/status")


def _high_water_rss_mb() -> float:
    """Peak (high-water mark) RSS in MiB via `ru_maxrss`. This value is
    monotonically non-decreasing for the process's lifetime -- it can only
    stay flat or increase, so it must NOT be used as a before/after-step
    comparison (a flat reading does not prove nothing grew, and a rising
    reading does not prove the *current* retained set is growing; it may
    already have shrunk back down). Reported here only as a supplementary,
    explicitly-labeled high-water figure alongside the current-RSS deltas
    that actually demonstrate (or refute) a growing/plateauing trend."""
    # ru_maxrss is KB on Linux.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _live_instance_count(cls_name: str) -> int:
    return sum(1 for obj in gc.get_objects() if type(obj).__name__ == cls_name)


def run_step(n_seeds: int, m_ticks: int) -> None:
    for factory_name, _ in _PROFILED_FACTORIES:
        getattr(runner_helpers, factory_name).cache_clear()
    gc.collect()
    rss_before = _current_rss_mb()
    t0 = time.time()

    n_calls = 0
    for seed in range(n_seeds):
        for tick in range(m_ticks):
            sample_seed = runner_helpers._sample_seed(seed, tick)
            for factory_name, _ in _PROFILED_FACTORIES:
                getattr(runner_helpers, factory_name)(sample_seed)
            n_calls += 1

    elapsed = time.time() - t0
    gc.collect()
    rss_after = _current_rss_mb()
    high_water = _high_water_rss_mb()
    print(
        f"N={n_seeds:3d} M={m_ticks:4d} calls={n_calls:6d} "
        f"rss_before={rss_before:9.1f}MiB rss_after={rss_after:9.1f}MiB "
        f"delta={rss_after - rss_before:9.1f}MiB elapsed_s={elapsed:6.2f} "
        f"MiB_per_call={(rss_after - rss_before) / max(n_calls, 1):8.4f} "
        f"high_water_rss={high_water:9.1f}MiB",
        flush=True,
    )
    for factory_name, cls_name in _PROFILED_FACTORIES:
        cache_info = getattr(runner_helpers, factory_name).cache_info()
        live = _live_instance_count(cls_name)
        print(
            f"    {factory_name:32s} cache_currsize={cache_info.currsize:4d} "
            f"(maxsize={cache_info.maxsize}) live_instances={live:4d}",
            flush=True,
        )


def main() -> None:
    print(
        "--- Mixed-process per-tick memory staircase (scope-C1, 7 of 18 factories) ---",
        flush=True,
    )
    # Kept deliberately small: this profiler constructs 7 heavyweight
    # processes (including Metabolism) per tick, so the call count is
    # multiplied 7x versus the single-process ProteinDecay staircase.
    # The staircase shape (increasing N*M) is what demonstrates plateau,
    # not the absolute scale of the largest step.
    for n_seeds, m_ticks in ((1, 10), (3, 30), (5, 60)):
        run_step(n_seeds, m_ticks)


if __name__ == "__main__":
    main()
