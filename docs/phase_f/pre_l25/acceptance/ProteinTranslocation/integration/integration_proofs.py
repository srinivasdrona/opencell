import sys
sys.dont_write_bytecode = True
from integration_common import *
import tarfile
import yaml
import h5py
import numpy as np
import opencell
import _l2_2_design_a_runner_helpers as adapters
from scripts.l22_evidence import catalog, generator, schema
from scripts import pre_l25_honesty as honesty

event("committed_integration_proofs_start")
native = load(OUT / "native_preflight.json")
original_native = load(OUT / "original_preflight.json")
assert native["head"] == HEAD and native["branch"] == "integrate/m1-accepted-20261019"
assert not native["status"] and not original_native["original_status"]
assert original_native["original_head"] == "65df71c26553f42dd95759b948de42647987bf68"
assert sys.executable == "/mnt/e/opencell/.venv-wsl/bin/python"
imports = {m.__name__: str(Path(m.__file__).resolve())
           for m in (opencell, adapters, generator, schema, catalog, honesty)}
assert all(Path(p).is_relative_to(ROOT) for p in imports.values())
save("environment.json", {"executable": sys.executable, "prefix": sys.prefix,
                          "local_imports": imports, "native_preflight": native})


def archive(name):
    with tarfile.open(OUT / name) as tar:
        return {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}


current_tree = tree("sealed_tree.txt")
pre_tree = tree("pre_pt_tree.txt")
sealed, pre = archive("sealed_payloads.tar"), archive("pre_pt_payloads.tar")
receipt_prefix = RECEIPTS.relative_to(ROOT).as_posix() + "/"
compact_prefix = PT.relative_to(ROOT).as_posix() + "/"
payload_paths = sorted(p for p in current_tree if p.startswith((receipt_prefix, compact_prefix)))
receipt_paths = [p for p in payload_paths if p.startswith(receipt_prefix)]
compact_paths = [p for p in payload_paths if p.startswith(compact_prefix)]
assert len(receipt_paths) == 69 and len(compact_paths) == 8
assert {p[len(receipt_prefix):] for p in receipt_paths} == {
    p.name for p in OLD_REVIEW.iterdir() if p.is_file()}
records = []
for path in payload_paths:
    original = (OLD_REVIEW / path[len(receipt_prefix):]
                if path.startswith(receipt_prefix)
                else ORIGINAL / "artifacts/m1_cohort/m1_pt/evidence_bundle/ProteinTranslocation/latest" / path[len(compact_prefix):])
    committed = sealed[path]
    working, accepted_original = (ROOT / path).read_bytes(), original.read_bytes()
    assert committed == working == accepted_original, path
    oid = hashlib.sha1(f"blob {len(committed)}\0".encode() + committed).hexdigest()
    assert oid == current_tree[path], path
    records.append({"path": path, "native_git_blob_oid": current_tree[path],
                    "archive_blob_oid_independent": oid,
                    "bytes": len(committed),
                    "committed_sha256": hashlib.sha256(committed).hexdigest(),
                    "current_sha256": sha(ROOT / path), "original_sha256": sha(original),
                    "original": str(original), "equal": True})
parent_proof = load(ROOT / "artifacts/m1_integration/pt-committed-byte-proof.json")
assert parent_proof["matched"] is True
assert {r["path"]: r["sha256"] for r in parent_proof["records"]} == {
    r["path"]: r["committed_sha256"] for r in records}
manifest = load(RECEIPTS / "REVIEW_DELIVERY_MANIFEST.json")
assert len(manifest["files"]) == 18
manifest_proof = []
for name, expected in manifest["files"].items():
    assert sha(RECEIPTS / name) == sha(OLD_REVIEW / name) == expected
    assert hashlib.sha256(sealed[receipt_prefix + name]).hexdigest() == expected
    manifest_proof.append({"name": name, "expected_and_actual_sha256": expected})
