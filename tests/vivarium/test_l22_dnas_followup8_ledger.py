from __future__ import annotations

from pathlib import Path
import sys

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.l22_dnas_followup8_ledger import build_seed_tick_ledger
from scripts.l22_dnas_followup7_ledger import _resolve_trace_root


def _normalize_regions(value: object) -> list[list[int]]:
    return [list(region) for region in value]  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def seed0_tick5_ledger() -> dict[str, object]:
    trace_root = _resolve_trace_root(
        Path("/mnt/e/opencell-worktrees/l22-dnas-closure-20260805/data/m1_sources/karr_native")
    )
    return build_seed_tick_ledger(
        trace_root=trace_root,
        seed=0,
        tick=5,
    )


def test_followup8_visible_state_candidate_space_matches_source_and_oc(
    seed0_tick5_ledger: dict[str, object],
) -> None:
    oc_path = seed0_tick5_ledger["oc_path"]
    matlab_path = seed0_tick5_ledger["matlab_source_path"]
    topoiv = seed0_tick5_ledger["topoiv"]
    summary = seed0_tick5_ledger["source_invariant_summary"]

    assert _normalize_regions(oc_path["accessible_regions"]) == [[579801, 0, 275], [0, 2, 275]]
    assert _normalize_regions(matlab_path["accessible_regions"]) == [[579801, 0, 275], [0, 2, 275]]
    assert int(oc_path["candidate_sites"]) == 484
    assert int(matlab_path["candidate_sites"]) == 484
    assert int(oc_path["stable_binding_count_if_called"]) == 12
    assert int(matlab_path["stable_binding_count_if_called"]) == 12
    assert float(topoiv["free_before"]) == pytest.approx(12.0)
    assert int(summary["source_visible_state_implied_binding_count"]) == 12
    assert int(summary["karr_trace_after_bound_count"]) == 0


def test_followup8_replay_proves_visible_state_source_path_cannot_explain_karr_zero_binding(
    seed0_tick5_ledger: dict[str, object],
) -> None:
    current_replay = seed0_tick5_ledger["topoiv_turn_replay_current_oc_rng"]
    matlab_replay = seed0_tick5_ledger["topoiv_turn_replay_matlab_rng"]
    first_step = seed0_tick5_ledger["first_divergent_step"]
    trace_fields = seed0_tick5_ledger["trace_visible_chromosome_fields"]

    assert _normalize_regions(current_replay["positive_regions_at_topoiv_call"]) == [
        [579765, 0, 311],
        [0, 2, 311],
    ]
    assert _normalize_regions(current_replay["accessible_regions_at_topoiv_call"]) == [
        [579801, 0, 275],
        [0, 2, 275],
    ]
    assert int(current_replay["candidate_sites_at_topoiv_call"]) == 484
    assert int(current_replay["proposal_trace"]["count"]) == 12
    assert bool(current_replay["proposal_validation"]["all_within_accessible_candidate_space"])
    assert not bool(current_replay["proposal_validation"]["any_source_style_overlap"])
    assert (
        current_replay["proposal_validation"]["source_bindProteinToChromosomeStochastically_can_silently_drop_sites"]
        is False
    )

    assert int(matlab_replay["candidate_sites_at_topoiv_call"]) == 484
    assert int(matlab_replay["proposal_trace"]["count"]) == 12
    assert (
        int(matlab_replay["source_binding_outcome"]["if_bindProteinToChromosomeStochastically_is_called_source_n_bound"])
        == 12
    )

    assert set(trace_fields) == {
        "abasicSites",
        "complexBoundSites",
        "damagedBases",
        "damagedSugarPhosphates",
        "gapSites",
        "hollidayJunctions",
        "intrastrandCrossLinks",
        "linkingNumbers",
        "monomerBoundSites",
        "polymerizedRegions",
        "strandBreaks",
    }
    assert first_step["kind"] == "missing_trace_state"
    assert "doubleStrandedRegions" in first_step["missing_fields_from_trace"]
    assert "damagedSites" in first_step["missing_fields_from_trace"]
    assert "validated_doubleStrandedRegions" in first_step["missing_fields_from_trace"]
