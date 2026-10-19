import sys
sys.dont_write_bytecode = True
from review_common import *
import shutil
import xml.etree.ElementTree as ET

event("independent_verdict_finalization_start")
preservation = load(OUT / "preservation_after.json")
assert preservation["files"] == 3649 and not preservation["changes"] and not preservation["new_prior_outputs"]
native = load(OUT / "native_postflight.json")
assert native["head"] == "65df71c26553f42dd95759b948de42647987bf68"
assert not native["status"] and not native["diff_stat"]
bindings = load(OUT / "source_and_compact_bindings.json")
numeric = load(OUT / "independent_numeric_proof.json")
publication = load(OUT / "publication_proof.json")
owners = load(OUT / "actual_owner_controls.json")
legacy = load(OUT / "legacy_contiguous_actual_owner.json")
integration = load(OUT / "parent_integration_metadata.json")
suite = ET.parse(OUT / "controls_retry1.xml").getroot().find("testsuite")
assert suite is not None
assert (suite.get("tests"), suite.get("errors"), suite.get("failures"), suite.get("skipped")) == ("27", "0", "0", "0")
testcases = [{"classname": t.get("classname"), "name": t.get("name"),
              "time_s": t.get("time"), "outcome": "PASS"} for t in suite.findall("testcase")]
sample_cases = [t for t in testcases if t["classname"].endswith(".test_protein_translocation_sample_isolation")]
pub_cases = [t for t in testcases if t["classname"].endswith(".test_ptrans_published_attestation")]
replay_cases = [t for t in testcases if t["classname"].endswith(".test_karr_protein_translocation_l2_replay")]
assert len(sample_cases) == 2 and len(pub_cases) == 4 and len(replay_cases) == 1
assert owners["six_distinct_execution_owners"] and owners["same_key_repeat_interleave_exact"]
assert legacy["single_persistent_owner"] and legacy["every_rng_transition_contiguous"]
assert publication["owned_row"]["green"] and not publication["owned_row"]["reasons"]
assert numeric["mechanical_verdict"] == "PASS"
source_paths = [
    "tests/scripts/test_ptrans_published_attestation.py",
    "tests/vivarium/test_protein_translocation_sample_isolation.py",
    "tests/vivarium/test_karr_protein_translocation_l2_replay.py",
    "tests/vivarium/test_ptransloc_design_a_full_vector.py",
    "tests/vivarium/test_karr_protein_translocation.py",
    "tests/vivarium/test_l2_no_oracle_dependency.py",
    "tests/unit/test_karr_protein_translocation_strict_zero.py",
    "tests/vivarium/test_protein_translocation_stage2.py",
    "opencell/vivarium/karr_protein_translocation.py",
    "opencell/vivarium/protein_state.py",
    "tests/vivarium/_l2_2_design_a_runner_helpers.py",
    "tests/vivarium/l2_2_design_a_runner.py",
    "scripts/l22_evidence/generator.py",
    "scripts/l22_evidence/verdict.py",
    "scripts/l22_evidence/schema.py",
    "docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml",
]
control_hashes = {path: sha(ROOT / path) for path in source_paths}
assert control_hashes[source_paths[0]] == bindings["publication_test_original_sha256"]
xml = {"path": relative(OUT / "controls_retry1.xml"),
       "sha256": sha(OUT / "controls_retry1.xml"), "tests": 27,
       "passed": 27, "errors": 0, "failures": 0, "skipped": 0, "xfails": 0}
