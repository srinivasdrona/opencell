from __future__ import annotations

from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.l22_dnas_followup7_ledger import classify_branch_mismatch


def _oc_ledger(
    *,
    delta_value_sum: float = 0.0,
    delta_nnz: float = 0.0,
    topoiv_n_bound: int = 0,
    release_gyrase: float = 0.0,
    release_topoiv: float = 0.0,
    activity_total: int = 0,
) -> dict[str, object]:
    return {
        "delta_projection": {
            "linkingNumbers.delta_value_sum": float(delta_value_sum),
            "linkingNumbers.delta_nnz": float(delta_nnz),
        },
        "stable_binding_by_enzyme": {
            "MG_203_204_TETRAMER": {
                "n_bound": int(topoiv_n_bound),
            }
        },
        "release_counts_by_enzyme": {
            "DNA_GYRASE": float(release_gyrase),
            "MG_203_204_TETRAMER": float(release_topoiv),
        },
        "activity_events_total_by_enzyme": {
            "DNA_GYRASE": int(activity_total),
            "MG_203_204_TETRAMER": 0,
            "MG_122_MONOMER": 0,
        },
    }


def _karr_ledger(
    *,
    delta_value_sum: float = 0.0,
    delta_nnz: float = 0.0,
    topoiv_before: int = 0,
    topoiv_after: int = 0,
    atp_delta: float = 0.0,
) -> dict[str, object]:
    return {
        "delta_projection": {
            "linkingNumbers.delta_value_sum": float(delta_value_sum),
            "linkingNumbers.delta_nnz": float(delta_nnz),
        },
        "bound_site_counts_before": {
            "MG_203_204_TETRAMER": int(topoiv_before),
        },
        "bound_site_counts_after": {
            "MG_203_204_TETRAMER": int(topoiv_after),
        },
        "substrate_delta": {
            "ATP": float(atp_delta),
        },
    }


def test_classify_branch_mismatch_projection_structure_only() -> None:
    classification = classify_branch_mismatch(
        oc_ledger=_oc_ledger(delta_value_sum=-8.0, delta_nnz=-4.0),
        karr_ledger=_karr_ledger(delta_value_sum=-8.0, delta_nnz=0.0),
    )

    assert classification == "projection_structure_only"


def test_classify_branch_mismatch_flags_topoiv_candidate_count_or_occupancy() -> None:
    classification = classify_branch_mismatch(
        oc_ledger=_oc_ledger(delta_value_sum=-126.0, delta_nnz=-4.0, topoiv_n_bound=12),
        karr_ledger=_karr_ledger(delta_value_sum=-8.0, delta_nnz=0.0, topoiv_before=0, topoiv_after=0),
    )

    assert classification == "candidate_count_or_binding_occupancy_topoiv"


def test_classify_branch_mismatch_flags_release_or_ownership() -> None:
    classification = classify_branch_mismatch(
        oc_ledger=_oc_ledger(release_gyrase=1.0),
        karr_ledger=_karr_ledger(),
    )

    assert classification == "enzyme_release_or_ownership"


def test_classify_branch_mismatch_flags_source_probabilities_or_rng() -> None:
    classification = classify_branch_mismatch(
        oc_ledger=_oc_ledger(activity_total=3),
        karr_ledger=_karr_ledger(atp_delta=-6.0),
    )

    assert classification == "source_probabilities_or_rng"


def test_classify_branch_mismatch_falls_back_to_unclassified_sparse_branch() -> None:
    classification = classify_branch_mismatch(
        oc_ledger=_oc_ledger(delta_value_sum=-3.0, delta_nnz=-1.0),
        karr_ledger=_karr_ledger(delta_value_sum=-1.0, delta_nnz=0.0),
    )

    assert classification == "unclassified_sparse_branch"
