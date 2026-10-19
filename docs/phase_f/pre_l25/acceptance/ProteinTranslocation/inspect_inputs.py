import sys
sys.dont_write_bytecode = True
from review_common import *

event("independent_input_inspection_start")
reads = []
phase = "imports"


def audit(event_name, args):
    if event_name == "open" and isinstance(args[0], (str, bytes)):
        path = Path(os.fsdecode(args[0]))
        if path.suffix == ".mat":
            reads.append({"phase": phase, "path": str(path.resolve())})


sys.addaudithook(audit)
import h5py
import numpy as np
from scipy.io import loadmat
import opencell
import _l2_2_design_a_runner_helpers as helpers
import l2_2_design_a_runner as runner
from opencell.vivarium import karr_protein_translocation as pt, protein_state
from scripts.l22_evidence import catalog, generator, schema, verdict

imports = {module.__name__: str(Path(module.__file__).resolve()) for module in
           (opencell, helpers, runner, pt, protein_state, generator, schema, verdict)}
assert all(Path(value).is_relative_to(ROOT) for value in imports.values())
assert sys.executable == "/mnt/e/opencell/.venv-wsl/bin/python"
entry = catalog.in_scope_processes()["ProteinTranslocation"]
assert (entry.n_seeds, entry.m_ticks, runner.DEFAULT_BOOTSTRAP_B) == (50, 100, 1000)
assert (entry.primary_channel, entry.bucket) == ("monomers", "ALGORITHMIC_SHALLOW")
native = load(OUT / "native_preflight.json")
assert native["head"] == "65df71c26553f42dd95759b948de42647987bf68" and not native["status"]
save("environment.json", {"time": now(), "pid": os.getpid(),
                         "executable": sys.executable, "prefix": sys.prefix,
                         "imports": imports, "native_git": native,
                         "catalog": vars(entry)})

phase = "capture_runtime_inputs"
runtime = helpers.capture_runtime_inputs("ProteinTranslocation")
assert len(runtime) == 14
phase = "actual_constructor"
process = pt.KarrProteinTranslocationProcess({"rng_seed": 0})
constructor_reads = {Path(r["path"]).name for r in reads if r["phase"] == phase}
assert constructor_reads == {
    "ProteinTranslocation_flat.mat", "MacromolecularComplexation_flat.mat",
    "RibosomeAssembly_flat.mat"}
phase = "independent_fixture_union"
fixtures = {}
for name in ("ProteinTranslocation", "TerminalOrganelleAssembly",
             "MacromolecularComplexation", "RibosomeAssembly"):
    fixtures[name] = loadmat(ROOT / f"data/karr_fixtures/per_process/{name}_flat.mat",
                            squeeze_me=True, struct_as_record=False)["data"].fixture
fx = fixtures["ProteinTranslocation"]
all_wids = [str(v) for v in np.asarray(fx.monomerWholeCellModelIDs).reshape(-1)]
trans_indices = np.asarray(fx.monomerIndexs_translocating, dtype=int).reshape(-1) - 1
translocating = {all_wids[i] for i in trans_indices}
toa_wids = set(str(v) for v in np.asarray(
    fixtures["TerminalOrganelleAssembly"].substrateWholeCellModelIDs).reshape(-1))
complex_union = set(str(v) for v in np.asarray(
    fixtures["MacromolecularComplexation"].complexWholeCellModelIDs).reshape(-1))
complex_union.update(str(v) for v in np.asarray(
    fixtures["RibosomeAssembly"].complexWholeCellModelIDs).reshape(-1))
complex_union.update({"RNA_POLYMERASE", "RIBOSOME_70S"})
assert set(protein_state.MIGRATED_WIDS) == translocating | toa_wids
assert set(process.complex_enzyme_wids) == set(process.enzyme_wids) & complex_union
assert set(process.monomer_enzyme_wids) == set(process.enzyme_wids) - complex_union
save("constructor_authority.json", {
    "actual_constructor_reads": sorted(constructor_reads),
    "all_mat_read_events": reads,
    "protein_authority": {"pt_translocating": sorted(translocating),
                          "toa": sorted(toa_wids),
                          "union": sorted(translocating | toa_wids)},
    "complex_authority_union": sorted(complex_union),
    "complex_enzyme_wids": process.complex_enzyme_wids,
    "monomer_enzyme_wids": process.monomer_enzyme_wids,
    "registered_parameter_fixtures": schema.PROCESS_PARAMETER_FIXTURES["ProteinTranslocation"],
    "registered_authority_fixtures": schema.PROTEIN_AUTHORITY_FIXTURES,
})

