import sys
sys.dont_write_bytecode = True
from review_common import *
import math
import numpy as np
from scipy.stats import wasserstein_distance, skew, kurtosis
from scripts.l22_evidence import catalog, schema, verdict
import _l2_2_design_a_runner_helpers as helpers

event("independent_numeric_population_start")
entry = catalog.in_scope_processes()["ProteinTranslocation"]
inputs = load(OUT / "all_consumed_rehashes.json")
population = load(ROOT / "docs/phase_f/l2_2_design_a/oracle_population_manifest.json")
pt_population = population["processes"]["ProteinTranslocation"]
assert len(pt_population["files"]) == 50
accepted = {r["relative_path"]: r["sha256"] for r in pt_population["files"]}
current = {r["path"].split("data/m1_sources/karr_native/")[1]: r["sha256"]
           for r in inputs if "seed" in r}
assert accepted == current
copies = load(LANE / "accepted-input-copy.json")
assert {r["RelativePath"].replace("\\", "/"): r["Sha256"] for r in copies} == accepted
save("accepted_population_verification.json", {
    "accepted_manifest_sha256": sha(ROOT / "docs/phase_f/l2_2_design_a/oracle_population_manifest.json"),
    "pt_manifest_metadata": {k: v for k, v in pt_population.items() if k != "files"},
    "all_50_population_copy_consumed_current_records_match": True,
    "full_population": pt_population["files"]})

