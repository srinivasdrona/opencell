# PP2 independent publication-integration check

## INTENT

Accept or reject only the committed PP2 integration at `c3ec943df61e485c0f50a3f770f85fdb5eae2cd1`. Verify native Git committed bytes and current filesystem against the exact original accepted 32 receipts and eight compact evidence files, recorded receipt hashes, unchanged runtime source, integrated PP2 strict-current-input status, portable full-index integrity, and candidate honesty integrity/four finding dispositions.

Expected: 40/40 committed and filesystem files equal the originals; all recorded receipt hashes still verify; runtime/script/test/fixture/schema diff from reviewed `65df71c26553f42dd95759b948de42647987bf68` is empty; PP2 strict row PASS; portable global index integrity OK but truthfully NON_GREEN (3 PASS/19 stale FAIL/2 MISSING); honesty audit INTEGRITY_OK, 5 eligible/23 blocked, exactly four PP2 findings RESOLVED.

Inversion: text-mode CRLF normalization could preserve readable receipts while invalidating accepted hashes; a scoped PP2 PASS could be mispublished as global PASS; or current filesystem could match while committed Git blobs differ. Compare native Git archive bytes and current files independently, preserve all earlier artifacts, and check aggregate distinctions.

PM assumption: the prior PP2 biological/evidence acceptance remains valid because runtime source is unchanged; no producer/F1 review, tests, campaign, or new H12 execution is authorized here.

## Boundaries and initial state

- Candidate: `E:\opencell-worktrees\m1-accepted-20261019`, native HEAD `c3ec943df61e485c0f50a3f770f85fdb5eae2cd1`, initial porcelain empty.
- Write only this new ignored `artifacts/m1_integration/independent_pp2/` subtree. No earlier receipt, source, evidence, index, baseline, plan, or journal changes; no commits/merge/push/nested agents.
- Original accepted evidence is read-only under the original PP2 worktree. Read only PP2 publication surfaces plus existing shared audit interfaces and aggregate output.
- Native Git inventory located 32 committed receipts under `docs/phase_f/pre_l25/acceptance/ProteinProcessingII/` and eight compact files under `docs/phase_f/l2_2_design_a/evidence_bundle/ProteinProcessingII/latest/`.
- Current semantic acceptance heading accurately preserves historical checkpoints and cites the original review. Four candidate PP2 dispositions are RESOLVED; current baseline records expected source digest `debfe45f9fbc1b3dd23ab5cfc352b340b1bf662762c338574466e3bea679c808` / 140 and truthful aggregate non-green qualification. These observations are not yet the final integrity verdict.

## Progress

Native Git archive created under this owned folder; exact native tree object IDs will independently bind its payloads to actual committed blobs. Initial overbroad source-diff probe included two append-only publication journals under `opencell/` and `data/`, and therefore returned 1. Preserved `initial_overbroad_diff_probe.json`; narrower actual runtime/input file-name check finds zero differences after explicitly excluding only those two non-runtime journal paths. This is not a runtime defect or permission to rewrite either journal.

Native receipt attributes confirm `text: unset` and `cr-at-eol`; this alone is not accepted as byte proof. Canonical WSL/local-candidate check, independent 40-file blob/filesystem/original comparison and existing audits next. No tests or biological work started.

First canonical check (Linux PID 5173 / PPID 5172, PowerShell 20772, 11:00:09.7213272Z–11:00:38.9343387Z) independently measured 40/40 committed+filesystem+original byte identity, verified all recorded receipt hashes, strict PP2 current-input PASS and 61 current input bytes. Portable full-index audit exit 0, integrity OK, NON_GREEN=3 PASS/19 FAIL/2 MISSING; honesty audit exit 0, INTEGRITY_OK, 5/28 eligible, 23 blocked, exact expected 140-file digest.

Owned script then incorrectly required identical *blocked-reason labels* for unrelated processes, instead of unchanged eligible membership plus unchanged findings and current honesty policy. DNADamage truthfully changed to BLOCKED_LOWER_GATE under stale inherited gate provenance; it was not promoted. Initial script exit 1 is preserved in `check_attempt1.log` and execution JSON. Correct only this extra unrequested assertion in the owned script, retain all actual successful audit logs/commands, and finish without repeating the full-index audit. No source/test/authority changed.

## Actual commands, environment, results

All Python execution ran from `E:\opencell-worktrees\m1-accepted-20261019` through assigned `bin\oc-py.cmd`, with relative Linux path arguments. Both check stages asserted:
- executable `/mnt/e/opencell/.venv-wsl/bin/python`;
- local candidate import `/mnt/e/opencell-worktrees/m1-accepted-20261019/opencell/__init__.py`.

### Native committed-byte proof

