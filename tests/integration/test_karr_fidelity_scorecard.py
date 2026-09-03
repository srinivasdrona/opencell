from __future__ import annotations

import sys
from pathlib import Path

# Ensure pytest imports from this worktree even if another editable install exists.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

from scripts.karr_fidelity_scorecard import DIAGNOSTIC_MIRROR_PROCESSES, run_scorecard


def test_karr_fidelity_scorecard_known_processes_not_fail() -> None:
    rows = run_scorecard(write_outputs=False)
    by_name = {row.process_name: row for row in rows}

    for process_name in (
        "Cytokinesis",
        "FtsZPolymerization",
        "ProteinTranslocation",
        "Metabolism",
    ):
        assert process_name in by_name, f"missing scorecard row for {process_name}"
        status = by_name[process_name].status
        assert status in {"PASS", "PARTIAL"}, (
            f"{process_name} expected PASS or PARTIAL, got {status}: {by_name[process_name].reason}"
        )


def test_chromosome_condensation_is_honestly_skipped_as_mirror_fixture() -> None:
    """ChromosomeCondensation's `per_process_replay` fixture is a pure mirror
    (states_before == states_after across all 100 ticks and all 3 compared
    properties) -- a placeholder captured before this process had a real
    per-tick Karr extraction, not a genuine zero-activity tick (the real,
    non-mirror 100-tick trace already exists and is used by the L2.1/
    strict-rubric gates: 66/100 ticks active, GENUINE verdict). Comparing
    OC's real output against that recorded no-op previously produced a
    spurious FAIL (`enzymes` max_abs=3). This test pins the CORRECT,
    evidence-backed classification (SKIP as a diagnostic mirror, exactly
    like Transcription/Translation/RNADecay/Replication/
    ReplicationInitiation) so a future regeneration of the mirror-process
    allowlist cannot silently drop ChromosomeCondensation back into a false
    FAIL, and so a future real re-extraction of this fixture (which would
    stop being a mirror) is caught here rather than silently masked."""
    assert "ChromosomeCondensation" in DIAGNOSTIC_MIRROR_PROCESSES

    rows = run_scorecard(write_outputs=False)
    by_name = {row.process_name: row for row in rows}
    row = by_name["ChromosomeCondensation"]
    assert row.status == "SKIP"
    assert "mirror" in row.reason.lower()


def test_chromosome_condensation_fixture_is_still_a_pure_mirror() -> None:
    """Guards the premise behind the SKIP classification above: if a future
    MATLAB re-extract replaces this fixture with real per-tick data, this
    test fails loudly (rather than the mirror classification silently
    masking newly-available real fidelity evidence) and the process should
    be removed from `DIAGNOSTIC_MIRROR_PROCESSES` and re-evaluated for a
    real PASS/PARTIAL/FAIL verdict instead."""
    from opencell.validation.replay import load_per_process_fixture
    from scripts.karr_fidelity_scorecard import REPLAY_FIXTURE_ROOT

    fixture = load_per_process_fixture("ChromosomeCondensation", root=REPLAY_FIXTURE_ROOT)
    for prop in ("boundEnzymes", "enzymes", "substrates"):
        before = fixture.inputs[prop]
        after = fixture.outputs[prop]
        assert (before == after).all(), (
            f"ChromosomeCondensation's per_process_replay fixture property {prop!r} is no "
            "longer a pure mirror -- remove it from DIAGNOSTIC_MIRROR_PROCESSES in "
            "scripts/karr_fidelity_scorecard.py and re-evaluate its real scorecard verdict."
        )