phase = "load_all_actual_oracles"
oracle = helpers.load_karr_oracle("ProteinTranslocation")
assert oracle["canonical_seed_count"] == 50 and oracle["seed_ids"] == list(range(50))
assert oracle["before_monomers"].shape == oracle["after_monomers"].shape == (50, 100, 2892)
manifest = load(RAW / "input_manifest.json")
assert manifest["resolved_seeds"] == list(range(50)) and manifest["m_ticks"] == 100
sources = helpers.merge_input_sources(runtime, oracle["input_sources"])
assert len(sources) == len(manifest["inputs"]) == 64


def normalized(records):
    return {relative(ROOT / r["path"]): {k: v for k, v in r.items() if k != "path"}
            for r in records}


assert normalized(sources) == normalized(manifest["inputs"])
prior = load(LANE / "preflight_consumed_inputs_resume.json")
if isinstance(prior, dict):
    prior = prior.get("inputs", prior.get("sources", prior))
assert normalized(sources) == normalized(prior)
rehashes = []
for record in manifest["inputs"]:
    path = ROOT / record["path"]
    actual = sha(path)
    assert actual == record["sha256"]
    rehashes.append({**record, "independent_sha256": actual, "bytes": path.stat().st_size})
save("all_consumed_rehashes.json", rehashes)

copies = load(LANE / "accepted-input-copy.json")
assert len(copies) == 50
population = load(ROOT / "docs/phase_f/l2_2_design_a/oracle_population_manifest.json")
save("accepted_population_structure.json", {
    "top_keys": list(population), "sha256": sha(
        ROOT / "docs/phase_f/l2_2_design_a/oracle_population_manifest.json")})
save("population_pt_entries.json", [
    r for r in population.get("processes", {}).get("ProteinTranslocation", [])
] if isinstance(population.get("processes", {}), dict) and
    isinstance(population.get("processes", {}).get("ProteinTranslocation", []), list) else [])

inventory = []
raw_arrays = {}
for source in sorted(oracle["input_sources"], key=lambda r: r["seed"]):
    seed = source["seed"]
    path = Path(source["path"])
    copy = [r for r in copies if r["RelativePath"].replace("\\", "/") ==
            path.relative_to(ROOT / "data/m1_sources/karr_native").as_posix()]
    assert len(copy) == 1 and copy[0]["Sha256"] == source["sha256"]
    assert copy[0]["Destination"].replace("\\", "/").endswith(
        path.relative_to(ROOT).as_posix())
    with h5py.File(path, "r") as trace:
        embedded = int(np.asarray(trace["metadata/rng_seed"][()]).reshape(-1)[0])
        ticks = int(np.asarray(trace["metadata/n_ticks"][()]).reshape(-1)[0])
        assert embedded == seed and ticks == 100
        assert set(trace["states_before"]) == set(trace["states_after"]) == {
            "substrates", "enzymes", "boundEnzymes", "monomers"}
        shapes = {}
        for group in ("states_before", "states_after"):
            for channel in trace[group]:
                refs = np.asarray(trace[group][channel][()]).reshape(-1)
                assert len(refs) == 100
                matrices = [np.asarray(trace[ref][()], dtype=float) for ref in refs]
                shapes[f"{group}/{channel}"] = sorted({tuple(a.shape) for a in matrices})
                assert len({a.shape for a in matrices}) == 1
                projected = np.stack([a.reshape(-1) for a in matrices])
                key = ("before_" if group == "states_before" else "after_") + (
                    "bound_enzymes" if channel == "boundEnzymes" else channel)
                if key in oracle:
                    np.testing.assert_array_equal(oracle[key][seed], projected)
                raw_arrays.setdefault(key, []).append(projected)
        inventory.append({"seed": seed, "embedded_rng_seed": embedded, "ticks": ticks,
                          "path": relative(path), "sha256": sha(path), "trace_shapes": shapes})