save("committed_byte_proof.json", {
    "sealed_head": HEAD, "method": "Native Windows Git ls-tree blob IDs and native Git archive bytes, independently SHA1-framed as Git blobs and SHA256-compared to current and original bytes. Not merely attributes or parent report.",
    "review_root_files": 69, "compact_files": 8, "matches": len(records),
    "records": records, "original_delivery_manifest_matches": manifest_proof,
    "also_matches_parent_report": True,
    "original_nested_duplicate_bundle": "Original review has8 additional nested regenerated_bundle outputs; these duplicate the same compact8 and are not among the69 original root receipts. Their accepted compact content is separately bound by the original proof."})

allowed_journal_diffs = {"data/provenance/llm_interactions.jsonl", "opencell/provenance/llm_interactions.jsonl"}
runtime_diff_lines = (OUT / "frozen_runtime_diff.txt").read_text(encoding="utf-8-sig").splitlines()
actual_runtime_diffs = {line.split("\t")[-1] for line in runtime_diff_lines if line.strip()}
assert actual_runtime_diffs <= allowed_journal_diffs
bundle_prefix = BUNDLE_ROOT.relative_to(ROOT).as_posix() + "/"
unrelated_bundle_files = sorted(p for p in pre_tree if p.startswith(bundle_prefix)
                                and not p.startswith(compact_prefix))
assert all(current_tree.get(p) == pre_tree[p] for p in unrelated_bundle_files)
assert {p for p in current_tree if p.startswith(bundle_prefix) and not p.startswith(compact_prefix)} == set(unrelated_bundle_files)
pp2_prefix = "docs/phase_f/pre_l25/acceptance/ProteinProcessingII/"
pp2_receipts = sorted(p for p in pre_tree if p.startswith(pp2_prefix))
assert pp2_receipts and all(current_tree.get(p) == pre_tree[p] for p in pp2_receipts)
pp2_semantic = "docs/phase_f/audits/ProteinProcessingII_semantic_audit.md"
assert current_tree[pp2_semantic] == pre_tree[pp2_semantic]
baseline_path = "docs/phase_f/pre_l25/PRE_L25_HONESTY_BASELINE.yaml"
baseline = yaml.safe_load(sealed[baseline_path])
old_baseline = yaml.safe_load(pre[baseline_path])
rows = {r["name"]: r for r in baseline["processes"]}
old_rows = {r["name"]: r for r in old_baseline["processes"]}
assert set(rows) == set(old_rows) and len(rows) == 28
assert all(rows[name] == old_rows[name] for name in rows if name != "ProteinTranslocation")
pt, old_pt = rows["ProteinTranslocation"], old_rows["ProteinTranslocation"]
assert pt["eligibility"] == "ELIGIBLE" and pt["behavior_gate"] == "L2.2" and pt["behavior_verdict"] == "PASS"
findings, old_findings = ({f["id"]: f for f in r["findings"]} for r in (pt, old_pt))
assert set(findings) == set(old_findings)
newly_closed = {"PTRANS-COMPLETE-ATTESTATION", "PTRANS-SAMPLE-ISOLATION"}
older_resolved = {"PTRANS-STAGE2-ALGORITHM", "PTRANS-GENUINE-EVIDENCE"}
assert {k for k in findings if findings[k] != old_findings[k]} == newly_closed
assert all(findings[k] == old_findings[k] and findings[k]["disposition"] == "RESOLVED"
           for k in older_resolved)
evidence_proof = []
for name in newly_closed:
    f = findings[name]
    assert old_findings[name]["disposition"] == "OPEN" and f["disposition"] == "RESOLVED"
    assert f["kind"] == old_findings[name]["kind"]
    resolving = [e for e in f["evidence"] if e["path"] == receipt_prefix + "VERDICT.json"]
    assert len(resolving) == 1
    a, b = map(int, resolving[0]["lines"].split("-"))
    excerpt = "\n".join((RECEIPTS / "VERDICT.json").read_text().splitlines()[a-1:b])
    accepted_finding = load(RECEIPTS / "VERDICT.json")["findings"][name]
    assert accepted_finding["verdict"] == "ACCEPTED"
    assert accepted_finding["proof"] in excerpt and '"verdict": "ACCEPTED"' in excerpt
    evidence_proof.append({"finding": name, "status": f["disposition"],
                           "resolving_verdict_span": resolving[0], "excerpt": excerpt})
