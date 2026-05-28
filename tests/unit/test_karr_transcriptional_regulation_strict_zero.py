"""Strict-zero paranoia tests for karr_transcriptional_regulation.

These tests pin two invariants for the TF-read path:

1. If a declared TF WID is missing from its mapped store at runtime, the
   process must raise (not silently zero-fill or fall back to the other store).
2. There must be no silent fallback to a global substrate store or to the
   "other" of (protein, complex) when a TF is present in the wrong store.

Pattern follows tests/unit/test_karr_<process>_strict_zero.py for the
dimer-port cohort: bare-process invocation (no Vivarium engine), one-shot
next_update call, KeyError expected.
"""

from __future__ import annotations

from typing import Any

import pytest

from opencell.vivarium.karr_transcriptional_regulation import (
    KarrTranscriptionalRegulationProcess,
)


def _build_process() -> KarrTranscriptionalRegulationProcess:
    return KarrTranscriptionalRegulationProcess({"rng_seed": 17})


def _seeded_protein_counts(process: KarrTranscriptionalRegulationProcess) -> dict[str, float]:
    return {wid: 0.0 for wid in process._protein_tf_wids}


def _seeded_complex_counts(process: KarrTranscriptionalRegulationProcess) -> dict[str, float]:
    return {wid: 0.0 for wid in process._complex_tf_wids}


def _seeded_binding(process: KarrTranscriptionalRegulationProcess) -> dict[str, dict[str, float]]:
    return {
        tf_wid: {tu_wid: 0.0 for tu_wid in process.tu_wids}
        for tf_wid in process.tf_wids
    }


def _baseline_state(process: KarrTranscriptionalRegulationProcess) -> dict[str, Any]:
    return {
        "protein": {"counts": _seeded_protein_counts(process)},
        "complex": {"counts": _seeded_complex_counts(process)},
        "tf_binding": _seeded_binding(process),
    }


def test_strict_zero_baseline_does_not_raise() -> None:
    """Sanity: fully-seeded zero state must NOT raise — isolates the failure
    modes below to the deliberate removals."""
    process = _build_process()
    state = _baseline_state(process)
    update = process.next_update(1.0, state)
    assert isinstance(update, dict)


def test_strict_zero_missing_protein_tf_raises() -> None:
    """A declared protein-store TF removed from protein.counts must KeyError;
    no silent zero-fill from defaults, no fallback to complex.counts."""
    process = _build_process()
    if not process._protein_tf_wids:
        pytest.skip("Fixture has no protein-store TFs; can't exercise this path.")
    target = process._protein_tf_wids[0]

    state = _baseline_state(process)
    del state["protein"]["counts"][target]

    with pytest.raises(KeyError, match=target):
        process.next_update(1.0, state)


def test_strict_zero_missing_complex_tf_raises() -> None:
    """A declared complex-store TF removed from complex.counts must KeyError;
    no silent zero-fill, no fallback to protein.counts."""
    process = _build_process()
    if not process._complex_tf_wids:
        pytest.skip("Fixture has no complex-store TFs; can't exercise this path.")
    target = process._complex_tf_wids[0]

    state = _baseline_state(process)
    del state["complex"]["counts"][target]

    with pytest.raises(KeyError, match=target):
        process.next_update(1.0, state)


def test_strict_zero_no_fallback_complex_tf_in_protein_store() -> None:
    """A complex-store TF that is ONLY present in protein.counts (wrong store)
    must still KeyError — no cross-store fallback."""
    process = _build_process()
    if not process._complex_tf_wids:
        pytest.skip("Fixture has no complex-store TFs; can't exercise this path.")
    target = process._complex_tf_wids[0]

    state = _baseline_state(process)
    del state["complex"]["counts"][target]
    state["protein"]["counts"][target] = 1000.0

    with pytest.raises(KeyError, match=target):
        process.next_update(1.0, state)


def test_strict_zero_no_fallback_protein_tf_in_complex_store() -> None:
    """Mirror of the previous test: a protein-store TF present only in
    complex.counts must still KeyError."""
    process = _build_process()
    if not process._protein_tf_wids:
        pytest.skip("Fixture has no protein-store TFs; can't exercise this path.")
    target = process._protein_tf_wids[0]

    state = _baseline_state(process)
    del state["protein"]["counts"][target]
    state["complex"]["counts"][target] = 1000.0

    with pytest.raises(KeyError, match=target):
        process.next_update(1.0, state)
