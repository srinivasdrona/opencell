from __future__ import annotations

from pathlib import Path


def test_ppii_active_window_driver_binds_real_scan_and_metadata():
    source = Path("scripts/matlab/extract_ppii_active_window_seeds.m").read_text(encoding="utf-8")

    assert "this_file = [mfilename('fullpath') '.m'];" in source
    assert "karr_bootstrap();" in source
    assert "extract_per_process_traces_v2({process_name}, tmp_subdir, n_ticks, uint32(s), tick_offset, 'fixed');" in source
    assert "regime_valid && transferase_demand > 0" in source
    assert "metadata.active_window_rule = active_window_rule;" in source
    assert "metadata.active_window_trigger_tick = int32(trigger.trigger_tick);" in source
    assert "metadata.active_window_driver_sha256 = sha256_lf_normalized(driver_path);" in source
    assert "statistics_rng_provider_identity_json" in source
    assert "ensure_wholecell_runtime_paths(repo_root);" in source
    assert "normalize_name_token(proc_obj.wholeCellModelID)" in source
    assert "if strncmp(wid, 'Process_', numel('Process_'))" in source


def test_ppii_active_window_driver_validates_provider_and_tick_contract_fields():
    source = Path("scripts/matlab/extract_ppii_active_window_seeds.m").read_text(encoding="utf-8")

    assert "'mnrnd_provider_kind'" in source
    assert "'mnrnd_provider_matlab_release'" in source
    assert "'mnrnd_provider_toolbox_version'" in source
    assert "'mnrnd_provider_path_relative_to_matlabroot'" in source
    assert "'mnrnd_provider_sha256'" in source
    assert "'statistics_rng_provider_identity_json'" in source
    assert "metadata.tick_start" in source
    assert "metadata.tick_offset" in source
    assert "metadata.active_window_search_max_ticks" in source