parent_actions = [
    {
        "action": "Verify accepted source closure before integration",
        "instruction": "Use native Windows Git and canonical WSL/local imports in the destination. Compare all12 scoped source/contract hashes in source_and_compact_bindings.json. New actual source drift requires honest new validation or reviewed re-attestation; do not refresh old hashes. No generic mechanics/F1 re-review is requested."
    },
    {
        "action": "Publish exact candidate bytes",
        "from": "artifacts/m1_cohort/m1_pt/evidence_bundle/ProteinTranslocation/latest",
        "to": "docs/phase_f/l2_2_design_a/evidence_bundle/ProteinTranslocation/latest",
        "instruction": "Copy exactly the eight named files/hash values in candidate_compact_files. Verify every destination hash against this receipt. Preserve unknown runner git_sha, native sweep git_sha, timestamps, scores, thresholds and normalized input paths verbatim. Preserve original raw/local and old evidence in history; no hash laundering."
    },
    {
        "action": "Verify integrated publication",
        "instruction": "After byte-identical copy, run the four original tests without the review retargeting plugin and the two sample-isolation tests through destination bin wrappers with fresh own scratch parents and XML. Regenerate/audit the GLOBAL index from the explicit integrated COMPLETE bundle using existing generator, strict --verify-input-files locally and default portable mode. Do not replace the global24-row index with this scoped1PASS/23MISSING candidate index, and do not assert all-green for unrelated rows.",
        "commands_from_destination_cwd": [
            r".\bin\oc-pytest.cmd tests/scripts/test_ptrans_published_attestation.py tests/vivarium/test_protein_translocation_sample_isolation.py -q -rsxX -p no:cacheprovider --basetemp=<fresh-parent-receipt>/pytest --junitxml=<fresh-parent-receipt>/integrated_pt.xml",
            r".\bin\oc-py.cmd scripts/l22_evidence/generator.py generate --out docs/phase_f/l2_2_design_a/evidence_index.json --evidence-root docs/phase_f/l2_2_design_a/evidence_bundle --verify-input-files",
            r".\bin\oc-py.cmd scripts/l22_evidence/generator.py audit --index docs/phase_f/l2_2_design_a/evidence_index.json --evidence-root docs/phase_f/l2_2_design_a/evidence_bundle --verify-input-files",
            r".\bin\oc-py.cmd scripts/l22_evidence/generator.py audit --index docs/phase_f/l2_2_design_a/evidence_index.json --evidence-root docs/phase_f/l2_2_design_a/evidence_bundle"
        ]
    },
    {
        "action": "Record bounded semantic closure, preserving prior biology adjudication",
        "path": "docs/phase_f/audits/ProteinTranslocation_semantic_audit.md",
        "instruction": "Keep the existing10 VERIFIED / zero deviation/missing claim table and prior stage2 algorithm verdict. Add the current evidence/publication acceptance receipt, complete64-input/50seed/4fixture closure, full2892 projection, real sample-owner and persistent replay receipts. Explicitly retain the absent-full-OC-tensor, scalar-rescore/Karr-only-recalibration limitation; no new chassis or bit-identity claim from the statistical W1 score."
    },
    {
        "action": "Reconcile baseline after integrated verification",
        "path": "docs/phase_f/pre_l25/PRE_L25_HONESTY_BASELINE.yaml",
        "instruction": "Only after integrated source/copy/tests/audits pass, set PTRANS-COMPLETE-ATTESTATION and PTRANS-SAMPLE-ISOLATION to RESOLVED with current exact file/line references and this independent receipt; replace obsolete representative-only/cached-owner summaries with closure facts. Preserve PTRANS-STAGE2-ALGORITHM and PTRANS-GENUINE-EVIDENCE as RESOLVED. Retain behavior_gate=L2.2 and behavior_verdict=PASS; derive PT eligibility=ELIGIBLE only if no other applicable blocker remains. Recompute baseline summary counts, not unrelated findings.",
        "suggested_current_source_anchors": {
            "complete_input_capture": "tests/vivarium/_l2_2_design_a_runner_helpers.py:243-290",
            "final_input_drift_guard_and_manifest": "tests/vivarium/l2_2_design_a_runner.py:1485-1491",
            "fresh_sample_owner": "tests/vivarium/_l2_2_design_a_runner_helpers.py:2544-2546",
            "actual_next_update_guard": "tests/vivarium/_l2_2_design_a_runner_helpers.py:2578-2580",
            "frozen_isolation_controls": "tests/vivarium/test_protein_translocation_sample_isolation.py:12-" + str(len((ROOT / "tests/vivarium/test_protein_translocation_sample_isolation.py").read_text().splitlines())),
            "frozen_publication_controls": "tests/scripts/test_ptrans_published_attestation.py:37-" + str(len((ROOT / "tests/scripts/test_ptrans_published_attestation.py").read_text().splitlines())),
        }
    },
    {
        "action": "Refresh stale baseline source-digest metadata; parent-only integration requirement",
        "recorded": integration["baseline_source_tree"],
        "actual_at_frozen65": integration["actual_source_tree"],
        "instruction": "The baseline source_tree metadata predates the approved F1 delta. Recompute in the final integrated destination, update source_tree.sha256/file_count, then run baseline audit. This known metadata staleness is not a new PT biological rejection; do not count unrelated baseline blockers as this lane failing.",
        "commands_from_destination_cwd": [
            r".\bin\oc-py.cmd scripts/pre_l25_honesty.py source-digest",
            r".\bin\oc-py.cmd scripts/pre_l25_honesty.py audit"
        ]
    }
]
finding_common = {
    "verdict_scope": "Independent acceptance of this fresh candidate packet at frozen65; committed/publication eligibility remains parent-owned.",
    "source": native["head"],
    "command_ledger": relative(OUT / "commands.jsonl"),
    "native_command_ledger": relative(OUT / "native_commands.log"),
    "XML": xml,
}
findings = {
    "PTRANS-COMPLETE-ATTESTATION": {
        **finding_common, "verdict": "ACCEPTED",
        "proof": "All64 consumed records independently rehashed and equal fresh capture plus original preflight descriptors; all50 unique accepted-population/copy/embeddedseed identities verified; four fixture authorities and constructor actual reads covered;12 current source hashes,7 sentinel sidecars and8 compact bytes verified; N50/M100/B1000 and every5000 allocator row verified.",
        "controls": pub_cases,
        "control_source_sha256": control_hashes["tests/scripts/test_ptrans_published_attestation.py"],
        "evidence": ["all_consumed_rehashes.json", "complete_50_seed_inventory.json",
                     "accepted_population_verification.json", "constructor_authority.json",
                     "shape_activity_allocator.json", "all_descriptor_drift_rejections.json",
                     "source_and_compact_bindings.json", "sweep_time_and_command.json",
                     "independent_numeric_proof.json", "publication_proof.json",
                     "publication_commands.json", "publication_candidate_input_configuration.json"],
    },
    "PTRANS-SAMPLE-ISOLATION": {
        **finding_common, "verdict": "ACCEPTED",
        "proof": "Frozen2/2 controls pass. Actual active A=(seed0,tick2)/B=(seed1,tick2), sequence A,A,B,A,B,A:6 distinct real next_update owners begin at derived initial RNG, advance, emit nonempty changes at2 monomer coordinates each, retain full2892 output; repeated/interleaved outputs remain exact with advanced metadata and poison after/hint fields. No execution RNG reset/cache clearing. Original contiguous100tick replay observed1 owner,100 contiguous RNG transitions,20 advancingticks and13 nonempty updates; original assertions pass.",
        "controls": sample_cases + replay_cases,
        "control_source_sha256": {
            path: control_hashes[path] for path in (
                "tests/vivarium/test_protein_translocation_sample_isolation.py",
                "tests/vivarium/test_karr_protein_translocation_l2_replay.py")},
        "evidence": ["actual_owner_controls.json", "actual_owner_outputs.npz",
                     "legacy_contiguous_actual_owner.json", "pytest_reports.json"],
    },
}
limits = [
    "No original full OC tensors retained: original full N50/M100/B1000 biological execution is accepted via frozen producer/consumption/sentinel/actual input evidence, NOT claimed independently rerun in full.",
    "This reviewer independently recalibrated full Karr-only B1000 nulls and re-scored retained measured OC raw numeric fields. Original full OC W1 cannot be recomputed from absent tensors; actual fresh biological execution here is bounded active-owner samples, existing public-input controls and original100tick contiguous replay.",
    "W1=0 is equality of empirical value distributions, not coordinate-wise bit identity. Full2892 positions were retained; no collapsed482 proxy used. The existing standalone legacy replay provides its own narrower identity assertions.",
    "No retained deterministic-convergence/H12 warning exists in this packet. No old H12 support is assumed or promoted; existing approved mechanics/stage2 biological adjudication is reused rather than generically reopened.",
    "Portable audit used the existing default non-strict mode with raw data still mounted. No physical absent-raw clone was created and no raw files were hidden/deleted.",
    "The first pytest invocation failed in DrvFS file-descriptor capture (FileNotFoundError during truncate); it is not counted as PASS. Same frozen assertions passed27/27 in fresh retry XML with -s, changing only capture/scratch/output configuration.",
    "No publication/baseline/semantic/source/test/global-index/plan/journal edits, commits, nested agents, merge or push were performed. Parent owns persistent integrated eligibility.",
]
verdict = {
    "schema": "independent-ptrans-candidate-acceptance-v1",
    "completed_at": now(), "role": "NEW independent evidence/publication verdict owner",
    "result": "ACCEPTED", "source_head": native["head"],
    "worktree": r"E:\opencell-worktrees\m1-pt-20261017",
    "findings": findings,
    "preserved_resolved_findings": ["PTRANS-STAGE2-ALGORITHM", "PTRANS-GENUINE-EVIDENCE"],
    "implementation_or_F1_reopened": False,
    "stage_tuple": {"code_reviewed": "EXISTING APPROVED", "gate_measured": "PASS",
                    "candidate_bundled": "COMPLETE", "independent_accepted": "ACCEPTED",
                    "committed_eligibility": "PENDING_PARENT_BYTE_IDENTICAL_PUBLICATION_AND_BASELINE"},
    "catalog": {"N": 50, "seeds": list(range(50)), "M": 100, "B": 1000,
                "primary_channel": "monomers", "full_width": 2892,
                "raw_per_tick_shape": [6, 482]},
    "consumed_count": 64, "oracle_count": 50, "runtime_count": 14,
    "fixture_count": 4, "all_allocator_seed_ticks_verified": 5000,
    "actual_oracle_activity": load(OUT / "shape_activity_allocator.json")["activity"],
    "numeric_proof": numeric,
    "source_contract_hashes": bindings["source_hashes"],
    "control_and_module_sha256": control_hashes,
    "candidate_compact_files": bindings["files"],
    "candidate_index_sha256": bindings["candidate_index_sha256"],
    "candidate_generation_and_audits": publication,
    "fresh_test_result": xml, "all_frozen_test_cases": testcases,
    "publication_configuration": load(OUT / "publication_candidate_input_configuration.json"),
    "publication_commands": load(OUT / "publication_commands.json"),
    "original_sweep_execution": load(OUT / "sweep_time_and_command.json")["job"],
    "environment": load(OUT / "environment.json"),
    "native_postflight": native,
    "preservation": preservation,
    "limitations": limits,
    "parent_publication_instructions": parent_actions,
    "no_known_applicable_PT_gap_remains_in_reviewed_candidate_packet": True,
}
save("VERDICT.json", verdict)
save("control_test_mapping.json", {
    "xml": xml, "all_testcases": testcases, "findings": findings,
    "test_and_source_hashes": control_hashes})