old_eligible = {name for name, r in old_rows.items() if r["eligibility"] == "ELIGIBLE"}
original_four = old_eligible - {"ProteinProcessingII"}
actual_eligible = {name for name, r in rows.items() if r["eligibility"] == "ELIGIBLE"}
assert len(original_four) == 4 and "ProteinProcessingII" in old_eligible
assert actual_eligible == original_four | {"ProteinProcessingII", "ProteinTranslocation"}
assert len(actual_eligible) == 6
semantic_path = "docs/phase_f/audits/ProteinTranslocation_semantic_audit.md"
assert sealed[semantic_path].startswith(pre[semantic_path])
assert b"Current independent evidence acceptance - 2026-10-19" in sealed[semantic_path][len(pre[semantic_path]):]
assert b"PTRANS-COMPLETE-ATTESTATION" in sealed[semantic_path][len(pre[semantic_path]):]
index_path = "docs/phase_f/l2_2_design_a/evidence_index.json"
index, old_index = json.loads(sealed[index_path]), json.loads(pre[index_path])
index_rows = {r["process"]: r for r in index["rows"]}
old_index_rows = {r["process"]: r for r in old_index["rows"]}
assert index_rows["ProteinProcessingII"] == old_index_rows["ProteinProcessingII"]
assert index["aggregate_verdict"] == "NON_GREEN"
assert index["tally"] == {"FAIL": 18, "MISSING_EVIDENCE": 2, "PASS": 4}
save("finding_and_unrelated_preservation.json", {
    "comparison_base": native["pre_pt_commit"],
    "runtime_diff_from65": sorted(actual_runtime_diffs),
    "runtime_changes_except_allowed_journals": [],
    "unrelated_compact_blobs_unchanged": len(unrelated_bundle_files),
    "PP2_receipt_blobs_unchanged": len(pp2_receipts),
    "PP2_semantic_blob_unchanged": True, "PP2_baseline_and_index_row_unchanged": True,
    "unrelated_baseline_process_payloads_unchanged": 27,
    "prior_resolved_PT_findings_identical": sorted(older_resolved),
    "only_changed_PT_findings": sorted(newly_closed),
    "resolved_finding_evidence": evidence_proof,
    "new_source_mapping": {
        "fresh_sample_owner": "tests/vivarium/_l2_2_design_a_runner_helpers.py:2544-2546",
        "actual_next_update": "tests/vivarium/_l2_2_design_a_runner_helpers.py:2578-2580",
        "final_consumed_input_verification": "tests/vivarium/l2_2_design_a_runner.py:1485-1491"},
    "inherited_citation_note": "Old bug-location references remain in the newly resolved finding evidence lists; resolving new committed VERDICT spans directly contain the matching finding's ACCEPTED proof and current source/control hash mapping. Those preserved historical ranges are not used as the current fresh-owner source proof.",
    "semantic_original_bytes_are_unmodified_prefix": True,
    "stage2_citation_lines_not_shifted": True,
    "original_four_eligible": sorted(original_four),
    "pre_PT_eligible_including_PP2": sorted(old_eligible),
    "current_eligible": sorted(actual_eligible),
    "current_tally": index["tally"], "aggregate": index["aggregate_verdict"]})

