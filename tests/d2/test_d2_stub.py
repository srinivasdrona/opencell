"""Smoke test for D.2 stub snapshot seeding."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from scipy.io import loadmat

from opencell.vivarium.karr_composite import build_karr_m1_m2_m3_engine

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_DIR = _REPO_ROOT / "data" / "karr_fixtures" / "per_process"
_PROTEIN_COMPLEX_FLAT = _FIXTURE_DIR / "ProteinComplex_flat.mat"
_MACROMOLECULAR_COMPLEXATION_FLAT = _FIXTURE_DIR / "MacromolecularComplexation_flat.mat"
_RIBOSOME_ASSEMBLY_FLAT = _FIXTURE_DIR / "RibosomeAssembly_flat.mat"


def _load_fixture(path: Path) -> object:  # noqa: ANN401 - matlab struct dynamic
    return loadmat(str(path), squeeze_me=True, struct_as_record=False)["data"].fixture


def _require_fixture_inputs() -> None:
    required = [
        _PROTEIN_COMPLEX_FLAT,
        _MACROMOLECULAR_COMPLEXATION_FLAT,
        _RIBOSOME_ASSEMBLY_FLAT,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        pytest.skip("D.2 fixture inputs missing: " + ", ".join(missing))


def _derive_expected_snapshot() -> tuple[tuple[str, ...], dict[str, float]]:
    _require_fixture_inputs()

    mc = _load_fixture(_MACROMOLECULAR_COMPLEXATION_FLAT)
    ra = _load_fixture(_RIBOSOME_ASSEMBLY_FLAT)
    pc = _load_fixture(_PROTEIN_COMPLEX_FLAT)

    d2_wids = set(np.asarray(mc.complexWholeCellModelIDs, dtype=object).ravel().astype(str))
    d2_wids.update(
        np.asarray(ra.complexWholeCellModelIDs, dtype=object).ravel().astype(str)
    )
    d2_wids_sorted = tuple(sorted(d2_wids))

    form_wids = np.asarray(pc.wholeCellModelIDs, dtype=object).ravel().astype(str)
    mature_rows = np.asarray(pc.matureIndexs, dtype=np.int64).ravel() - 1
    compartments = np.asarray(pc.compartments, dtype=np.int64).ravel() - 1
    counts = np.asarray(pc.counts, dtype=np.float64)

    mature_count_by_wid: dict[str, float] = {}
    for row in mature_rows:
        if row < 0 or row >= form_wids.size:
            continue
        col = int(compartments[row])
        if col < 0 or col >= counts.shape[1]:
            continue
        mature_count_by_wid[form_wids[row]] = float(counts[row, col])

    expected = {
        wid: float(mature_count_by_wid.get(wid, 0.0))
        for wid in d2_wids_sorted
    }
    return d2_wids_sorted, expected


def test_d2_stub_seeds_defaults_and_stays_static() -> None:
    d2_wids, expected = _derive_expected_snapshot()
    assert len(d2_wids) == 149

    engine = build_karr_m1_m2_m3_engine(time_step_s=1.0, emit_step_s=1.0)
    state_t0 = engine.state.get_value()
    complex_counts_t0 = state_t0["complex"]["counts"]

    for wid in d2_wids:
        assert float(complex_counts_t0[wid]) == pytest.approx(expected[wid])

    engine.update(1.0)
    state_t1 = engine.state.get_value()
    complex_counts_t1 = state_t1["complex"]["counts"]

    for wid in d2_wids:
        assert float(complex_counts_t1[wid]) == pytest.approx(expected[wid])