Actual native Windows Git commands:
```
git --no-pager rev-parse HEAD
git --no-pager status --porcelain=v1
git --no-pager ls-tree -r HEAD -- docs/phase_f/pre_l25/acceptance/ProteinProcessingII docs/phase_f/l2_2_design_a/evidence_bundle/ProteinProcessingII/latest
git --no-pager archive --format=zip --output=artifacts\m1_integration\independent_pp2\committed_pp2.zip HEAD -- docs/phase_f/pre_l25/acceptance/ProteinProcessingII docs/phase_f/l2_2_design_a/evidence_bundle/ProteinProcessingII/latest
git --no-pager diff --name-only 65df71c26553f42dd95759b948de42647987bf68 HEAD -- opencell scripts tests data bin
git --no-pager check-attr text whitespace -- docs/phase_f/pre_l25/acceptance/ProteinProcessingII/controls.xml docs/phase_f/pre_l25/acceptance/ProteinProcessingII/STATUS.md
```

`before_snapshot.json`, `native_tree.txt`, and `committed_pp2.zip` retain exact source/blob inventories. Every archive payload's Git blob object ID was independently recomputed as SHA1(`blob <size>\0<payload>`) and matched native `ls-tree`, so the archive cannot hide an export/filter rewrite. **40/40 files** then match actual current candidate filesystem **and original accepted bytes**: 32 receipts + eight bundle files. CRLF counts are preserved in the per-file report. All **11 recorded hashes** in original `report_hashes.json` independently verify against actual committed payloads. Known prior trusted STATUS/VERDICT/XML/measurement hashes also match, not just the parent's copy report.

An additional native Git archive/tree check verifies current filesystem equals committed blobs for all four publication authorities: semantic audit, baseline, full generated index, and acceptance `.gitattributes`. Report: `committed_authority_bytes.json`.

Runtime/scripts/tests/fixtures/schemas/bin committed tree matches reviewed `65df71c...`. The only differences in the deliberately broader `opencell/scripts/tests/data/bin` inventory are two append-only non-runtime publication journals; these are explicitly recorded, not suppressed as runtime changes. Native candidate and original PP2 worktrees remain clean at their respective expected tips.

### Existing strict/current and aggregate audits

Initial caller:
```
.\bin\oc-py.cmd -B artifacts/m1_integration/independent_pp2/check.py
```
PowerShell PID 20772; 11:00:09.7213272Z–11:00:38.9343387Z; Linux PID 5173. The actual successful existing audit calls from this stage are preserved unchanged:

1. `scripts.l22_evidence.generator.build_process_row(entry=ProteinProcessingII, evidence_root=docs/phase_f/l2_2_design_a/evidence_bundle, strict_input_files=True)`:
   **PASS**, green, no reasons; same seven artifact hashes as accepted bundle. Independent direct current-candidate hashing also verifies **61 inputs, 50 seed identities 0..49 + 11 runtime/fixture records**, all portable paths. Reports: `strict_current_pp2_row.json`, `candidate_current_input_bytes.json`.
2. Existing generator main:
   ```
   scripts/l22_evidence/generator.py audit --index docs/phase_f/l2_2_design_a/evidence_index.json --evidence-root docs/phase_f/l2_2_design_a/evidence_bundle
   ```
   Linux PID 5173; 11:00:15.299797Z–11:00:37.031134Z; **exit 0, integrity OK**. Aggregate truthfully **NON_GREEN: 3 PASS / 19 FAIL / 2 MISSING_EVIDENCE**. Every FAIL row retains stale provenance reason(s); no unrelated raw-data campaign or replacement of hashes. No `--require-all-pass`.
3. Existing honesty main:
   ```
   scripts/pre_l25_honesty.py audit --baseline docs/phase_f/pre_l25/PRE_L25_HONESTY_BASELINE.yaml
   ```
   Linux PID 5173; 11:00:37.046841Z–11:00:38.662106Z; **exit 0, INTEGRITY_OK, eligible=5/28, blocked=23**; actual source digest `debfe45f9fbc1b3dd23ab5cfc352b340b1bf662762c338574466e3bea679c808`, **140 files**. No require-all-eligible.

Caller initial exit 1 was solely the owned extra blocked-reason equality assertion described above, **after both real audit calls exited 0**. It was not an audit failure or hidden PP2 defect. Preserved logs: `check_attempt1.log`, `check_attempt1_execution.json`, `portable_full_index.log`, `honesty.log`, `audit_commands.json`.

