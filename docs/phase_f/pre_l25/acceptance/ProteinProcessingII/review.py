from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path.cwd().resolve()
OWN = ROOT / "artifacts/m1_cohort/m1_pp2/independent_acceptance"
RAW = ROOT / "artifacts/l2_2_gates/ProteinProcessingII/latest"
sys.path.insert(0, str(ROOT))
import opencell

assert sys.executable == "/mnt/e/opencell/.venv-wsl/bin/python", sys.executable
assert Path(opencell.__file__).resolve().is_relative_to(ROOT), opencell.__file__


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, payload):
    path = OWN / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    print(json.dumps({"report": str(path.relative_to(ROOT)), "sha256": sha(path)}), flush=True)


def inspect():
    details = {}
    for name in ("result.json", "input_manifest.json", "null_calibration.json", "allocator_inputs.json"):
        payload = load(RAW / name)
        detail = {}
        for key, value in payload.items():
            if isinstance(value, list):
                detail[key] = {"length": len(value), "first": value[:1]}
            elif isinstance(value, dict):
                detail[key] = {
                    k: ({"length": len(v), "first": v[:1]} if isinstance(v, list) else v)
                    for k, v in value.items()
                }
            else:
                detail[key] = value
        details[name] = detail
    for name in ("preflight.json", "accepted-input-copy.json", "preflight_reuse_validation.json"):
        payload = load(ROOT / "artifacts/m1_cohort/m1_pp2" / name)
        if isinstance(payload, list):
            details[name] = {"length": len(payload), "first": payload[:1]}
            continue
        details[name] = {
            k: ({"length": len(v), "first": v[:1]} if isinstance(v, list) else
                {"keys": list(v), "first": dict(list(v.items())[:1])} if isinstance(v, dict) else v)
            for k, v in payload.items()
        }
    save("independent_structure.json", details)
    print(json.dumps(details, indent=2))


def controls():
    import pytest
    selectors = [
        "tests/vivarium/test_karr_protein_processing_ii_l2_replay.py",
        "tests/vivarium/test_karr_protein_processing_ii_design_a_projection.py",
    ]
    fidelity = "tests/vivarium/test_karr_protein_processing_ii_fidelity.py::"
    selectors += [fidelity + name for name in (
        "test_requests_match_matlab_ceil_min_algebra",
        "test_requests_are_independent_of_shared_substrate_availability",
        "test_requests_use_compartment_processed_i_not_legacy_shadows",
        "test_evolution_uses_source_compartment_not_conflicting_legacy_pool",
        "test_evolution_uses_live_mature_enzymes_not_seeded_compatibility_branch",
        "test_requests_use_live_mature_enzymes_when_compatibility_disagrees",
        "test_zero_grant_blocks_real_precursor_even_with_huge_shared_pool",
        "test_engine_construction_does_not_evolve_biology",
        "test_engine_new_precursor_requests_grants_and_consumes_in_same_tick",
        "test_measured_transition_canary_rejects_stale_or_duplicated_evolution",
        "test_nonmigrated_reader_selects_pp1_processed_i_queue_not_mature_pool",
        "test_nonmigrated_processed_i_moves_once_to_folding_queue_without_mature_drain",
        "test_nonmigrated_mature_only_pool_never_creates_processing",
        "test_nonmigrated_real_pp1_pp2_folding_handoff_uses_distinct_forms",
        "test_engine_nonmigrated_form_queues_visible_and_consumed_once",
    )]
    guard = "tests/vivarium/test_protein_state_no_dual_writer.py::"
    selectors += [guard + name for name in (
        "test_canary_c5_rejects_undeclared_migrated_wid_write",
        "test_c2b_no_fake_empty_counts_declaration_in_pp2",
        "test_c2b_migrated_wids_never_emitted_to_legacy_branches",
        "test_pp2_shadow_enzymes_do_not_activate_migrated_peptides",
    )]
    selectors += ["tests/vivarium/test_karr_protein_processing_ii.py::test_mass_conservation"]
    args = selectors + [
        "-q", "-s", "-ra", "-p", "no:cacheprovider",
        "--basetemp=artifacts/m1_cohort/m1_pp2/independent_acceptance/scratch/pytest",
        "--junitxml=artifacts/m1_cohort/m1_pp2/independent_acceptance/controls.xml",
    ]
    assert (OWN / "scratch").is_dir(), "Create owned parent before pytest basetemp"
    save("controls_argv.json", {"executable": sys.executable, "argv": args, "pid": os.getpid()})
    rc = pytest.main(args)
    import xml.etree.ElementTree as ET
    tree = ET.parse(OWN / "controls.xml")
    cases = tree.findall(".//testcase")
    outcomes = {"cases": len(cases), "skipped": len(tree.findall(".//skipped")),
                "failures": len(tree.findall(".//failure")), "errors": len(tree.findall(".//error"))}
    save("controls_outcomes.json", {"exit_code": int(rc), **outcomes,
                                  "selectors": selectors, "tests": [c.attrib for c in cases]})
    assert rc == 0 and not any(outcomes[k] for k in ("skipped", "failures", "errors")), outcomes


