"""DNASupercoiling-specific persistent-process Design-A tick runner.

Extracted out of `_l2_2_design_a_runner_helpers.py` so that shared file can
stay byte-identical to `main` for every OTHER Design-A process. Before this
split, DNASupercoiling's persistent-process-pool fix (MATLAB reuses one
`DnaSupercoiling` object -- and therefore one persistent `randStream`
position -- across all 100 ticks of a seed, instead of reconstructing a
fresh process per tick) lived directly inside the shared runner-helpers
file. That is architecturally correct (MATLAB's real per-seed object
lifetime) but the shared file's whole-file sha256 is recorded, unconditionally,
in EVERY Design-A process's `sweep_provenance.json["source_hashes"]["helpers"]`
-- so editing it for DNASupercoiling alone mechanically staled all 18
Design-A rows (`generator.audit` moved from N PASS to 1 PASS / 19 FAIL / 2
MISSING). See `STATUS_L22_DNAS_INTEGRATION.md` for the full incident.

This module is a REGISTERED, process-specific runtime dependency of
DNASupercoiling ONLY (`scripts/l22_evidence/schema.py::PROCESS_DEPENDENCY_FILES
["DNASupercoiling"]["dnas_runner_helpers_module"]`, and, via the AST-static
`tick_runner_entry_hash("DNASupercoiling")`, the process-specific half of the
redesigned `"helpers"`/`"tick_runner"` provenance pair -- see that module's
docstring for the full R7 design). No other process imports or depends on
this file; editing it changes ONLY DNASupercoiling's provenance.

`_l2_2_design_a_runner_helpers.py` binds this module's `run_dna_supercoiling_tick`
to the local name `_run_dna_supercoiling_tick` via a plain
`from _l2_2_dnas_runner_helpers import run_dna_supercoiling_tick as
_run_dna_supercoiling_tick` -- so `_tick_dispatch()`'s dict body (`"DNASupercoiling":
_run_dna_supercoiling_tick,`) is completely unchanged text, and every OTHER
process's dispatch entry/body is untouched, byte-for-byte, from `main`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

_VIVARIUM_TESTS_DIR = Path(__file__).resolve().parent
if str(_VIVARIUM_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_VIVARIUM_TESTS_DIR))

_REPO_ROOT = _VIVARIUM_TESTS_DIR.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Shared, process-agnostic replay primitives -- already a registered
# `design_a_per_tick` harness dependency (`schema.HARNESS_DEPENDENCY_FILES
# ["design_a_per_tick"]["l2_replay_common"]`); importing it here adds no new
# provenance surface.
from l2_replay_common import (  # noqa: E402
    apply_count_update,
    build_state_template,
    forbid_sut_oracle_file_io,
    overlay_observable_into_state,
    project_observable_from_state,
    refresh_allocator_views,
)

from opencell.state.chromosome_store import ChromosomeStore  # noqa: E402
from opencell.vivarium.karr_dna_supercoiling import KarrDNASupercoilingProcess  # noqa: E402

__all__ = [
    "reset_dna_supercoiling_persistent_processes",
    "run_dna_supercoiling_tick",
]


def _construct_dna_supercoiling_process(seed: int) -> KarrDNASupercoilingProcess:
    with forbid_sut_oracle_file_io():
        return KarrDNASupercoilingProcess({"rng_seed": int(seed)})


class _DNASupercoilingPersistentProcessPool:
    """Keep one DNAS process per biological seed, matching MATLAB tick reuse.

    The runner still overlays every tick's `states_before` snapshot into a fresh
    runtime state dict, so only process-local state that MATLAB itself keeps on
    the process object (its persistent RNG stream and replay alignment flag) is
    allowed to survive across ticks.
    """

    def __init__(self) -> None:
        self._processes: dict[int, KarrDNASupercoilingProcess] = {}
        self._last_tick_by_seed: dict[int, int] = {}

    def reset(self, seed: int | None = None) -> None:
        if seed is None:
            self._processes.clear()
            self._last_tick_by_seed.clear()
            return

        biological_seed = int(seed)
        self._processes.pop(biological_seed, None)
        self._last_tick_by_seed.pop(biological_seed, None)

    def get(self, *, seed: int, tick: int) -> KarrDNASupercoilingProcess:
        biological_seed = int(seed)
        tick_i = int(tick)
        last_tick = self._last_tick_by_seed.get(biological_seed)

        # A restarted or rewound tick sequence is a new simulation pass for that
        # biological seed and therefore needs a fresh MATLAB-style process object.
        if last_tick is not None and tick_i <= last_tick:
            self.reset(seed=biological_seed)

        process = self._processes.get(biological_seed)
        if process is None:
            process = _construct_dna_supercoiling_process(biological_seed)
            self._processes[biological_seed] = process

        self._last_tick_by_seed[biological_seed] = tick_i
        return process


_DNA_SUPERCOILING_PERSISTENT_PROCESSES = _DNASupercoilingPersistentProcessPool()


def reset_dna_supercoiling_persistent_processes(seed: int | None = None) -> None:
    _DNA_SUPERCOILING_PERSISTENT_PROCESSES.reset(seed)


def run_dna_supercoiling_tick(seed: int, tick: int, state: dict[str, Any]) -> dict[str, Any]:
    """Run one OpenCell DNASupercoiling tick from a prepared state snapshot."""
    # Deferred (call-time, not module-scope) import: `_l2_2_design_a_runner_
    # helpers.py` imports THIS module at module scope (to bind
    # `_run_dna_supercoiling_tick`), so importing it back at OUR module scope
    # would be a circular import whose success depends on which module a
    # caller happens to import first. Resolving it lazily here -- guaranteed
    # to run long after both modules have finished loading -- sidesteps that
    # order-dependence entirely.
    import _l2_2_design_a_runner_helpers as _shared

    process = _DNA_SUPERCOILING_PERSISTENT_PROCESSES.get(seed=seed, tick=tick)
    runtime_state = build_state_template(process)
    substrate_wids = list(state["substrate_wids"])
    enzyme_wids = list(state["enzyme_wids"])

    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="substrates",
        vector=np.asarray(state["oracle_before_substrates"], dtype=np.float64),
        wids=substrate_wids,
    )
    overlay_observable_into_state(
        process=process,
        state=runtime_state,
        observable="enzymes",
        vector=np.asarray(state["oracle_before_enzymes"], dtype=np.float64),
        wids=enzyme_wids,
    )
    if "oracle_before_bound_enzymes" in state:
        overlay_observable_into_state(
            process=process,
            state=runtime_state,
            observable="boundEnzymes",
            vector=np.asarray(state["oracle_before_bound_enzymes"], dtype=np.float64),
            wids=enzyme_wids,
        )

    # CRITICAL: overlay Karr's actual chromosome state, not a fixture default
    # (Beat 4 failure mode F3).
    chrom_store_before: ChromosomeStore = state["oracle_before_chromosome_store"]
    _shared._overlay_chromosome_into_state(runtime_state, chrom_store_before)  # noqa: SLF001

    refresh_allocator_views(process, runtime_state)
    with forbid_sut_oracle_file_io():
        update = process.next_update(1.0, runtime_state)
    apply_count_update(runtime_state, update)

    chrom_update = update.get("chromosome", {}) if isinstance(update, dict) else {}
    chrom_after_store = _shared._apply_chromosome_update(chrom_store_before, chrom_update)  # noqa: SLF001

    return {
        "substrates": np.asarray(
            project_observable_from_state(
                process=process,
                state=runtime_state,
                observable="substrates",
                wids=substrate_wids,
                bound_enzymes_before=None,
            ),
            dtype=np.float64,
        ),
        "chromosome_after_store": chrom_after_store,
        "sample_seed": int(seed),
        "legacy_tick_sample_seed": _shared._sample_seed(seed, tick),  # noqa: SLF001
    }
