from __future__ import annotations

from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
import dataclasses
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

ROOT = Path.cwd().resolve()
OWN = ROOT / "artifacts/m1_integration/independent_pp2"
ORIGINAL = Path("/mnt/e/opencell-worktrees/m1-pp2-20261017")
RECEIPT = "docs/phase_f/pre_l25/acceptance/ProteinProcessingII/"
BUNDLE = "docs/phase_f/l2_2_design_a/evidence_bundle"
ORIGINAL_RECEIPT = ORIGINAL / "artifacts/m1_cohort/m1_pp2/independent_acceptance"
ORIGINAL_BUNDLE = ORIGINAL / "artifacts/m1_cohort/m1_pp2/evidence_bundle/ProteinProcessingII/latest"
CANDIDATE_HEAD = "c3ec943df61e485c0f50a3f770f85fdb5eae2cd1"
sys.path.insert(0, str(ROOT))
import opencell

assert sys.executable == "/mnt/e/opencell/.venv-wsl/bin/python", sys.executable
assert Path(opencell.__file__).resolve().is_relative_to(ROOT), opencell.__file__


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(filename, value):
    path = OWN / filename
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")
    print(json.dumps({"report": filename, "sha256": sha_bytes(path.read_bytes())}), flush=True)


def main():
    from scripts.l22_evidence import catalog, generator
    from scripts import pre_l25_honesty
    import yaml

    snap = load(OWN / "before_snapshot.json")
    assert snap["head"] == CANDIDATE_HEAD and not snap["status"] and not snap["runtime_diff_names"]
    if "--finish" in sys.argv:
        authorities = []
        with zipfile.ZipFile(OWN / "committed_authorities.zip") as archive:
            for line in (OWN / "authority_native_tree.txt").read_text(encoding="utf-8-sig").splitlines():
                header, path = line.split("\t", 1)
                oid = header.split()[2]
                data = archive.read(path)
                assert hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == oid
                assert data == (ROOT / path).read_bytes(), path
                authorities.append({"path": path, "git_blob_oid": oid,
                                    "committed_and_current_sha256": sha_bytes(data)})
        assert len(authorities) == 4
        save("committed_authority_bytes.json", authorities)
    tree = {}
    for line in (OWN / "native_tree.txt").read_text(encoding="utf-8-sig").splitlines():
        header, path = line.split("\t", 1)
        mode, kind, oid = header.split()
        assert mode == "100644" and kind == "blob"
        tree[path] = oid
    assert len(tree) == 40
    records = []
    with zipfile.ZipFile(OWN / "committed_pp2.zip") as archive:
        blob_bytes = {}
        counts = Counter()
        for path, git_oid in sorted(tree.items()):
            native_blob = archive.read(path)
            expected_oid = hashlib.sha1(
                b"blob " + str(len(native_blob)).encode() + b"\0" + native_blob
            ).hexdigest()
            assert expected_oid == git_oid, (path, "archive does not match actual Git blob object")
            filesystem_bytes = (ROOT / path).read_bytes()
            if path.startswith(RECEIPT):
                original_path = ORIGINAL_RECEIPT / path.removeprefix(RECEIPT)
                counts["receipts"] += 1
            else:
                prefix = BUNDLE + "/ProteinProcessingII/latest/"
                assert path.startswith(prefix), path
                original_path = ORIGINAL_BUNDLE / path.removeprefix(prefix)
                counts["bundle"] += 1
            original_bytes = original_path.read_bytes()
            assert native_blob == filesystem_bytes == original_bytes, path
            blob_bytes[path] = native_blob
            records.append({
                "path": path, "git_blob_oid": git_oid,
                "git_archive_sha256": sha_bytes(native_blob),
                "current_filesystem_sha256": sha_bytes(filesystem_bytes),
                "original_accepted_sha256": sha_bytes(original_bytes),
                "size_bytes": len(native_blob), "crlf_count": native_blob.count(b"\r\n"),
                "all_three_byte_equal": True,
            })
        assert counts == {"receipts": 32, "bundle": 8}, counts
        recorded_hashes = json.loads(blob_bytes[RECEIPT + "report_hashes.json"].decode("utf-8-sig"))
        for record in recorded_hashes:
            assert sha_bytes(blob_bytes[RECEIPT + record["file"]]) == record["sha256"], record
        known_receipts = {
            "STATUS.md": "11346d1e950d57f60e286883e8fb7101115469a122a2b64088381cbb59a5bb6a",
            "VERDICT.json": "9480b2eb6510962261aa189da7063e912564c026e076afa524f02c431c82c7e7",
            "controls.xml": "46cc7d226917f39782ba28de945e2233525c8e92c2dc99466759a7160d86e24e",
            "independent_measurements.json": "6b2284dc56cecf6fd517ddd13ec2a34f5d65529970be22d987be04cbfe75c1d5",
        }
        for filename, digest in known_receipts.items():
            assert sha_bytes(blob_bytes[RECEIPT + filename]) == digest, filename
        prior_completion = json.loads(blob_bytes[RECEIPT + "completion_verification.json"].decode("utf-8-sig"))
        assert prior_completion["status_sha256"] == known_receipts["STATUS.md"]
        assert prior_completion["verdict_sha256"] == known_receipts["VERDICT.json"]
        receipt_verdict = json.loads(blob_bytes[RECEIPT + "VERDICT.json"].decode("utf-8-sig"))
        assert receipt_verdict["verdict"] == "ACCEPTED"
        save("committed_and_filesystem_preservation.json", {
            "candidate_head": CANDIDATE_HEAD, "native_git_archive_object_ids_verified": True,
            "counts": dict(counts), "files_byte_equal": 40,
            "recorded_receipt_hashes_verified": len(recorded_hashes),
            "known_original_hashes_verified": known_receipts, "records": records,
        })

    entry = catalog.in_scope_processes()["ProteinProcessingII"]
    strict_start = datetime.now(timezone.utc).isoformat()
    strict = generator.build_process_row(
        entry, ROOT / BUNDLE, strict_input_files=True)
    assert strict["green"] is True and strict["mechanical_verdict"] == "PASS"
    assert strict["reasons"] == []
    save("strict_current_pp2_row.json", {
        "call": "scripts.l22_evidence.generator.build_process_row",
        "kwargs": {"process": "ProteinProcessingII", "evidence_root": BUNDLE,
                   "strict_input_files": True},
        "started_utc": strict_start, "finished_utc": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(), "row": strict,
    })

    manifest = load(ROOT / BUNDLE / "ProteinProcessingII/latest/input_manifest.json")
    verified_inputs = []
    for record in manifest["inputs"]:
        path = Path(record["path"])
        assert not path.is_absolute() and "\\" not in record["path"]
        actual = sha_bytes((ROOT / path).read_bytes())
        assert actual == record["sha256"], path
        verified_inputs.append({**record, "actual_candidate_sha256": actual})
    assert len(verified_inputs) == 61
    assert sorted(r["seed"] for r in verified_inputs if "seed" in r) == list(range(50))
    save("candidate_current_input_bytes.json", {
        "verified_count": 61, "seed_count": 50, "non_seed_count": 11,
        "input_manifest_sha256": sha_bytes((ROOT / BUNDLE / "ProteinProcessingII/latest/input_manifest.json").read_bytes()),
        "records": verified_inputs,
    })

    commands = [
        ("portable_full_index", "scripts/l22_evidence/generator.py",
         ["audit", "--index", "docs/phase_f/l2_2_design_a/evidence_index.json",
          "--evidence-root", BUNDLE], generator.main),
        ("honesty", "scripts/pre_l25_honesty.py",
         ["audit", "--baseline", "docs/phase_f/pre_l25/PRE_L25_HONESTY_BASELINE.yaml"],
         pre_l25_honesty.main),
    ]
    command_records = []
    if "--finish" in sys.argv:
        command_records = load(OWN / "audit_commands.json")
        assert len(command_records) == 2 and all(c["exit_code"] == 0 for c in command_records)
        assert "integrity: OK" in (OWN / "portable_full_index.log").read_text()
        assert "INTEGRITY_OK; eligible=5/28; blocked=23" in (OWN / "honesty.log").read_text()
        for authority in snap["authority_before"]:
            assert sha_bytes((ROOT / authority["path"].replace("\\", "/")).read_bytes()) == authority["sha256"]
    else:
        for label, entrypoint, argv, invoke in commands:
            started = datetime.now(timezone.utc).isoformat()
            with (OWN / f"{label}.log").open("w") as log, redirect_stdout(log), redirect_stderr(log):
                print(json.dumps({"entrypoint": entrypoint, "argv": argv, "pid": os.getpid(),
                                  "started_utc": started}), flush=True)
                rc = invoke(argv)
            command_records.append({
                "entrypoint": entrypoint, "argv": argv, "exit_code": rc,
                "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
                "pid": os.getpid(),
            })
            save("audit_commands.json", command_records)
            assert rc == 0, (label, rc)

    index_path = ROOT / "docs/phase_f/l2_2_design_a/evidence_index.json"
    index = load(index_path)
    assert index["aggregate_verdict"] == "NON_GREEN"
    assert index["tally"] == {"PASS": 3, "FAIL": 19, "MISSING_EVIDENCE": 2}
    indexed_pp2 = next(r for r in index["rows"] if r["process"] == "ProteinProcessingII")
    assert indexed_pp2["green"] is True and indexed_pp2["mechanical_verdict"] == "PASS"
    assert indexed_pp2["reasons"] == []
    assert indexed_pp2["artifact_hashes"] == strict["artifact_hashes"]
    failed = [r for r in index["rows"] if r["mechanical_verdict"] == "FAIL"]
    assert all(any("STALE" in reason for reason in r["reasons"]) for r in failed)

    baseline_path = ROOT / "docs/phase_f/pre_l25/PRE_L25_HONESTY_BASELINE.yaml"
    baseline = yaml.safe_load(baseline_path.read_text())
    original_baseline = yaml.safe_load(
        (ORIGINAL / "docs/phase_f/pre_l25/PRE_L25_HONESTY_BASELINE.yaml").read_text())
    pp2 = next(p for p in baseline["processes"] if p["name"] == "ProteinProcessingII")
    expected_ids = {"PPII-DEVIATIONS", "PPII-LEGACY-OWNERSHIP",
                    "PPII-REPLAY-INPUT-EVIDENCE", "PPII-PROJECTION-GUARD-INPUTS"}
    assert {f["id"] for f in pp2["findings"]} == expected_ids
    assert all(f["disposition"] == "RESOLVED" for f in pp2["findings"])
    assert pp2["eligibility"] == "ELIGIBLE" and pp2["behavior_verdict"] == "PASS"
    old_by_name = {p["name"]: p for p in original_baseline["processes"]}
    blocked_reason_reconciliation = []
    for process in baseline["processes"]:
        if process["name"] != "ProteinProcessingII":
            assert process["findings"] == old_by_name[process["name"]]["findings"], process["name"]
            old_eligibility = old_by_name[process["name"]]["eligibility"]
            assert (process["eligibility"] == "ELIGIBLE") == (old_eligibility == "ELIGIBLE"), process["name"]
            if process["eligibility"] != old_eligibility:
                blocked_reason_reconciliation.append({
                    "process": process["name"], "previous": old_eligibility,
                    "current": process["eligibility"], "both_remain_blocked": True})
    honest = pre_l25_honesty.audit_baseline(baseline_path)
    assert honest.integrity_ok and honest.eligible_count == 5 and honest.blocked_count == 23
    assert honest.process_count == 28
    assert honest.source_digest == "debfe45f9fbc1b3dd23ab5cfc352b340b1bf662762c338574466e3bea679c808"
    assert honest.source_file_count == 140
    audit_path = ROOT / "docs/phase_f/audits/ProteinProcessingII_semantic_audit.md"
    current_audit = audit_path.read_text().split("## Deliberate Action Prefix v2")[0]
    assert "Current independent acceptance - 2026-10-19" in current_audit
    assert all(finding in current_audit for finding in expected_ids)
    assert "historical" in current_audit and "active-window" in current_audit

    save("integration_measurements.json", {
        "candidate_head": CANDIDATE_HEAD,
        "reviewed_runtime_head": "65df71c26553f42dd95759b948de42647987bf68",
        "runtime_diff_paths": [],
        "publication_journals_not_runtime": snap["publication_journals_excluded"],
        "committed_and_current_byte_equality": "40/40 PASS",
        "recorded_receipt_hashes_verified": len(recorded_hashes),
        "strict_pp2_row": strict,
        "portable_index": {
            "sha256": sha_bytes(index_path.read_bytes()),
            "content_hash": index["content_hash"], "integrity": "OK",
            "aggregate": index["aggregate_verdict"], "tally": index["tally"],
            "all_19_fail_rows_have_stale_reasons": True,
        },
        "honesty": dataclasses.asdict(honest),
        "pp2_findings": pp2, "other_findings_and_eligible_membership_unchanged": True,
        "inherited_blocked_reason_reconciliation": blocked_reason_reconciliation,
        "full_index_and_honesty_main_commands": command_records,
        "full_index_main_reused_from_completed_same_review_stage": "--finish" in sys.argv,
        "baseline_sha256": sha_bytes(baseline_path.read_bytes()),
        "semantic_audit_sha256": sha_bytes(audit_path.read_bytes()),
        "biology_tests_or_campaigns_executed": False,
        "verdict": "ACCEPTED",
    })


if __name__ == "__main__":
    print(json.dumps({
        "started_utc": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(),
        "ppid": os.getppid(), "argv": sys.argv, "executable": sys.executable,
        "opencell_file": opencell.__file__, "cwd": str(ROOT),
    }), flush=True)
    main()
    print(json.dumps({"finished_utc": datetime.now(timezone.utc).isoformat(),
                      "pid": os.getpid(), "verdict": "ACCEPTED"}), flush=True)