def verify():
    import dataclasses
    from collections import Counter
    import h5py
    import numpy as np
    from scipy.stats import wasserstein_distance
    from scripts.l22_evidence import catalog, generator, h12, schema, verdict
    sys.path.insert(0, str(ROOT / "tests/vivarium"))
    import _l2_2_design_a_runner_helpers as helpers
    import l2_2_design_a_runner as runner
    from opencell.vivarium.karr_protein_processing_ii import KarrProteinProcessingIIProcess

    name = "ProteinProcessingII"
    entry = catalog.in_scope_processes()[name]
    result = load(RAW / "result.json")
    manifest = load(RAW / "input_manifest.json")
    sentinel = load(RAW / "sweep_provenance.json")
    preflight = load(ROOT / "artifacts/m1_cohort/m1_pp2/preflight.json")
    reuse = load(ROOT / "artifacts/m1_cohort/m1_pp2/preflight_reuse_validation.json")
    assert entry.n_seeds == 50 and entry.m_ticks == 20 and entry.primary_channel == "monomers"
    assert runner.DEFAULT_BOOTSTRAP_B == result["bootstrap_B"] == 1000
    assert result["seeds"] == manifest["resolved_seeds"] == list(range(50))
    assert result["ticks"] == manifest["m_ticks"] == 20
    assert result["n_observations_per_channel"] == 1000
    current_hashes = generator._current_source_hashes(entry)
    assert current_hashes == sentinel["source_hashes"] == preflight["source_hashes"]
    assert len(current_hashes) == 10
    assert sentinel["completion_status"] == "COMPLETE" and sentinel["inputs_verified"] is True
    assert sentinel["git_sha"] == "65df71c26553f42dd95759b948de42647987bf68"
    for fname, digest in sentinel["sidecar_hashes"].items():
        assert sha(RAW / fname) == digest, fname

    records = manifest["inputs"]
    assert len(records) == 61
    verified_inputs = []
    for rec in records:
        path = Path(rec["path"])
        if not path.is_absolute():
            path = ROOT / path
        assert path.resolve().is_relative_to(ROOT)
        assert sha(path) == rec["sha256"], rec
        verified_inputs.append({**rec, "size_bytes": path.stat().st_size,
                                "actual_sha256": sha(path)})
    runtime = helpers.capture_runtime_inputs(name)
    actual_runtime = {str(Path(r["path"]).resolve().relative_to(ROOT)): r["sha256"] for r in runtime}
    recorded_runtime = {r["path"]: r["sha256"] for r in records if "seed" not in r}
    assert len(actual_runtime) == 11 and actual_runtime == recorded_runtime
    proc = KarrProteinProcessingIIProcess({"rng_seed": 0})
    assert len(proc.unprocessed_monomer_wids) == len(proc.processed_monomer_wids) == 482
    assert len(proc.signal_sequence_monomer_wids) == 482
    assert Path(proc.parameters["fixture_path"]).name == "ProteinProcessingII_flat.mat"
    assert sha(ROOT / "artifacts/m1_cohort/m1_pp2/preflight.json") == reuse["preflight_sha256"]
    pre_inputs = preflight["oracle_load_inputs"] + preflight["runtime_inputs"]
    assert {str((ROOT / r["path"]).resolve()): r["sha256"] for r in records} == {
        str(Path(r["path"]).resolve()): r["sha256"] for r in pre_inputs
    }
    assert all(preflight["isolation"][k] for k in ("repeat_equal", "interleave_equal", "distinct_same_seed_owners"))

    copied = load(ROOT / "artifacts/m1_cohort/m1_pp2/accepted-input-copy.json")
    copy_hashes = {r["RelativePath"].replace("\\", "/"): r["Sha256"] for r in copied}
    population_path = ROOT / "docs/phase_f/l2_2_design_a/oracle_population_manifest.json"
    population = load(population_path)["processes"][name]["files"]
    population_hashes = {r["relative_path"]: r["sha256"] for r in population}
    seeds = sorted((r for r in records if "seed" in r), key=lambda r: r["seed"])
    assert [r["seed"] for r in seeds] == list(range(50))
    assert len(set(r["path"] for r in seeds)) == 50
    assert not (ROOT / "data/m1_sources/karr_native/per_process_traces_v2_s000/ProteinProcessingII_100ticks.mat").exists()
    families = {"substrates", "enzymes", "boundEnzymes", "processedMonomers",
                "unprocessedMonomers", "signalSequenceMonomers"}
    widths = {"substrates": 5, "enzymes": 2, "boundEnzymes": 2,
              "processedMonomers": 482, "unprocessedMonomers": 482, "signalSequenceMonomers": 482}
    seed_inventory = []
    all_before = []
    all_after = []
    activity = Counter()
    fixture = h12.load_fixture(name)
    h12_results = []
    for rec in seeds:
        path = ROOT / rec["path"]
        relative = path.relative_to(ROOT / "data/m1_sources/karr_native").as_posix()
        assert rec["sha256"] == copy_hashes[relative] == population_hashes[relative]
        before, after = {}, {}
        with h5py.File(path, "r") as trace:
            seed = int(np.asarray(trace["metadata/rng_seed"][()]).ravel()[0])
            ticks = int(np.asarray(trace["metadata/n_ticks"][()]).ravel()[0])
            assert seed == rec["seed"] and ticks == 100
            for phase, dest in (("states_before", before), ("states_after", after)):
                assert set(trace[phase]) == families
                for family in sorted(families):
                    ds = trace[f"{phase}/{family}"]
                    assert ds.shape == (1, 100), (phase, family, ds.shape)
                    rows = [np.asarray(trace[ref][()]).ravel() for ref in ds[0, :20]]
                    dest[family] = np.stack(rows)
                    assert dest[family].shape == (20, widths[family])
                    assert np.array_equal(dest[family], np.rint(dest[family]))
        active = {f: int(np.count_nonzero(np.any(after[f] != before[f], axis=1))) for f in families}
        activity.update(active)
        seed_inventory.append({**rec, "embedded_seed": seed, "n_ticks": ticks,
                               "families": sorted(families), "widths": widths, "active_ticks_M20": active})
        all_before.append(before)
        all_after.append(after)
        predictions = h12.predict_protein_processing_ii(seed, before, fixture)
        measured = h12.compare_predictions(name, predictions, after, before)
        measured["branches_confirmed"] = sorted(measured["branches_confirmed"])
        measured["branches_observed"] = sorted(measured["branches_observed"])
        h12_results.append({"seed": seed, **measured})
    assert activity["signalSequenceMonomers"] > 0
    assert dict(activity) == preflight["activity_M20"]
    alloc = load(RAW / "allocator_inputs.json")["records"]
    assert len(alloc) == 1000
    assert Counter((r["seed"], r["tick"]) for r in alloc) == Counter(
        (s, t) for s in range(50) for t in range(20))
    for rec in alloc:
        b = all_before[rec["seed"]]
        t = rec["tick"]
        assert rec["process"] == name and rec["primary_channel"] == "monomers"
        assert rec["primary_sum_before"] == rec["monomers_sum_before"] == float(b["unprocessedMonomers"][t].sum())
        assert rec["substrates_sum_before"] == float(b["substrates"][t].sum())
        assert rec["substrates_nonzero_before"] == int(np.count_nonzero(b["substrates"][t]))
        assert rec["enzymes_sum_before"] == float(b["enzymes"][t].sum())

    calibration = load(RAW / "null_calibration.json")["channels"]
    thresholds = load(RAW / "thresholds.json")["channels"]
    numbers = {}
    for channel, family in (("monomers", "unprocessedMonomers"), ("substrates", "substrates")):
        karr = np.stack([r[family] for r in all_after])
        pairwise = np.empty((50, 50, 20))
        for i in range(50):
            for j in range(50):
                for t in range(20):
                    pairwise[i, j, t] = wasserstein_distance(karr[i, t], karr[j, t])
        rng = np.random.default_rng(helpers.L2_2_VALIDATION_SEED)
        bootstrap = []
        for _ in range(result["bootstrap_B"]):
            lhs = rng.integers(0, 50, size=50)
            rhs = rng.integers(0, 50, size=50)
            bootstrap.append(float(np.mean(pairwise[lhs, rhs, :])))
        values = np.asarray(bootstrap)
        q95 = float(np.percentile(values, 95))
        stats = {"mean": float(np.mean(values)), "stddev": float(np.std(values)),
                 "min": float(np.min(values)), "max": float(np.max(values))}
        threshold = max(helpers.ABSOLUTE_FLOOR, helpers.TRIVIAL_RNG_K_ENG * q95)
        c = result["channels"][channel]
        assert calibration[channel]["bootstrap_B"] == 1000
        assert calibration[channel]["n_karr_seeds"] == 50 and calibration[channel]["n_ticks"] == 20
        np.testing.assert_allclose(q95, c["q95_null"], rtol=1e-13, atol=1e-13)
        np.testing.assert_allclose(q95, calibration[channel]["q95_null"], rtol=1e-13, atol=1e-13)
        np.testing.assert_allclose(threshold, c["threshold"], rtol=1e-13, atol=1e-13)
        np.testing.assert_allclose(threshold, thresholds[channel]["threshold"], rtol=1e-13, atol=1e-13)
        assert thresholds[channel]["k_eng"] == 2 and thresholds[channel]["absolute_floor"] == 1
        for stat, value in stats.items():
            np.testing.assert_allclose(value, calibration[channel]["bootstrap_values_summary"][stat],
                                       rtol=1e-13, atol=1e-13)
        assert np.count_nonzero(karr) == c["n_nonzero_karr"] == c["n_nonzero_oc"]
        assert c["n_nonzero_oc"] >= schema.MIN_NONZERO_EVENTS
        assert c["is_primary"] == (channel == "monomers")
        assert c["w1_oc_vs_karr"] == c["per_sample_w1_summary"]["mean"] == 0
        assert c["per_sample_w1_summary"]["min"] == c["per_sample_w1_summary"]["max"] == 0
        direct_verdict = "SEED_NOISE" if c["w1_oc_vs_karr"] <= q95 else (
            "PASS" if c["w1_oc_vs_karr"] <= threshold else "FAIL")
        assert direct_verdict == c["verdict"] == "SEED_NOISE"
        ci = np.percentile(values, [2.5, 97.5]).tolist()
        np.testing.assert_allclose(ci, c["w1_oc_vs_karr_ci95"], rtol=1e-13, atol=1e-13)
        numbers[channel] = {"karr_shape": list(karr.shape), "q95_recomputed": q95,
                            "threshold_recomputed": threshold, "bootstrap_summary_recomputed": stats,
                            "saved_w1": c["w1_oc_vs_karr"], "direct_verdict": direct_verdict,
                            "ci95_under_saved_zero_distance_condition": ci,
                            "n_nonzero_karr_recomputed": int(np.count_nonzero(karr))}
        save(f"{channel}_calibration_recomputed.json", {"values": bootstrap, **numbers[channel]})

    old_ref = generator._with_h12_evidence_ref(name, result)
    assert verdict.h12_support_reason(old_ref, name) is None
    mechanical = verdict.rederive_process(name, entry, old_ref)
    assert mechanical.mechanical_verdict == "PASS" and not mechanical.reasons
    old_h12 = load(ROOT / old_ref["h12_evidence_ref"])
    h12_counts = {k: sum(r[k] for r in h12_results) for k in (
        "total_sample_count", "nontrivial_sample_count", "exact_match_count",
        "trivial_checked_count", "trivial_mismatch_count")}
    branches = set().union(*(r["branches_confirmed"] for r in h12_results))
    rate = h12_counts["exact_match_count"] / h12_counts["nontrivial_sample_count"]
    current_h12_verdict, current_h12_reason = h12.decide_verdict(
        h12_counts["nontrivial_sample_count"], h12_counts["exact_match_count"], rate,
        h12_counts["trivial_mismatch_count"], branches, h12.REQUIRED_BRANCHES[name])
    save("current_h12_applicability.json", {
        "purpose": "Current-byte predictor recomputation, not new biological/SUT execution or replacement of tracked H12",
        "existing_ref": old_ref["h12_evidence_ref"], "existing_sha256": sha(ROOT / old_ref["h12_evidence_ref"]),
        "existing_support_validator_reason": None,
        "old_vs_current_seed_hash_differences": [r["seed"] for r in seeds
            if r["sha256"] != old_h12["oracle_seed_file_sha256"][str(r["seed"])]],
        "current_verdict": current_h12_verdict, "current_reason": current_h12_reason,
        "current_counts": h12_counts, "exact_match_rate": rate,
        "branches_confirmed": sorted(branches), "per_seed": h12_results})
    # The tracked support explicitly owns active windows, not birth ticks 0..19.
    # Requiring birth-window transferase activity would invent a new gate.
    from scripts.l22_evidence import ppii_active_windows
    support_manifest = ROOT / old_h12["active_window_authority"]["manifest_ref"]["path"]
    linked = ppii_active_windows.build_active_window_validation_artifact(
        support_manifest, require_full_catalog=True)
    assert ppii_active_windows.validate_active_window_artifact(linked) is None
    regenerated_support = ppii_active_windows.build_shared_h12_artifact(linked)
    for key in (
        "oracle_seed_file_sha256", "oracle_manifest_cross_check", "raw_prediction_hash",
        "nontrivial_sample_count", "exact_match_count", "exact_match_rate",
        "trivial_checked_count", "trivial_mismatch_count", "required_branches",
        "branches_confirmed", "verdict", "active_window_authority",
    ):
        assert regenerated_support[key] == old_h12[key], key
    save("linked_h12_active_window_recomputation.json", {
        "purpose": "Existing registered H12 domain independently rehashed and numerically regenerated; no SUT execution and no authority replacement",
        "linked_artifact": linked, "regenerated_support": regenerated_support,
        "original_support_sha256": sha(ROOT / old_ref["h12_evidence_ref"]),
        "birth_window_is_not_active_window_domain": True,
        "birth_window_outcome": current_h12_verdict,
        "birth_window_uncovered_required_branch": "transferase_fires",
        "birth_window_regime_invalid_count": 1000 - h12_counts["nontrivial_sample_count"] - h12_counts["trivial_checked_count"],
        "registered_active_window_payload_exactly_reproduced": True})
    assert current_h12_verdict in {"H12_OBSERVED_REGIME", "H12_CONFIRMED"}
    assert h12_counts["exact_match_count"] == h12_counts["nontrivial_sample_count"] > 0
    assert h12_counts["trivial_mismatch_count"] == 0

    job = load(ROOT / "artifacts/m1_cohort/m1_pp2/sweep_report.json")["jobs"][0]
    exe = load(ROOT / "artifacts/m1_cohort/m1_pp2/sweep_execution.json")
    assert job["status"] == "RAN_EXIT_0" and job["exit_code"] == exe["exit_code"] == 0
    assert datetime.fromisoformat(job["started_at"]) < datetime.fromisoformat(result["timestamp"])
    assert datetime.fromisoformat(result["timestamp"]) < datetime.fromisoformat(job["finished_at"])
    assert datetime.fromisoformat(job["finished_at"]) < datetime.fromisoformat(sentinel["written_at"])
    run_log = (ROOT / job["log_path"]).read_text()
    assert str(ROOT / "tests/vivarium/l2_2_design_a_runner.py") in run_log
    assert "'--seeds', '50', '--ticks', '20'" in run_log and "ProteinProcessingII PASS" in run_log
    save("independent_measurements.json", {
        "contract": dataclasses.asdict(entry), "registered_B": runner.DEFAULT_BOOTSTRAP_B,
        "primary_width": 482, "source_hashes": current_hashes, "verified_inputs": verified_inputs,
        "runtime_binding": actual_runtime, "parameter_constructor": dict(proc.parameters),
        "seed_inventory": seed_inventory, "activity_M20": dict(activity),
        "allocator_records": len(alloc), "allocator_sha256": sha(RAW / "allocator_inputs.json"),
        "mechanical_evaluator": dataclasses.asdict(mechanical), "direct_numbers": numbers,
        "sidecar_hashes": {p.name: sha(p) for p in RAW.iterdir() if p.is_file()},
        "sweep_job": job, "sweep_execution": exe,
        "preflight_reused_not_rerun": True,
        "saved_numeric_limitation": "No full OC tensor saved. W1 is re-scored from saved numeric summaries; null calibration rederived from all current oracle values. CI rederived conditional on saved zero per-sample distances. No full biological campaign rerun."})


