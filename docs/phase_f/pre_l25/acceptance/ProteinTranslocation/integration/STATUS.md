# Independent PT committed-integration check

State: COMPLETE — ACCEPTED for exact sealed candidate `f87ebf1939a0a172a13f3d15c2ede0af0a3bca95`.
Scope: bounded committed copy/publication integration only; earned producer/F1/mechanics/evidence acceptance is not reopened.
All writes restricted to this NEW ignored subtree. No commits, merges, pushes, agents, old receipt edits, or gate reruns.

## INTENT
Verify actual committed native Git blob/archive/current/original byte identity, current strict PT64-input/source/sentinel closure, four unmodified publication assertions on the actual tracked bundle, explicit portable full-index and honesty audits, and exact PT/PP2/unrelated preservation.
Expected:77/77 original committed PT payload matches (69review receipts+8compact files),18delivery-manifest hashes valid, PT/PP2 strict PASS/no reasons, full index integrityOK/NON_GREEN4PASS18FAIL2MISSING, honesty integrityOK6eligible22blocked, only the two new PT findings resolved, prior payloads preserved against058fa1b.
Inversion: filesystem copies differ from committed Git blobs, test input root is silently retargeted, or unrelated/prior-resolved findings are changed while a row appears green.
PM sanity-check: this is final sealed integration acceptance only; original full biological execution and prior27-test acceptance are reused, not rerun or relabeled as new evidence.