entry = catalog.in_scope_processes()["ProteinTranslocation"]
published_manifest = load(PT / "input_manifest.json")
accepted_proof = load(RECEIPTS / "VERDICT.json")
accepted_bindings = load(RECEIPTS / "source_and_compact_bindings.json")
assert generator._current_source_hashes(entry) == accepted_bindings["source_hashes"]
sentinel = load(PT / "sweep_provenance.json")
assert sentinel["source_hashes"] == accepted_bindings["source_hashes"]
assert sentinel["completion_status"] == "COMPLETE" and sentinel["inputs_verified"] is True
assert sentinel["git_sha"] == "65df71c26553f42dd95759b948de42647987bf68"
assert published_manifest["resolved_seeds"] == list(range(50)) and published_manifest["m_ticks"] == 100
assert len(published_manifest["inputs"]) == 64
accepted_inputs = {r["path"]: r for r in load(RECEIPTS / "all_consumed_rehashes.json")}
current_inputs = []
for record in published_manifest["inputs"]:
    path = ROOT / record["path"]
    assert path.is_relative_to(ROOT) and path.is_file()
    actual = sha(path)
    assert actual == record["sha256"] == accepted_inputs[record["path"]]["independent_sha256"]
    proof = {**record, "current_sha256": actual, "bytes": path.stat().st_size}
    if "seed" in record:
        with h5py.File(path, "r") as mat:
            seed = int(np.asarray(mat["metadata/rng_seed"][()]).reshape(-1)[0])
            ticks = int(np.asarray(mat["metadata/n_ticks"][()]).reshape(-1)[0])
        assert seed == record["seed"] and ticks == 100
        proof.update(embedded_seed=seed, embedded_ticks=ticks)
    current_inputs.append(proof)
runtime = adapters.capture_runtime_inputs(entry.name)
runtime_by_path = {str(Path(r["path"]).relative_to(ROOT)): r["sha256"] for r in runtime}
assert len(runtime) == 14
assert runtime_by_path == {r["path"]: r["sha256"] for r in published_manifest["inputs"] if "seed" not in r}
assert sorted(r["seed"] for r in current_inputs if "seed" in r) == list(range(50))
for record in accepted_bindings["files"]:
    name = record["name"]
    assert sha(PT / name) == record["candidate_sha256"] == record["raw_sha256"]
    if name != "sweep_provenance.json":
        assert sentinel["sidecar_hashes"][name] == sha(PT / name)
strict_rows = {}
for name in ("ProteinTranslocation", "ProteinProcessingII"):
    row = generator.build_process_row(catalog.in_scope_processes()[name], BUNDLE_ROOT,
                                      strict_input_files=True)
    assert row["green"] and row["mechanical_verdict"] == "PASS" and not row["reasons"], row
    strict_rows[name] = row
actual_digest, count = honesty.compute_source_digest(ROOT)
assert (actual_digest, count) == ("a4694f00ef286d47283aa90605a3120030c1d700e79cf9560132bcfe50d41525", 140)
assert baseline["source_tree"] == {"sha256": actual_digest, "file_count": count}
save("current_PT_source_input_closure.json", {
    "source_head": HEAD, "original_producer_source": sentinel["git_sha"],
    "source_hashes": sentinel["source_hashes"], "source_hash_count": len(sentinel["source_hashes"]),
    "consumed_count": len(current_inputs), "runtime_count": len(runtime), "oracle_count": 50,
    "inputs": current_inputs, "sentinel": sentinel,
    "compact_files": accepted_bindings["files"],
    "strict_current_rows": strict_rows,
    "actual_baseline_source_digest": actual_digest, "baseline_dependency_count": count,
    "new_biological_execution_or_calibration": False,
    "publication_test_original_sha256": sha(ROOT / "tests/scripts/test_ptrans_published_attestation.py")})
event("committed_integration_proofs_complete", byte_matches=len(records),
      delivery_manifest=18, consumed=64, source_hashes=12,
      strict_rows={k: r["mechanical_verdict"] for k, r in strict_rows.items()},
      eligible=sorted(actual_eligible), index_tally=index["tally"],
      preservation_base=native["pre_pt_commit"])
