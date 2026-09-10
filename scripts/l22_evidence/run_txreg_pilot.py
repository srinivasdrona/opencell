"""Regenerate the TranscriptionalRegulation L2.2 PIT-gate pilot evidence
bundle (``docs/phase_f/l2_2_design_a/evidence_bundle/TranscriptionalRegulation/
latest_event/``) from the genuine seed-0 4000-tick event-window trace.

This is a committed, reusable regeneration entrypoint (not a throwaway tmp/
script) -- run it any time the underlying trace, the gate implementation
(``scripts/l22_evidence/txreg_pit_gate.py``), or the OC process implementation
(``opencell/vivarium/karr_transcriptional_regulation.py``) changes, since the
written bundle hash-binds all three (see
``txreg_pit_gate.write_evidence_bundle``). Verdict remains
``PILOT_ONLY_NOT_A_GATE_VERDICT`` -- N=10 full-cohort extraction is deferred
until an accepted preregistration design (see
``docs/phase_f/l2_2_design_a/TRANSCRIPTIONALREGULATION_ACTIVE_WINDOW_PREREG.md``).

Usage:
    bin\\oc-py.cmd scripts/l22_evidence/run_txreg_pilot.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.l22_evidence import txreg_pit_gate as gate  # noqa: E402

_TRACE_PATH = (
    _REPO_ROOT
    / "data"
    / "m1_sources"
    / "karr_native"
    / "per_process_traces_v2_event_s000"
    / "TranscriptionalRegulation_4000ticks.mat"
)
_ANALYSIS_RNG_SEED = 12345


def main() -> None:
    if not _TRACE_PATH.exists():
        raise FileNotFoundError(
            f"genuine trace not found at {_TRACE_PATH} -- this is gitignored, "
            "regenerate-on-demand evidence data; extract it first via "
            "scripts/matlab/extract_per_process_traces_v2.m (process="
            "'TranscriptionalRegulation', output_subdir="
            "'per_process_traces_v2_event_s000', n_ticks=4000, seed=0, "
            "tick_offset=0, window_contract='fixed') and reconstruct its "
            "ledger sidecar via scripts/matlab/reconstruct_chromosome_draw_ledger.m"
        )

    events = gate.extract_competition_events(_TRACE_PATH)
    print(f"n_events: {len(events)}")
    n_with_winner = sum(1 for e in events if e.winner_local_indices)
    print(f"n_events_with_winner: {n_with_winner}")
    print("n_candidates histogram:", Counter(e.n_candidates for e in events))
    print("winner-count histogram:", Counter(len(e.winner_local_indices) for e in events))

    result = gate.compute_pit_values(events, analysis_rng_seed=_ANALYSIS_RNG_SEED)
    print(
        f"result: n_events={result.n_events} n_pooled={result.n_pooled_values} "
        f"ks_statistic={result.ks_statistic!r} ks_pvalue={result.ks_pvalue!r}"
    )
    if result.randomized_pit_values:
        mean_pit = sum(result.randomized_pit_values) / len(result.randomized_pit_values)
        print(f"mean randomized PIT: {mean_pit!r}")

    uniform_pc = gate.run_weight_law_positive_control(
        events, analysis_rng_seed=_ANALYSIS_RNG_SEED, perturbation="uniform_weights"
    )
    print(
        f"uniform_weights positive control: n_pooled={uniform_pc.n_pooled_values} "
        f"ks_statistic={uniform_pc.ks_statistic!r} ks_pvalue={uniform_pc.ks_pvalue!r}"
    )

    shuffled_pc = gate.run_weight_law_positive_control(
        events, analysis_rng_seed=_ANALYSIS_RNG_SEED, perturbation="shuffled_weights"
    )
    print(
        f"shuffled_weights positive control: n_pooled={shuffled_pc.n_pooled_values} "
        f"ks_statistic={shuffled_pc.ks_statistic!r} ks_pvalue={shuffled_pc.ks_pvalue!r}"
    )

    occlusion_pc = gate.run_positive_control(_TRACE_PATH, analysis_rng_seed=_ANALYSIS_RNG_SEED)
    print(
        f"occlusion_disabled positive control: n_pooled={occlusion_pc.n_pooled_values} "
        f"ks_statistic={occlusion_pc.ks_statistic!r} ks_pvalue={occlusion_pc.ks_pvalue!r}"
    )

    out_dir = gate.write_evidence_bundle(
        trace_path=_TRACE_PATH,
        result=result,
        positive_controls={
            "occlusion_disabled": occlusion_pc,
            "uniform_weights": uniform_pc,
            "shuffled_weights": shuffled_pc,
        },
    )
    print(f"wrote bundle to: {out_dir}")


if __name__ == "__main__":
    main()