## Surfaces
Read-only: native Git metadata/archives; current tracked PT publication and committed receipt directory; original PT independent_acceptance subtree; prior integration058fa1b/publicatione372a5b; current source/fixtures/private inputs/index/baseline/semantic audit.
Write-only: artifacts/m1_integration/independent_pt/**, including logs, scripts, archives, hash proofs and XML.

## VERIFICATION
PENDING. Commands/times/PIDs will be recorded as executed.

Proof-driver correction (not a candidate change): its first attempt demanded that a cited partial JSON range repeat the finding-key heading. The sample-isolation range starts inside that finding object and contains its exact matching ACCEPTED proof. The artifact-only driver now verifies that actual matching proof and verdict payload rather than requiring a heading outside the cited range. Original candidate/source/test assertion bytes are untouched; the failed initial driver log remains preserved.

## preservation_before_start
```json
{
  "at": "2026-10-19T12:35:13.889665+00:00",
  "pid": 481,
  "cwd": "/mnt/e/opencell-worktrees/m1-accepted-20261019",
  "argv": [
    "artifacts/m1_integration/independent_pt/preservation.py",
    "before"
  ],
  "stage": "preservation_before_start"
}
```

## preservation_before_complete
```json
{
  "at": "2026-10-19T12:36:16.701956+00:00",
  "pid": 481,
  "cwd": "/mnt/e/opencell-worktrees/m1-accepted-20261019",
  "argv": [
    "artifacts/m1_integration/independent_pt/preservation.py",
    "before"
  ],
  "stage": "preservation_before_complete",
  "files": 3803,
  "bytes": 616303282
}
```

## existing_audit_child_started
```json
{
  "at": "2026-10-19T12:38:49.339866+00:00",
  "pid": 362,
  "cwd": "/mnt/e/opencell-worktrees/m1-accepted-20261019",
  "argv": [
    "artifacts/m1_integration/independent_pt/run_audits.py"
  ],
  "stage": "existing_audit_child_started",
  "name": "full_portable_index_audit",
  "command": [
    "/mnt/e/opencell/.venv-wsl/bin/python",
    "scripts/l22_evidence/generator.py",
    "audit",
    "--index",
    "docs/phase_f/l2_2_design_a/evidence_index.json",
    "--evidence-root",
    "docs/phase_f/l2_2_design_a/evidence_bundle"
  ],
  "child_pid": 387,
  "started_at": "2026-10-19T12:38:49.335684+00:00"
}
```

## four_original_publication_assertions_start
```json
{
  "at": "2026-10-19T12:38:50.044700+00:00",
  "pid": 371,
  "cwd": "/mnt/e/opencell-worktrees/m1-accepted-20261019",
  "argv": [
    "artifacts/m1_integration/independent_pt/run_publication_tests.py"
  ],
  "stage": "four_original_publication_assertions_start",
  "pytest_args": [
    "tests/scripts/test_ptrans_published_attestation.py",
    "-q",
    "-s",
    "-rsxX",
    "-p",
    "no:cacheprovider",
    "--basetemp=artifacts/m1_integration/independent_pt/scratch/pytest/publication",
    "--junitxml=artifacts/m1_integration/independent_pt/publication.xml"
  ],
  "source_sha256": "3d7e27e2a220d80f6c75b75b46f49e7b3efd3ab258272d4b9cbe9a73f602e19d",
  "plugins_supplied": [],
  "input_retargeting": false
}
```

## four_original_publication_assertions_complete
```json
{
  "at": "2026-10-19T12:38:57.397134+00:00",
  "pid": 371,
  "cwd": "/mnt/e/opencell-worktrees/m1-accepted-20261019",
  "argv": [
    "artifacts/m1_integration/independent_pt/run_publication_tests.py"
  ],
  "stage": "four_original_publication_assertions_complete",
  "exit_code": 0,
  "tests": "4",
  "failures": "0",
  "errors": "0",
  "skipped": "0",
  "input_retargeting": false
}
```

## existing_audit_child_completed
```json
{
  "at": "2026-10-19T12:39:12.036002+00:00",
  "pid": 362,
  "cwd": "/mnt/e/opencell-worktrees/m1-accepted-20261019",
  "argv": [
    "artifacts/m1_integration/independent_pt/run_audits.py"
  ],
  "stage": "existing_audit_child_completed",
  "name": "full_portable_index_audit",
  "command": [
    "/mnt/e/opencell/.venv-wsl/bin/python",
    "scripts/l22_evidence/generator.py",
    "audit",
    "--index",
    "docs/phase_f/l2_2_design_a/evidence_index.json",
    "--evidence-root",
    "docs/phase_f/l2_2_design_a/evidence_bundle"
  ],
  "child_pid": 387,
  "started_at": "2026-10-19T12:38:49.335684+00:00",
  "finished_at": "2026-10-19T12:39:12.022701+00:00",
  "exit_code": 0,
  "log": "full_portable_index_audit.log",
  "log_sha256": "37d4b671f4e836a22eb45be9d47bab14a6a6f306377d57e77b932bc1c80554f7"
}
```

## existing_audit_child_started
```json
{
  "at": "2026-10-19T12:39:12.048273+00:00",
  "pid": 362,
  "cwd": "/mnt/e/opencell-worktrees/m1-accepted-20261019",
  "argv": [
    "artifacts/m1_integration/independent_pt/run_audits.py"
  ],
  "stage": "existing_audit_child_started",
  "name": "honesty_baseline_audit",
  "command": [
    "/mnt/e/opencell/.venv-wsl/bin/python",
    "scripts/pre_l25_honesty.py",
    "audit",
    "--baseline",
    "docs/phase_f/pre_l25/PRE_L25_HONESTY_BASELINE.yaml"
  ],
  "child_pid": 476,
  "started_at": "2026-10-19T12:39:12.043190+00:00"
}
```

## existing_audit_child_completed
```json
{
  "at": "2026-10-19T12:39:13.804794+00:00",
  "pid": 362,
  "cwd": "/mnt/e/opencell-worktrees/m1-accepted-20261019",
  "argv": [
    "artifacts/m1_integration/independent_pt/run_audits.py"
  ],
  "stage": "existing_audit_child_completed",
  "name": "honesty_baseline_audit",
  "command": [
    "/mnt/e/opencell/.venv-wsl/bin/python",
    "scripts/pre_l25_honesty.py",
    "audit",
    "--baseline",
    "docs/phase_f/pre_l25/PRE_L25_HONESTY_BASELINE.yaml"
  ],
  "child_pid": 476,
  "started_at": "2026-10-19T12:39:12.043190+00:00",
  "finished_at": "2026-10-19T12:39:13.788815+00:00",
  "exit_code": 0,
  "log": "honesty_baseline_audit.log",
  "log_sha256": "1119db48c4486409643fbde1a31f4baff779d52cd2d4fb8bcb0e41a40e5da5bd"
}
```

## committed_integration_proofs_start
```json
{
  "at": "2026-10-19T12:39:15.222709+00:00",
  "pid": 365,
  "cwd": "/mnt/e/opencell-worktrees/m1-accepted-20261019",
  "argv": [
    "artifacts/m1_integration/independent_pt/integration_proofs.py"
  ],
  "stage": "committed_integration_proofs_start"
}
```

## existing_integration_audits_complete
```json
{
  "at": "2026-10-19T12:39:27.084706+00:00",
  "pid": 362,
  "cwd": "/mnt/e/opencell-worktrees/m1-accepted-20261019",
  "argv": [
    "artifacts/m1_integration/independent_pt/run_audits.py"
  ],
  "stage": "existing_integration_audits_complete",
  "portable_integrity": true,
  "tally": {
    "MISSING_EVIDENCE": 2,
    "PASS": 4,
    "FAIL": 18
  },
  "aggregate": "NON_GREEN",
  "honesty_integrity": true,
  "eligible": 6,
  "blocked": 22,
  "processes": 28
}
```

## committed_integration_proofs_start
```json
{
  "at": "2026-10-19T12:40:28.034618+00:00",
  "pid": 347,
  "cwd": "/mnt/e/opencell-worktrees/m1-accepted-20261019",
  "argv": [
    "artifacts/m1_integration/independent_pt/integration_proofs.py"
  ],
  "stage": "committed_integration_proofs_start"
}
```

## committed_integration_proofs_complete
```json
{
  "at": "2026-10-19T12:40:35.299176+00:00",
  "pid": 347,
  "cwd": "/mnt/e/opencell-worktrees/m1-accepted-20261019",
  "argv": [
    "artifacts/m1_integration/independent_pt/integration_proofs.py"
  ],
  "stage": "committed_integration_proofs_complete",
  "byte_matches": 77,
  "delivery_manifest": 18,
  "consumed": 64,
  "source_hashes": 12,
  "strict_rows": {
    "ProteinTranslocation": "PASS",
    "ProteinProcessingII": "PASS"
  },
  "eligible": [
    "ChromosomeSegregation",
    "HostInteraction",
    "ProteinActivation",
    "ProteinProcessingII",
    "ProteinTranslocation",
    "TerminalOrganelleAssembly"
  ],
  "index_tally": {
    "FAIL": 18,
    "MISSING_EVIDENCE": 2,
    "PASS": 4
  },
  "preservation_base": "058fa1b5e5519a5312635a396701ea4d5c8740d9"
}
```

## preservation_after_start
```json
{
  "at": "2026-10-19T12:40:57.503509+00:00",
  "pid": 338,
  "cwd": "/mnt/e/opencell-worktrees/m1-accepted-20261019",
  "argv": [
    "artifacts/m1_integration/independent_pt/preservation.py",
    "after"
  ],
  "stage": "preservation_after_start"
}
```

## preservation_after_complete
```json
{
  "at": "2026-10-19T12:41:30.145832+00:00",
  "pid": 338,
  "cwd": "/mnt/e/opencell-worktrees/m1-accepted-20261019",
  "argv": [
    "artifacts/m1_integration/independent_pt/preservation.py",
    "after"
  ],
  "stage": "preservation_after_complete",
  "files": 3803,
  "changes": []
}
```

## final_sealed_integration_verdict_start
```json
{
  "at": "2026-10-19T12:43:59.901472+00:00",
  "pid": 384,
  "cwd": "/mnt/e/opencell-worktrees/m1-accepted-20261019",
  "argv": [
    "artifacts/m1_integration/independent_pt/finish.py"
  ],
  "stage": "final_sealed_integration_verdict_start"
}
```

## VERIFICATION — final committed integration ACCEPTED

**ACCEPTED for exact sealed candidate `f87ebf1939a0a172a13f3d15c2ede0af0a3bca95`**, branch `integrate/m1-accepted-20261019`, publication `e372a5b158b27b42ad94f2c1065a1867d4fb58da`.

- PTRANS-COMPLETE-ATTESTATION: ACCEPTED; committed disposition RESOLVED.
- PTRANS-SAMPLE-ISOLATION: ACCEPTED; committed disposition RESOLVED.
- Direct native Git `cat-file --batch` binary payloads, native Git archive, current tracked files and accepted original bytes agree77/77:69review root receipts plus8compact files. All18original delivery-manifest hashes verify. Attributes alone were not used as proof. Full paths/OIDs/SHA256s are in actual_native_blob_proof.json and committed_byte_proof.json.
- Current strict PT input/source closure:64records=50private accepted seed inputs+14runtime records; all hashes and embedded seed0..49/M100 identities match original accepted descriptors. All12source hashes,7sidecar hashes,8compact files and original COMPLETE sentinel bind unchanged. The sentinel truthfully retains producer SHA65df71c, not a fabricated integration execution SHA.
- Existing strict PT and PP2 rows:PASS/green/reasons[]. No new biology or score claim is made.
- Fresh **only four original publication assertions** on actual tracked `docs/phase_f/l2_2_design_a/evidence_bundle/ProteinTranslocation/latest`:4passed/0failed/0errors/0skips/0xfails. No custom plugin or input retargeting. Test source SHA256 `3d7e27e2a220d80f6c75b75b46f49e7b3efd3ab258272d4b9cbe9a73f602e19d`; XML `publication.xml`, SHA256 `4fe54bf363f534e928647a2d0a0cde12b0c2a32f3c0744492bc94a248f2581c6`. Exact pytest argv and PID371/times are in publication_test_result.json and commands.jsonl.
- Existing full portable generator audit explicitly against tracked bundle:integrityOK, aggregateNON_GREEN,4PASS18FAIL2MISSING; exit0. Existing honesty audit:INTEGRITY_OK,6eligible/28,22blocked; exit0. Child PIDs387/476 with exact commands/times/log hashes in audit_commands.json.
- Actual eligible members: ChromosomeSegregation, HostInteraction, ProteinActivation, ProteinProcessingII, ProteinTranslocation, TerminalOrganelleAssembly. These are the original4 plus PP2 plus PT.
- Comparison base is pre-PT `058fa1b5e5519a5312635a396701ea4d5c8740d9`, not old65. All198unrelated compact blobs,58PP2receipt blobs,PP2semantic/baseline/index row,27unrelated process baseline payloads are unchanged. Both older PT resolved payloads PTRANS-STAGE2-ALGORITHM/PTRANS-GENUINE-EVIDENCE are identical. Only the2new PT findings changed; dated semantic acceptance is append-only so old citation lines did not shift.
- Baseline digest current and matching:`a4694f00ef286d47283aa90605a3120030c1d700e79cf9560132bcfe50d41525` /140dependencies. Runtime/scripts/tests/fixtures/schema/bin match65; only allowed provenance journals differ within those tree prefixes.
- Preservation before/after:3803files/616303282bytes,0hash/size/mtime changes. Candidate and original PT worktrees remain native Git clean at their exact tips. All bounded subprocesses finished; no agents were launched.

### Inversion checks and limits
Committed-vs-filesystem fiction excluded by actual cat-file payloads and archive/current/original four-way equality. Wrong-test-root fiction excluded by unchanged original source, no custom plugins and observed actual tracked constants. Unrelated/old finding mutation excluded against058fa1b, including original resolved payloads and semantic byte-prefix preservation.
No N50/27-test loop, new calibration/H12 campaign, owner reset, generic producer/F1 review, code/source/test/publication/index/baseline/plan/journal write or commit/merge/push occurred. Prior independent full-evidence limitations, including absent original full OC tensors, remain unchanged in the byte-identical committed receipt.

**VERDICT: matched — final PT committed integration ACCEPTED.**
Parent may persist this sealed-tip verdict and mark PT done; no main merge/push is authorized.

## final_sealed_integration_verdict_complete
```json
{
  "at": "2026-10-19T12:44:01.066697+00:00",
  "pid": 384,
  "cwd": "/mnt/e/opencell-worktrees/m1-accepted-20261019",
  "argv": [
    "artifacts/m1_integration/independent_pt/finish.py"
  ],
  "stage": "final_sealed_integration_verdict_complete",
  "verdict": "ACCEPTED",
  "sealed_tip": "f87ebf1939a0a172a13f3d15c2ede0af0a3bca95",
  "verdict_sha256": "f4140a739d59417aa44b8fb3e33454cca954691aefd2726d0beb40bdfc219c53",
  "actual_native_blob_matches": 77,
  "tests": 4,
  "preservation_changes": 0,
  "children_running": 0
}
```