body = f"""
## VERIFICATION — independent verdict COMPLETE

- **PTRANS-COMPLETE-ATTESTATION: ACCEPTED.**
- **PTRANS-SAMPLE-ISOLATION: ACCEPTED.**
- Frozen source: `{native['head']}`; native tracked status/diff remain empty.
- Candidate source: `artifacts/m1_cohort/m1_pt/evidence_bundle/ProteinTranslocation/latest` (not the old tracked PT publication).
- Original doer sweep: 2026-10-19T10:19:44.791961Z to11:37:30.731084Z,4665.939118697001 seconds; sweepPID823/runnerPID831, nativeSHA65; final COMPLETE sentinel11:37:42.065907Z. This review inspected that real command/timing/consumption receipt, did not run a second full biological sweep.
- Predicted versus actual: N50 seeds0..49, M100, B1000, raw monomer[6,482], full projected[50,100,2892],64 consumed records (50oracle+14runtime),4fixture authorities,12source/contract hashes,7sentinel-bound sidecars and8compact candidate/live/regenerated files: all matched.
- Actual oracle monomer activity:759/5000 seed-ticks,1726 changed coordinates, every seed active. Substrate activity:759 seed-ticks/4197 changed coordinates. All5000 allocator summary rows match actual before vectors.
- Every accepted-population/copy/embeddedseed identity verified, every consumed path rehashed, and64 deliberately wrong descriptor hashes rejected without input mutation. Constructor actualreads and independent PT/TOA protein authority plus MacromolecularComplexation/RibosomeAssembly complex union verified.
- Original numeric fields re-scored: monomer W1=0, independently recalibrated q95=0.0006345193637621023, threshold1; substrate W1=0.005714285714285714, independent q95=71853.90085285714, threshold143707.8017057143. Both SEED_NOISE; mechanical PASS/no reasons/warnings. Recalibration matches retained values within floating-point arithmetic precision; no threshold/sample/RNG changes.
- Fresh controls: **27passed/0failed/0errors/0skipped/0xfail**; canonical WSL pytestPID395. XML `{xml['path']}`, SHA256 `{xml['sha256']}`. Exact selectors/time/PID are in commands.jsonl, controls_retry1.log and control_test_mapping.json.
- Four original publication assertions pass after changing **only** their module EVIDENCE_ROOT/BUNDLE constants to the explicit new candidate. Original assertion/source bytes preserved: SHA256 `{bindings['publication_test_original_sha256']}`. Configuration receipt: publication_candidate_input_configuration.json.
- Frozen sample-isolation2/2 pass. Independent active actual-owner sequence A,A,B,A,B,A for A=(0,2),B=(1,2) used6distinct owners, initial derived RNGs,6nonempty updates/2changed coordinates each, full2892 widths, unchanged input payloads; metadata advancement and poison oracle-after/hint fields did not affect results. No execution RNG resets/cache clearing.
- Original contiguous100tick replay separately re-executed unchanged with observation:1persistent owner,100contiguous RNG transitions,20advancingticks,13nonempty updates; assertions pass. Public input/strict-zero and PT-only anti-oracle/collapsed-projection controls also pass.
- Independent generator bundle/generate/strict+portable audits:7child commands all exit0; PT PASS/green/reasons[]/warnings[],1PASS23unrelatedMISSING, aggregateNON_GREEN as expected. Strict, portable and doer-index normalized content hashes agree at `{publication['strict_portable_doer_content_hash']}`. Candidate index SHA256 `{bindings['candidate_index_sha256']}`.
- Preservation:3649original files /612881722bytes snapshotted before controls, then hashes/sizes/mtimes rechecked:0changes,0new prior outputs. Includes tracked source/tests/docs/baseline/globalindex and original local inputs/raw/candidate/prior lane outputs. See preservation_before.json, preservation_after.json and native pre/postflight.
- Every bounded reviewer command has finished; no agents/services/long-running work were launched.

### Inversion disposition
1. Wrong publication: excluded by explicit constant retarget receipt, all4original assertions and8original-candidate/live/fresh-bundle hash equalities.
2. Collapsed/no-op evidence: excluded by raw6x482/all2892 equality, all50seed activity and active public-owner outputs, plus frozen collapse canary.
3. Finalization hash laundering: no input/source/evidence metadata was rewritten. Original load-time descriptor set equals current/fresh captures; all64bytes and12source hashes match, original real sweep timings/nativeSHA/COMPLETEsidecars are linked. This is bounded receipt verification, not direct observation of the earlier biological run.
4. Cached-owner state hidden by resets: excluded by six actual fresh execution owner identities/initial stream hashes with advanced metadata and repeated/interleaved results; no reset/cache-clear operation. Original contiguous replay separately proves one persistent owner/RNG chain.
5. Wrong imports: excluded by canonical `/mnt/e/opencell/.venv-wsl/bin/python` and LOCALworktree module paths in environment.json; native Windows Git only.
6. Self-grading: this verdict is independent of the doer's report, but does NOT edit committed eligibility/publication. Parent must complete byte-identical integration and baseline reconciliation.

### Meaningful limitations
""" + "\n".join("- " + item for item in limits) + """

### Parent integration contract
See VERDICT.json `parent_publication_instructions` for exact destination paths, commands and current source anchors.
Publish only the8byte-identical PT candidate files, verify original publication tests against the integrated copy, regenerate/audit the full global index explicitly from the integrated bundle without replacing unrelated rows, and record semantic/baseline closure. Preserve PTRANS-STAGE2-ALGORITHM and PTRANS-GENUINE-EVIDENCE as RESOLVED and all10VERIFIED semantic claims.
Current baseline source digest metadata is stale after the approved F1 delta: recorded `be95a0b307b08590de24a760183a631d37b96e490526016e17666de72e46809e` /140files versus actual frozen65 `2b78bca95460efce2451e23b6f8f9b30fefaec24604297dae33485d13faa2ecc` /140files. Parent must recompute at final integration; this is not a new PT biological rejection.
Stage tuple: code-reviewed=existingAPPROVED / gate-measured=PASS / candidate-bundled=COMPLETE / independent-accepted=ACCEPTED / committed-eligibility=PENDING_PARENT_PUBLICATION.

**VERDICT: matched — both requested PT candidate findings ACCEPTED.**
"""
with (OUT / "STATUS.md").open("a") as stream:
    stream.write(body)
