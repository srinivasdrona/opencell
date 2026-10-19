import sys
sys.dont_write_bytecode = True
from integration_common import *
import shutil

event("final_sealed_integration_verdict_start")
bytes_proof = load(OUT / "committed_byte_proof.json")
batch = (OUT / "native_blob_batch.bin").read_bytes()
cursor = 0
blob_records = []
for record in bytes_proof["records"]:
    end = batch.index(b"\n", cursor)
    oid, kind, count = batch[cursor:end].decode("ascii").split()
    assert kind == "blob" and oid == record["native_git_blob_oid"]
    length = int(count)
    content = batch[end + 1:end + 1 + length]
    assert len(content) == length and batch[end + 1 + length:end + 2 + length] == b"\n"
    cursor = end + 2 + length
    sha256 = hashlib.sha256(content).hexdigest()
    assert hashlib.sha1(f"blob {length}\0".encode() + content).hexdigest() == oid
    assert sha256 == record["committed_sha256"] == record["current_sha256"] == record["original_sha256"]
    assert content == (ROOT / record["path"]).read_bytes() == Path(record["original"]).read_bytes()
    blob_records.append({"path": record["path"], "oid": oid, "bytes": length,
                         "native_cat_file_sha256": sha256,
                         "native_blob_archive_current_original_equal": True})
assert cursor == len(batch) and len(blob_records) == 77
save("actual_native_blob_proof.json", {
    "sealed_tip": HEAD, "matched": 77, "records": blob_records,
    "batch_sha256": sha(OUT / "native_blob_batch.bin"),
    "native_command": load(OUT / "native_blob_batch_command.json")})
preserved = load(OUT / "preservation_after.json")
native = load(OUT / "native_postflight.json")
assert preserved["files"] == 3803 and not preserved["changes"]
assert native["candidate_head"] == HEAD and not native["candidate_status"] and not native["candidate_diff"]
assert native["original_head"] == "65df71c26553f42dd95759b948de42647987bf68" and not native["original_status"]
tests = load(OUT / "publication_test_result.json")
assert (tests["tests"], tests["errors"], tests["failures"], tests["skipped"]) == (4, 0, 0, 0)
assert tests["exit_code"] == 0 and not tests["input_constants_modified"]
audits = load(OUT / "structured_audit_results.json")
preservation = load(OUT / "finding_and_unrelated_preservation.json")
closure = load(OUT / "current_PT_source_input_closure.json")
assert all(r["mechanical_verdict"] == "PASS" and not r["reasons"]
           for r in closure["strict_current_rows"].values())
