import sys
sys.dont_write_bytecode = True
from review_common import *
import subprocess
from scripts.l22_evidence import catalog, generator, schema
import _l2_2_design_a_runner_helpers as helpers

event("independent_publication_audits_start")
commands = [
    ("independent_bundle", ["bundle", "--source-root", "artifacts/l2_2_gates",
                           "--bundle-root", relative(OUT / "regenerated_bundle")]),
    ("independent_generate_strict", ["generate", "--out", relative(OUT / "candidate_index_strict.json"),
                                    "--evidence-root", relative(CANDIDATE), "--verify-input-files"]),
    ("independent_audit_strict", ["audit", "--index", relative(OUT / "candidate_index_strict.json"),
                                 "--evidence-root", relative(CANDIDATE), "--verify-input-files"]),
    ("independent_audit_portable", ["audit", "--index", relative(OUT / "candidate_index_strict.json"),
                                   "--evidence-root", relative(CANDIDATE)]),
    ("independent_generate_portable", ["generate", "--out", relative(OUT / "candidate_index_portable.json"),
                                      "--evidence-root", relative(CANDIDATE)]),
    ("doer_candidate_audit_strict", ["audit", "--index", relative(LANE / "candidate_index_resume.json"),
                                   "--evidence-root", relative(CANDIDATE), "--verify-input-files"]),
    ("doer_candidate_audit_portable", ["audit", "--index", relative(LANE / "candidate_index_resume.json"),
                                     "--evidence-root", relative(CANDIDATE)]),
]
stages = []
for name, args in commands:
    command = [sys.executable, "scripts/l22_evidence/generator.py", *args]
    started = now()
    with (OUT / f"{name}.log").open("w") as stream:
        child = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        event("publication_child_started", name=name, command=command,
              child_pid=child.pid, started_at=started, log=f"{name}.log")
        rc = child.wait()
    record = {"name": name, "command": command, "child_pid": child.pid,
              "started_at": started, "finished_at": now(), "exit_code": rc,
              "log": f"{name}.log", "log_sha256": sha(OUT / f"{name}.log")}
    stages.append(record)
    save("publication_commands.json", stages)
    event("publication_child_completed", **record)
    assert rc == 0, record
entry = catalog.in_scope_processes()["ProteinTranslocation"]
files = (*schema.REQUIRED_AUTHORITY_FILES, *schema.MANDATORY_SIDECAR_FILES,
         schema.SWEEP_PROVENANCE_FILE)
copies = []
for name in files:
    regenerated = OUT / "regenerated_bundle/ProteinTranslocation/latest" / name
    candidate = CANDIDATE / "ProteinTranslocation/latest" / name
    assert sha(regenerated) == sha(candidate) == sha(RAW / name)
    copies.append({"name": name, "sha256": sha(regenerated)})
manifest = load(CANDIDATE / "ProteinTranslocation/latest/input_manifest.json")
for record in manifest["inputs"]:
    path = record["path"]
    assert "\\" not in path and not path.startswith(("/", "E:", "C:", "D:"))
    assert ".." not in Path(path).parts
indices = [load(p) for p in (OUT / "candidate_index_strict.json",
                             OUT / "candidate_index_portable.json",
                             LANE / "candidate_index_resume.json")]
normalized_hashes = [generator.content_hash(index) for index in indices]
assert len(set(normalized_hashes)) == 1
for index in indices:
    row = next(r for r in index["rows"] if r["process"] == "ProteinTranslocation")
    assert row["green"] and row["mechanical_verdict"] == "PASS"
    assert not row["reasons"] and not row["warnings"]
    assert index["aggregate_verdict"] == "NON_GREEN"
    assert index["tally"] == {"MISSING_EVIDENCE": 23, "PASS": 1}
save("independent_candidate_row.json", row)
save("publication_proof.json", {
    "input_root": relative(CANDIDATE),
    "owned_row": row, "tally": indices[0]["tally"],
    "aggregate": "NON_GREEN", "strict_portable_doer_content_hash": normalized_hashes[0],
    "fresh_generator_module_sha256": sha(ROOT / "scripts/l22_evidence/generator.py"),
    "candidate_index_sha256": sha(LANE / "candidate_index_resume.json"),
    "independent_index_strict_sha256": sha(OUT / "candidate_index_strict.json"),
    "independent_index_portable_sha256": sha(OUT / "candidate_index_portable.json"),
    "normalized_input_paths": len(manifest["inputs"]),
    "independently_regenerated_and_live_candidate_identical": copies,
    "portable_audit_meaning": "Default non-strict semantics exercised against explicit candidate; raw files remained mounted, not deleted or hidden.",
})

drift = []
for source in manifest["inputs"]:
    wrong = {**source, "path": str(ROOT / source["path"]), "sha256": "0" * 64}
    try:
        helpers.verify_input_sources([wrong])
    except ValueError as exc:
        assert "Consumed input source hash drift:" in str(exc)
        drift.append({"path": source["path"], "actual_sha256": source["sha256"],
                      "rejected": str(exc)})
    else:
        raise AssertionError(source)
assert len(drift) == 64
save("all_descriptor_drift_rejections.json", drift)
event("independent_publication_audits_complete", stages=len(stages),
      compact_regeneration_matches=len(copies), rejected_wrong_descriptors=len(drift),
      PT="PASS", aggregate="NON_GREEN", tally=indices[0]["tally"])