save("complete_50_seed_inventory.json", inventory)
assert not (ROOT / "data/m1_sources/karr_native/per_process_traces_v2_s000/ProteinTranslocation_100ticks.mat").exists()
local = list((ROOT / "data/m1_sources/karr_native").glob("per_process_traces_v2*/ProteinTranslocation_100ticks.mat"))
assert len(local) == 50
arrays = {key: np.asarray(values) for key, values in raw_arrays.items()}
np.savez_compressed(OUT / "independent_karr_only_arrays.npz", **arrays)

allocator = load(RAW / "allocator_inputs.json")["records"]
assert len(allocator) == 5000
seen = set()
for r in allocator:
    s, t = r["seed"], r["tick"]
    assert (s, t) not in seen and r["process"] == "ProteinTranslocation"
    assert r["primary_channel"] == "monomers"
    seen.add((s, t))
    for field, channel in {
        "substrates_sum_before": "substrates", "primary_sum_before": "monomers",
        "enzymes_sum_before": "enzymes", "monomers_sum_before": "monomers",
        "bound_enzymes_sum_before": "bound_enzymes",
    }.items():
        assert r[field] == float(np.sum(arrays["before_" + channel][s, t]))
    assert r["substrates_nonzero_before"] == int(np.count_nonzero(arrays["before_substrates"][s, t]))
assert seen == {(s, t) for s in range(50) for t in range(100)}
activity = {}
for channel in ("monomers", "substrates"):
    difference = arrays["after_" + channel] - arrays["before_" + channel]
    activity[channel] = {
        "shape": list(difference.shape),
        "active_seed_ticks": int(np.count_nonzero(np.any(difference != 0, axis=2))),
        "nonzero_delta_coordinates": int(np.count_nonzero(difference)),
        "active_ticks_per_seed": np.count_nonzero(np.any(difference != 0, axis=2), axis=1).tolist(),
        "after_nonzero": int(np.count_nonzero(arrays["after_" + channel])),
    }
save("shape_activity_allocator.json", {
    "activity": activity, "allocator_records_verified": len(allocator),
    "all_seed_ticks_present": True,
    "raw_monomer_shapes": inventory[0]["trace_shapes"],
    "adapter_raw_full_array_equalities": "every seed, both groups, every available family",
    "arrays_are": "Karr only; not retained original OC outputs nor fresh full biological rerun"})

sweep = load(RAW / "sweep_provenance.json")
assert sweep["completion_status"] == "COMPLETE" and sweep["inputs_verified"] is True
assert (sweep["n_seeds"], sweep["m_ticks"]) == (50, 100)
assert sweep["git_sha"] == native["head"]
current = generator._current_source_hashes(entry)
assert current == sweep["source_hashes"]
assert load(LANE / "preflight_source_hashes_resume.json") == current
bindings = []
files = (*schema.REQUIRED_AUTHORITY_FILES, *schema.MANDATORY_SIDECAR_FILES,
         schema.SWEEP_PROVENANCE_FILE)
assert len(files) == 8
for name in files:
    raw_hash, candidate_hash = sha(RAW / name), sha(CANDIDATE / entry.name / "latest" / name)
    assert raw_hash == candidate_hash
    if name != schema.SWEEP_PROVENANCE_FILE:
        assert raw_hash == sweep["sidecar_hashes"][name]
    bindings.append({"name": name, "raw_sha256": raw_hash,
                     "candidate_sha256": candidate_hash})
save("source_and_compact_bindings.json", {"source_hashes": current, "files": bindings,
     "candidate_index_sha256": sha(LANE / "candidate_index_resume.json"),
     "publication_test_original_sha256": sha(ROOT / "tests/scripts/test_ptrans_published_attestation.py")})
timing = load(LANE / "sweep_report.json")["jobs"][0]
assert timing["duration_s"] > 0 and timing["status"] == "RAN_EXIT_0"
assert timing["exit_code"] == 0
assert timing["started_at"] < load(RAW / "result.json")["timestamp"] < sweep["written_at"]
save("sweep_time_and_command.json", {
    "job": timing, "native_head": native["head"], "sentinel": sweep,
    "native_log": (ROOT / "artifacts/l2_2_gates/_sweep_logs/ProteinTranslocation.log").read_text(),
    "telemetry": (LANE / "gate_processes_resume.log").read_text(),
    "note": "Independent receipt inspection of original execution, not this review's full rerun"})
event("independent_input_inspection_complete", consumed=len(sources),
      seeds=len(inventory), source_hashes=len(current), compact_files=len(bindings),
      activity=activity)