assert audits["portable_full_index"]["ok"] and audits["honesty_baseline"]["integrity_ok"]
assert len(preservation["current_eligible"]) == 6
verdict = {
    "schema": "independent-pt-sealed-integration-v1",
    "completed_at": now(),
    "verdict": "ACCEPTED",
    "candidate": {
        "worktree": r"E:\opencell-worktrees\m1-accepted-20261019",
        "branch": "integrate/m1-accepted-20261019",
        "sealed_tip": HEAD,
        "publication_commit": "e372a5b158b27b42ad94f2c1065a1867d4fb58da",
        "pre_PT_comparison_commit": preservation["comparison_base"],
        "original_approved_runtime": "65df71c26553f42dd95759b948de42647987bf68",
    },
    "scope": "Final committed copy/publication/finding integration only; earned producer/F1/mechanics and original full evidence acceptance reused, not reopened.",
    "findings": {
        "PTRANS-COMPLETE-ATTESTATION": {
            "verdict": "ACCEPTED", "committed_baseline_disposition": "RESOLVED",
            "proof": "Exact native Git cat-file/archive/current/original equality for69receipt+8compact payloads;18manifest hashes;64current consumed input hashes and embedded50seed/M100 identities;12current source hashes,7sidecar hashes and COMPLETE sentinel; four original tests pass on actual tracked publication.",
            "evidence": ["actual_native_blob_proof.json", "committed_byte_proof.json",
                         "current_PT_source_input_closure.json", "publication.xml",
                         "finding_and_unrelated_preservation.json"]},
        "PTRANS-SAMPLE-ISOLATION": {
            "verdict": "ACCEPTED", "committed_baseline_disposition": "RESOLVED",
            "proof": "Original independently accepted owner-isolation/persistent-replay receipts are committed byte-identically, current source/control hashes match frozen65, and baseline's matching committed resolving proof is correct. No owner or biological test rerun needed or performed.",
            "evidence": ["actual_native_blob_proof.json", "committed_byte_proof.json",
                         "current_PT_source_input_closure.json",
                         "finding_and_unrelated_preservation.json"]},
    },
    "byte_proof": {
        "native_blob_archive_current_original_matches": 77,
        "receipt_files": 69, "compact_files": 8, "delivery_manifest_matches": 18,
        "native_git_cat_file_binary_stream_verified": True,
        "native_git_cat_file_command": load(OUT / "native_blob_batch_command.json"),
        "sealed_archive_sha256": sha(OUT / "sealed_payloads.tar"),
        "pre_PT_archive_sha256": sha(OUT / "pre_pt_payloads.tar"),
        "original_evidence_acceptance_verdict_sha256": sha(RECEIPTS / "VERDICT.json"),
        "published_result_sha256": sha(PT / "result.json"),
        "published_manifest_sha256": sha(PT / "input_manifest.json"),
        "published_sentinel_sha256": sha(PT / "sweep_provenance.json"),
    },
    "source_and_input_closure": closure,
    "original_publication_tests": tests,
    "audit_results": audits,
    "prior_preservation_and_eligibility": preservation,
    "native_postflight": native,
    "filesystem_preservation": preserved,
    "commands": {
        "ledger": "commands.jsonl", "native_wrapper_ledger": "native_commands.log",
        "audits": load(OUT / "audit_commands.json")},
    "narrow_real_integration_defects": [],
    "limitations_and_observations": [
        "No fresh N50 biological gate,27-test producer loop, isolation/replay rerun, calibration, H12 campaign, generic F1 review, or new numerical waiver.",
        "Original producer sentinel keeps its truthful65df71c execution SHA, not the docs-only sealed integration SHA; source/content closure is unchanged and independently matches.",
        "The full index remains expected NON_GREEN:4PASS18inheritedstale-sourceFAIL2MISSING; honesty6eligible22blocked. These are not new biological failures.",
        "Historical bug-location citations remain in the newly resolved finding lists; the matching new committed ACCEPTED proof spans and current source/control hashes supply closure. Older resolved finding payloads and semantic original prefix are unchanged.",
        "The first artifact proof-driver attempt over-required a finding heading inside a partial JSON citation. Corrected only that new verifier to check the matching proof payload and ACCEPTED state; original code/tests/receipts were never altered. Initial failure log retained.",
        "69 original root receipts are published. Original review's8nested regenerated_bundle duplicates are not part of that69; the same8compact evidence bytes are separately published and fully checked.",
        "All new writes are confined to artifacts/m1_integration/independent_pt. Both worktrees remain native-Git clean. No commit/merge/push/nested agent.",
    ],
    "parent_next_action": "Persist this final verdict against the exact sealed candidate, then mark PT committed integration DONE. No further PT producer/evidence rerun or generic review is requested. Main merge/push is not authorized by this verdict.",
}
save("VERDICT.json", verdict)
summary = f"""
## VERIFICATION — final committed integration ACCEPTED

**ACCEPTED for exact sealed candidate `{HEAD}`**, branch `integrate/m1-accepted-20261019`, publication `e372a5b158b27b42ad94f2c1065a1867d4fb58da`.

- PTRANS-COMPLETE-ATTESTATION: ACCEPTED; committed disposition RESOLVED.
- PTRANS-SAMPLE-ISOLATION: ACCEPTED; committed disposition RESOLVED.
- Direct native Git `cat-file --batch` binary payloads, native Git archive, current tracked files and accepted original bytes agree77/77:69review root receipts plus8compact files. All18original delivery-manifest hashes verify. Attributes alone were not used as proof. Full paths/OIDs/SHA256s are in actual_native_blob_proof.json and committed_byte_proof.json.
- Current strict PT input/source closure:64records=50private accepted seed inputs+14runtime records; all hashes and embedded seed0..49/M100 identities match original accepted descriptors. All12source hashes,7sidecar hashes,8compact files and original COMPLETE sentinel bind unchanged. The sentinel truthfully retains producer SHA65df71c, not a fabricated integration execution SHA.
- Existing strict PT and PP2 rows:PASS/green/reasons[]. No new biology or score claim is made.
- Fresh **only four original publication assertions** on actual tracked `docs/phase_f/l2_2_design_a/evidence_bundle/ProteinTranslocation/latest`:4passed/0failed/0errors/0skips/0xfails. No custom plugin or input retargeting. Test source SHA256 `{tests['original_source_sha256']}`; XML `publication.xml`, SHA256 `{tests['xml_sha256']}`. Exact pytest argv and PID371/times are in publication_test_result.json and commands.jsonl.
- Existing full portable generator audit explicitly against tracked bundle:integrityOK, aggregateNON_GREEN,4PASS18FAIL2MISSING; exit0. Existing honesty audit:INTEGRITY_OK,6eligible/28,22blocked; exit0. Child PIDs387/476 with exact commands/times/log hashes in audit_commands.json.
- Actual eligible members: {", ".join(preservation["current_eligible"])}. These are the original4 plus PP2 plus PT.
- Comparison base is pre-PT `{preservation['comparison_base']}`, not old65. All198unrelated compact blobs,58PP2receipt blobs,PP2semantic/baseline/index row,27unrelated process baseline payloads are unchanged. Both older PT resolved payloads PTRANS-STAGE2-ALGORITHM/PTRANS-GENUINE-EVIDENCE are identical. Only the2new PT findings changed; dated semantic acceptance is append-only so old citation lines did not shift.
- Baseline digest current and matching:`{closure['actual_baseline_source_digest']}` /140dependencies. Runtime/scripts/tests/fixtures/schema/bin match65; only allowed provenance journals differ within those tree prefixes.
- Preservation before/after:3803files/616303282bytes,0hash/size/mtime changes. Candidate and original PT worktrees remain native Git clean at their exact tips. All bounded subprocesses finished; no agents were launched.

### Inversion checks and limits
Committed-vs-filesystem fiction excluded by actual cat-file payloads and archive/current/original four-way equality. Wrong-test-root fiction excluded by unchanged original source, no custom plugins and observed actual tracked constants. Unrelated/old finding mutation excluded against058fa1b, including original resolved payloads and semantic byte-prefix preservation.
No N50/27-test loop, new calibration/H12 campaign, owner reset, generic producer/F1 review, code/source/test/publication/index/baseline/plan/journal write or commit/merge/push occurred. Prior independent full-evidence limitations, including absent original full OC tensors, remain unchanged in the byte-identical committed receipt.

**VERDICT: matched — final PT committed integration ACCEPTED.**
Parent may persist this sealed-tip verdict and mark PT done; no main merge/push is authorized.
"""
with (OUT / "STATUS.md").open("a") as stream:
    stream.write(summary)
text = (OUT / "STATUS.md").read_text().replace(
    "State: STARTING — exact sealed candidate", "State: COMPLETE — ACCEPTED for exact sealed candidate", 1)
(OUT / "STATUS.md").write_text(text)
shutil.rmtree(OUT / "scratch")
files = [
    "VERDICT.json", "actual_native_blob_proof.json", "native_blob_batch_command.json",
    "committed_byte_proof.json", "current_PT_source_input_closure.json",
    "finding_and_unrelated_preservation.json", "publication.xml",
    "publication_test_result.json", "structured_audit_results.json",
    "audit_commands.json", "full_portable_index_audit.log", "honesty_baseline_audit.log",
    "native_preflight.json", "native_postflight.json",
    "preservation_before.json", "preservation_after.json"]
save("DELIVERY_MANIFEST.json", {
    "sealed_tip": HEAD, "generated_at": now(),
    "files": {name: sha(OUT / name) for name in files}})
event("final_sealed_integration_verdict_complete", verdict="ACCEPTED", sealed_tip=HEAD,
      verdict_sha256=sha(OUT / "VERDICT.json"), actual_native_blob_matches=77,
      tests=4, preservation_changes=0, children_running=0)