result = load(RAW / "result.json")
null = load(RAW / "null_calibration.json")
thresholds = load(RAW / "thresholds.json")
assert result["seeds"] == list(range(50))
assert result["ticks"] == 100 and result["bootstrap_B"] == 1000
assert result["n_observations_per_channel"] == 5000
assert result["canonical_seed_count"] == 50
assert result["warnings"] == null["warnings"] == []
arrays = np.load(OUT / "independent_karr_only_arrays.npz")
report = {}
for channel in ("substrates", "monomers"):
    values = arrays["after_" + channel]
    assert values.shape[:2] == (50, 100)
    sorted_values = np.sort(values, axis=2)
    # Equal-weight, equal-cardinality empirical W1 is mean absolute rank difference.
    # Precompute all actual seed-pair/tick distances once; no biological execution.
    distances = np.empty((50, 50, 100), dtype=float)
    for left in range(50):
        distances[left] = np.mean(np.abs(sorted_values[left][None] - sorted_values), axis=2)
    np.testing.assert_array_equal(np.diagonal(distances, axis1=0, axis2=1), 0)
    checks = []
    for a, b, t in ((0, 1, 2), (49, 0, 99), (13, 28, 51), (11, 46, 10), (0, 0, 2)):
        independent = float(distances[a, b, t])
        existing_scipy = float(wasserstein_distance(values[a, t], values[b, t]))
        assert math.isclose(independent, existing_scipy, rel_tol=1e-12, abs_tol=1e-12)
        checks.append({"left_seed": a, "right_seed": b, "tick": t,
                       "rank_formula": independent, "scipy": existing_scipy})
    rng = np.random.default_rng(0xCA11B)
    boot = np.empty(1000)
    sampled_indices = np.empty((1000, 2, 50), dtype=int)
    for i in range(1000):
        left = rng.integers(0, 50, size=50)
        right = rng.integers(0, 50, size=50)
        sampled_indices[i] = [left, right]
        boot[i] = float(np.mean(distances[left, right, :]))
    q95 = float(np.percentile(boot, 95))
    summary = {"mean": float(np.mean(boot)), "stddev": float(np.std(boot)),
               "min": float(np.min(boot)), "max": float(np.max(boot))}
    oldnull = null["channels"][channel]
    assert oldnull["bootstrap_B"] == 1000 and oldnull["n_karr_seeds"] == 50
    assert oldnull["n_ticks"] == 100
    assert math.isclose(q95, oldnull["q95_null"], rel_tol=1e-12, abs_tol=1e-14)
    for k, v in summary.items():
        assert math.isclose(v, oldnull["bootstrap_values_summary"][k],
                            rel_tol=1e-12, abs_tol=1e-14)
    p = result["channels"][channel]
    assert p["n_nonzero_karr"] == int(np.count_nonzero(values))
    flat = values.reshape(-1)
    actual_stats = {"min": float(np.min(flat)), "max": float(np.max(flat)),
                    "mean": float(np.mean(flat)), "stddev": float(np.std(flat)),
                    "skew": float(skew(flat, bias=False)),
                    "kurtosis": float(kurtosis(flat, fisher=True, bias=False))}
    for k, v in actual_stats.items():
        assert math.isclose(v, p["samples_karr"][k], rel_tol=1e-12, abs_tol=1e-14)
    snapshot = thresholds["channels"][channel]
    assert snapshot["k_eng"] == 2.0 and snapshot["absolute_floor"] == 1.0
    rethreshold = max(snapshot["absolute_floor"], snapshot["k_eng"] * q95)
    assert math.isclose(rethreshold, p["threshold"], rel_tol=1e-12, abs_tol=1e-14)
    assert snapshot["q95_null"] == p["q95_null"] == oldnull["q95_null"]
    assert snapshot["threshold"] == p["threshold"]
    w1 = p["w1_oc_vs_karr"]
    assert all(math.isfinite(p[k]) and p[k] >= 0 for k in
               ("w1_oc_vs_karr", "q95_null", "threshold", "n_nonzero_oc", "n_nonzero_karr"))
    assert min(p["n_nonzero_oc"], p["n_nonzero_karr"]) >= schema.MIN_NONZERO_EVENTS
    rederived = "SEED_NOISE" if w1 <= q95 else ("PASS" if w1 <= rethreshold else "FAIL")
    assert p["verdict"] == rederived == "SEED_NOISE"
    assert p["per_sample_w1_summary"]["mean"] == w1
    if channel == "monomers":
        assert p["per_sample_w1_summary"] == {"min": 0.0, "max": 0.0, "mean": 0.0}
    assert verdict.rederive_channel(channel, p, is_primary=channel == "monomers") == (rederived, [])
    np.savez_compressed(OUT / f"independent_null_{channel}.npz",
                        all_seed_pair_tick_w1=distances,
                        bootstrap_values=boot, seed_indices=sampled_indices)
    report[channel] = {"q95_independent": q95, "q95_retained": p["q95_null"],
                       "bootstrap_values_summary_independent": summary,
                       "threshold_independent": rethreshold, "threshold_retained": p["threshold"],
                       "retained_w1_rescored": w1, "rederived_channel_verdict": rederived,
                       "actual_karr_stats": actual_stats, "rank_formula_scipy_checks": checks,
                       "original_oc_tensor_available": False,
                       "independent_oc_w1_recomputed_from_original_tensor": False}
pv = verdict.rederive_process(entry.name, entry, result)
assert pv.mechanical_verdict == "PASS" and not pv.reasons
save("independent_numeric_proof.json", {
    "method": "Every actual Karr seed-pair/tick W1 via equal-mass sorted-rank identity, fixed seed-level bootstrap B1000; scalar evaluator re-score using retained measured OC raw numeric fields.",
    "B": 1000, "N": 50, "M": 100, "validation_seed": 0xCA11B,
    "channels": report, "mechanical_verdict": pv.mechanical_verdict,
    "channel_verdicts": pv.channel_verdicts, "reasons": pv.reasons,
    "h12": {"retained_deterministic_convergence_warning": False,
            "support_required_for_current_packet": False,
            "note": "No convergence/H12 demotion is retained. W1=0 is sorted empirical-distribution agreement, not coordinate-wise identity; historical support is not assumed or promoted."},
    "limitation": "Original OC tensors are not saved. This independently recalibrates Karr nulls and re-scores retained source-bound numeric measurements; it is not independent reproduction of original full OC outputs nor a new full biological sweep.",
})
event("independent_numeric_population_complete", calibrated_channels=list(report),
      process_verdict=pv.mechanical_verdict,
      thresholds={k: v["threshold_independent"] for k, v in report.items()},
      q95={k: v["q95_independent"] for k, v in report.items()})