def candidate():
    from contextlib import redirect_stdout, redirect_stderr
    from scripts.l22_evidence import generator
    bundle = Path("artifacts/m1_cohort/m1_pp2/evidence_bundle")
    index = Path("artifacts/m1_cohort/m1_pp2/independent_acceptance/candidate_evidence_index.json")
    commands = [
        ("generate", ["generate", "--out", str(index), "--evidence-root", str(bundle)]),
        ("audit_strict", ["audit", "--index", str(index), "--evidence-root", str(bundle),
                          "--verify-input-files"]),
        ("audit_portable", ["audit", "--index", str(index), "--evidence-root", str(bundle)]),
    ]
    executions = []
    for label, argv in commands:
        start = datetime.now(timezone.utc).isoformat()
        with (OWN / f"candidate_{label}.log").open("w") as log, redirect_stdout(log), redirect_stderr(log):
            print(json.dumps({"entrypoint": "scripts/l22_evidence/generator.py", "argv": argv,
                              "started_utc": start, "pid": os.getpid()}), flush=True)
            rc = generator.main(argv)
        executions.append({"entrypoint": "scripts/l22_evidence/generator.py", "argv": argv,
                           "started_utc": start, "finished_utc": datetime.now(timezone.utc).isoformat(),
                           "pid": os.getpid(), "exit_code": rc})
        save("candidate_commands.json", executions)
        assert rc == 0, (label, rc)
    own_index = load(index)
    original = load(ROOT / "artifacts/m1_cohort/m1_pp2/candidate_evidence_index.json")
    assert own_index["content_hash"] == original["content_hash"]
    assert own_index["aggregate_verdict"] == "NON_GREEN"
    assert own_index["tally"] == {"PASS": 1, "MISSING_EVIDENCE": 23}
    row = next(r for r in own_index["rows"] if r["process"] == "ProteinProcessingII")
    assert row["green"] is True and row["mechanical_verdict"] == "PASS" and row["reasons"] == []
    directory = ROOT / bundle / "ProteinProcessingII/latest"
    files = sorted(p.name for p in directory.iterdir() if p.is_file())
    assert len(files) == 8 and "allocator_inputs.json" not in files
    compact = []
    for filename in files:
        path = directory / filename
        actual_sha = sha(path)
        if filename == "input_manifest.json":
            raw_manifest = load(RAW / filename)
            normalized = load(path)
            expected = json.loads(json.dumps(raw_manifest))
            for r in expected["inputs"]:
                resolved = (ROOT / r["path"]).resolve()
                r["path"] = resolved.relative_to(ROOT).as_posix()
            assert expected == normalized
            for r in normalized["inputs"]:
                assert not Path(r["path"]).is_absolute() and "\\" not in r["path"]
                assert sha(ROOT / r["path"]) == r["sha256"], r["path"]
        else:
            assert actual_sha == sha(RAW / filename) == row["artifact_hashes"][filename]
        compact.append({"path": str(path.relative_to(ROOT)), "sha256": actual_sha,
                        "size_bytes": path.stat().st_size})
    save("independent_candidate_verification.json", {
        "explicit_bundle_root": str(bundle), "compact_files": compact, "compact_count": len(compact),
        "normalized_manifest_inputs_rehashed": 61, "index_path": str(index),
        "index_sha256": sha(index), "content_hash": own_index["content_hash"],
        "original_index_sha256": sha(ROOT / "artifacts/m1_cohort/m1_pp2/candidate_evidence_index.json"),
        "same_content_hash_as_original": True, "aggregate": own_index["aggregate_verdict"],
        "tally": own_index["tally"], "owned_row": row,
        "strict_exit": executions[1]["exit_code"], "portable_exit": executions[2]["exit_code"]})


if __name__ == "__main__":
    print(json.dumps({
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(), "ppid": os.getppid(), "argv": sys.argv,
        "cwd": str(ROOT), "executable": sys.executable,
        "opencell_file": opencell.__file__,
    }), flush=True)
    parser = argparse.ArgumentParser()
    parser.add_argument("mode")
    args = parser.parse_args()
    if args.mode == "inspect":
        inspect()
    elif args.mode == "controls":
        controls()
    elif args.mode == "verify":
        verify()
    elif args.mode == "candidate":
        candidate()
    else:
        raise ValueError(args.mode)
    print(json.dumps({"finished_utc": datetime.now(timezone.utc).isoformat(), "pid": os.getpid()}), flush=True)