text = (OUT / "STATUS.md").read_text()
text = text.replace("State: STARTING. Independent evidence/publication verdict, not implementation review.",
                    "State: COMPLETE — both requested findings ACCEPTED for the frozen candidate. Parent publication/eligibility pending.", 1)
(OUT / "STATUS.md").write_text(text)
shutil.rmtree(OUT / "scratch")
immutable_proofs = [
    "VERDICT.json", "control_test_mapping.json", "controls_retry1.xml",
    "all_consumed_rehashes.json", "complete_50_seed_inventory.json",
    "accepted_population_verification.json", "constructor_authority.json",
    "source_and_compact_bindings.json", "independent_numeric_proof.json",
    "publication_proof.json", "publication_commands.json", "actual_owner_controls.json",
    "legacy_contiguous_actual_owner.json", "preservation_before.json", "preservation_after.json",
    "native_preflight.json", "native_postflight.json", "catalog_entry_verbatim.txt",
]
save("REVIEW_DELIVERY_MANIFEST.json", {
    "generated_at": now(), "files": {name: sha(OUT / name) for name in immutable_proofs}})
event("independent_verdict_complete", findings={k: v["verdict"] for k, v in findings.items()},
      verdict_sha256=sha(OUT / "VERDICT.json"), preservation_changes=0,
      scratch_cleanup="only own review scratch removed", children_running=0)
