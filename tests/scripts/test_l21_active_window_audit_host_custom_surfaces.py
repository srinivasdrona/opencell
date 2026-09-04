from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import l21_active_window_audit as active_windows  # noqa: E402


def test_host_bacterium_adherent_overlay_sets_boolean_and_strength():
    state: dict[str, object] = {}

    active_windows._overlay_custom_observable(  # type: ignore[attr-defined]
        state=state,
        observable="isBacteriumAdherent",
        vector=np.asarray([1.0], dtype=np.float64),
        process_name="HostInteraction",
        wids=["isBacteriumAdherent_0"],
    )

    assert state == {"cell": {"host_attached": True, "host_adhesion_strength": 1.0}}


def test_host_bacterium_adherent_projection_reads_host_attached():
    projected = active_windows._project_custom_observable(  # type: ignore[attr-defined]
        state={"cell": {"host_attached": True}},
        observable="isBacteriumAdherent",
        process_name="HostInteraction",
        wids=["isBacteriumAdherent_0"],
    )

    assert np.array_equal(projected, np.asarray([1.0], dtype=np.float64))


def test_host_missing_signaling_surfaces_fail_closed_as_zero_vectors():
    for observable in (
        "isTLRActivated_1",
        "isTLRActivated_2",
        "isTLRActivated_3",
        "isNFkBActivated",
        "isInflammatoryResponseActivated",
    ):
        projected = active_windows._project_custom_observable(  # type: ignore[attr-defined]
            state={"cell": {"host_attached": True}},
            observable=observable,
            process_name="HostInteraction",
            wids=[observable],
        )
        assert np.array_equal(projected, np.asarray([0.0], dtype=np.float64))


def test_tr_bound_tfs_projection_sums_tf_binding_rows():
    tf_wids, tu_wids = active_windows._tr_surface_order()  # type: ignore[attr-defined]
    state = {
        "tf_binding": {
            tf_wids[0]: {tu_wids[0]: 1.0},
            tf_wids[1]: {tu_wids[1]: 1.0},
        }
    }

    projected = active_windows._project_custom_observable(  # type: ignore[attr-defined]
        state=state,
        observable="boundTFs",
        process_name="TranscriptionalRegulation",
        wids=tf_wids,
    )

    expected = np.zeros(len(tf_wids), dtype=np.float64)
    expected[0] = 1.0
    expected[1] = 1.0
    assert np.array_equal(projected, expected)


def test_tr_tf_bound_promoters_projection_flattens_oc_tf_binding_grid():
    tf_wids, tu_wids = active_windows._tr_surface_order()  # type: ignore[attr-defined]
    state = {
        "tf_binding": {
            tf_wids[0]: {tu_wids[0]: 1.0},
            tf_wids[1]: {tu_wids[1]: 1.0},
        }
    }

    projected = active_windows._project_custom_observable(  # type: ignore[attr-defined]
        state=state,
        observable="tfBoundPromoters",
        process_name="TranscriptionalRegulation",
        wids=[],
    )

    expected = np.zeros(len(tf_wids) * len(tu_wids), dtype=np.float64)
    expected[0] = 1.0
    expected[len(tu_wids) + 1] = 1.0
    assert np.array_equal(projected, expected)
