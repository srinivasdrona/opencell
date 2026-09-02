from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.l22_extraction import ppii_active_window as paw_contract  # noqa: E402
from tests.scripts._l22_fixtures import write_synthetic_trace  # noqa: E402


def test_build_portable_full50_manifest_rewrites_birth_paths_and_records_later_provenance(
    tmp_path: Path, monkeypatch
):
    covered_trace = write_synthetic_trace(
        tmp_path / "data" / "m1_sources" / "karr_native" / "per_process_traces_v2_s002" / "ProteinProcessingII_100ticks.mat",
        process_name=paw_contract.PROCESS_NAME,
        seed=2,
        n_ticks=100,
        channels=("substrates",),
    )
    covered_manifest = tmp_path / "covered28.json"
    covered_manifest.write_text(
        json.dumps(
            {
                "schema_version": "h12_trace_window_manifest_v1",
                "process": paw_contract.PROCESS_NAME,
                "window_length_ticks": paw_contract.WINDOW_TICKS,
                "entries": {
                    "2": {
                        "seed": 2,
                        "process": paw_contract.PROCESS_NAME,
                        "trace_path": "unused_in_test.mat",
                        "trace_sha256": paw_contract.sha256_file(covered_trace),
                        "trace_schema": "per_process_traces_v2_birth_100ticks",
                        "trace_tick_start": 1,
                        "trace_tick_end": 100,
                        "window_tick_start": 44,
                        "window_tick_end": 63,
                        "window_length_ticks": paw_contract.WINDOW_TICKS,
                        "first_regime_valid_transferase_tick": 44,
                        "window_selection": "birth_window",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(paw_contract, "REQUIRED_N_SEEDS", 3)
    monkeypatch.setattr(
        paw_contract,
        "canonical_birth_trace_path",
        lambda seed: tmp_path / "data" / "m1_sources" / "karr_native" / f"per_process_traces_v2_s{seed:03d}" / "ProteinProcessingII_100ticks.mat",
    )
    monkeypatch.setattr(
        paw_contract,
        "_driver_hash",
        lambda: "d" * 64,
    )
    monkeypatch.setattr(
        paw_contract,
        "_fixture_hash",
        lambda: "f" * 64,
    )
    monkeypatch.setattr(
        paw_contract,
        "_karr_source_hash",
        lambda: "k" * 64,
    )
    monkeypatch.setattr(
        paw_contract,
        "validate_later_active_window_seed",
        lambda seed, _path: paw_contract.PPIIActiveWindowSeed(
            seed=seed,
            path=tmp_path / "data" / "m1_sources" / "karr_native" / "ppii_active_window" / paw_contract.seed_subdir_token(seed) / "ProteinProcessingII_20ticks.mat",
            sha256=f"{seed:064x}"[-64:],
            tick_start=100 + seed,
            tick_end=119 + seed,
            tick_offset=99 + seed,
            trigger_tick=100 + seed,
            search_max_ticks=2000,
            detection_mechanism="synthetic_test",
            search_stop_reason=paw_contract.SEARCH_STOP_REASON_SUCCESS,
            provider={
                "kind": "statistics_toolbox",
                "matlab_release": "R2026a",
                "toolbox_version": "26.1",
                "provider_path_relative_to_matlabroot": "toolbox/stats/stats/mnrnd.m",
                "sha256_lf_normalized": "1" * 64,
            },
            rng_identity_json='{"kind":"statistics_toolbox"}',
        ),
    )

    out_path = tmp_path / "manifest.full50.json"
    payload = paw_contract.build_portable_full50_manifest(
        covered_manifest_path=covered_manifest,
        out_path=out_path,
    )

    assert payload["covered_seed_count"] == 3
    assert payload["entries"]["2"]["trace_origin_kind"] == paw_contract.TRACE_ORIGIN_ORACLE_POPULATION
    assert not Path(payload["entries"]["2"]["trace_path"]).is_absolute()
    assert payload["entries"]["0"]["trace_origin_kind"] == paw_contract.TRACE_ORIGIN_TRACKED_ACTIVE_WINDOW
    assert payload["entries"]["0"]["tracked_extraction_provenance"]["driver_sha256_lf_normalized"] == "d" * 64
    assert payload["entries"]["0"]["tracked_extraction_provenance"]["fixture_sha256"] == "f" * 64