Final scoped completion caller:
```
.\bin\oc-py.cmd -B artifacts/m1_integration/independent_pp2/check.py --finish
```
PowerShell PID 15144; 11:02:06.4329636Z–11:02:14.2409060Z; Linux PID 5418 / PPID 5417; **exit 0**. It re-verifies committed/current bytes and strict PP2 input binding, checks the authorities stayed byte-identical since the completed audit stage, retains original successful audit main logs without rerunning the portable full-index command, and independently validates current honesty result/dispositions. No tests, gate, producer/F1 review, biological campaign, or new H12 work was run.

## Finding/publication reconciliation

- Exactly `PPII-DEVIATIONS`, `PPII-LEGACY-OWNERSHIP`, `PPII-REPLAY-INPUT-EVIDENCE`, and `PPII-PROJECTION-GUARD-INPUTS` are present in the PP2 row; all four are **RESOLVED**.
- PP2 lower-gate result is PASS and parent-integrated eligibility is ELIGIBLE. The existing honesty evaluator confirms that integration at the current source/authority digest.
- All other processes' finding payloads and eligible membership are unchanged from the reviewed baseline. Nineteen inherited blocked reasons correctly reconcile to BLOCKED_LOWER_GATE under current stale provenance; they remain blocked, not newly promoted.
- Dated current semantic acceptance is at the top of the PP2 audit, accurately cites the original independent receipt and six-family/signal evidence, preserves the historical sections as historical, and retains the active-window-vs-birth H12 distinction.
- The stale inherited baseline source-digest integration prerequisite is now discharged: the actual recomputed current digest is the expected `debfe45...` / 140.
- The 32 original receipt files retain their source-specific original paths and results as historical execution evidence; the integrated current strict row/audit are separately verified here. Original receipt status still saying parent integration pending is not rewritten retroactively.

## Important hashes

All these refer to actual committed payload/current filesystem unless stated otherwise:
- Original accepted receipt STATUS.md: `11346d1e950d57f60e286883e8fb7101115469a122a2b64088381cbb59a5bb6a`
- Original accepted receipt VERDICT.json: `9480b2eb6510962261aa189da7063e912564c026e076afa524f02c431c82c7e7`
- Original 56-test XML (not rerun): `46cc7d226917f39782ba28de945e2233525c8e92c2dc99466759a7160d86e24e`
- Published PP2 result.json: `3a16afc784b237355aad4bb8b8c9713b55faeb9bdca80a7343dec48fd7c607fa`
- Published PP2 input_manifest.json: `e60f6fe898c881b3ce42c124b95352db2572a5cdebd414010553ffcb965beec5`
- Published PP2 completion sentinel: `857707ba31c689086b0a8c9b9c03e88302c4173dd4814dbe7cb5a0d402626a19`
- Candidate semantic audit: `ba8b1423b09c3c49ebbca752cae6e1abb2e431bf6bb26643fd87a7fcfccac90b`
- Candidate baseline file: `6e10d433cb6851bbdcc9f5ae291d710b260a57a9585a2cde1bfcb53c77688bb4`
- Candidate global index file: `5c567b8919259313bd1b35f317abfcaf6b9b69a1b270d9e35227086490739ddc`
- Global index canonical content hash: `74486dded507a7118f30339ada7eee96b5f61097e1b8ff4dd23e49a1af6d73b6`
- Independent committed/current/original byte proof: `committed_and_filesystem_preservation.json`, SHA256 `75f27fc32cf8122d810f3d89dfe61d1efb574c3eea504f45c213b93abf5e5f25`
- Independent completed measurements: `integration_measurements.json`, SHA256 `ab948f23b29e35e469e9a4cb563ada5c2e085ada76f7cfe0914264672426d654`

## VERIFICATION

Expected vs actual: 40 exact original committed/filesystem copies -> **40/40 PASS**; recorded receipt hashes -> **11/11 PASS**; unchanged runtime -> **zero runtime differences**; strict current PP2 row -> **PASS/no reasons**; portable full-index -> **integrity OK/NON_GREEN 3/19/2**; honesty -> **INTEGRITY_OK 5 eligible/23 blocked**, correct actual 140-file digest; exactly four accepted PP2 findings -> **four RESOLVED**.

Inversion checks: native Git blob OIDs plus three-way byte comparison disprove CRLF or Git-vs-filesystem receipt drift; explicit NON_GREEN index and unchanged unrelated eligible membership disprove scoped-to-global promotion; current source/authority hashes and strict 61-input checks disprove stale-source publication. Historical receipt bytes remain unchanged, including original honest limitations and failed setup attempts.

**Verdict: ACCEPTED for committed PP2 publication integration at `c3ec943df61e485c0f50a3f770f85fdb5eae2cd1`.**

No remaining PP2 publication-integration defect reproduced. Parent can preserve this verdict and mark PP2 persistently done on this isolated candidate. This is not a global all-process PASS, canonical-main eligibility update, merge, or push. All review command shells have completed; no helpers left running. Verification result: **matched**.
