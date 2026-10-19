# Independent ProteinTranslocation acceptance

State: COMPLETE — both requested findings ACCEPTED for the frozen candidate. Parent publication/eligibility pending.
Scope: frozen native HEAD `65df71c26553f42dd95759b948de42647987bf68`.
All writes restricted to this newly created ignored subtree. No agents, commits, publication, or source edits.

## INTENT
Independently accept or reject PTRANS-COMPLETE-ATTESTATION and PTRANS-SAMPLE-ISOLATION using actual frozen source, consumed inputs, numerical evidence and explicit candidate publication.
Contract: PROMPT_m1_pt.md deliberate-action/domain/catalog rules and current independent-owner assignment; preserve approved producer/mechanics/shared-F1 and resolved stage2algorithm/genuineevidence.
Expected outcome: N50 seeds0..49 / M100 / B1000 / full2892 projection, truthful64 consumed records, active fresh sample owners with persistent contiguous replay owners, four unmodified candidate-publication assertions, fresh strict and portable generator audits with PT PASS/no reasons and23 unrelated MISSING.
Inversions: checking old tracked publication instead of explicit candidate; collapsed/no-op projection; attaching current hashes to unconsumed historical results; owner-cache state hidden by resets; wrong worktree imports; self-grading numerical PASS as eligibility.
PM sanity-check: evidence acceptance does not itself publish or grant committed eligibility; parent owns byte-identical integration and stale baseline-source metadata repair.

## Surfaces
Read-only: PROMPT_m1_pt.md, SESSION_CONTEXT.md, STATUS_m1_pt.md, catalog, frozen PT adapters and controls, publication module, existing generator/schema/verdict and numeric evaluator, local MATLAB/fixture/oracle inputs, artifacts/l2_2_gates/ProteinTranslocation/latest, artifacts/m1_cohort/m1_pt/evidence_bundle and candidate_index_resume.json plus prior lane receipts.
Write-only: artifacts/m1_cohort/m1_pt/independent_acceptance/** (scripts, logs, XML, snapshots, independent generation/audits and verdict).

## Command ledger
Initial reads through view tool completed; no child processes. Exact native/WSL command times and PIDs will be recorded here and in commands.jsonl.
Next: native frozen/clean preflight and preservation snapshot before executing Python controls.

## VERIFICATION
PENDING. No doer claim is yet an independent verdict.

## preservation_before_start
```json
{
  "stage": "preservation_before_start",
  "at": "2026-10-19T11:47:21.604010+00:00",
  "pid": 386,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/preservation.py",
    "before"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017"
}
```

## preservation_before_complete
```json
{
  "stage": "preservation_before_complete",
  "at": "2026-10-19T11:48:50.243253+00:00",
  "pid": 386,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/preservation.py",
    "before"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "files": 3649,
  "bytes": 612881722
}
```

## independent_input_inspection_start
```json
{
  "stage": "independent_input_inspection_start",
  "at": "2026-10-19T11:50:36.909092+00:00",
  "pid": 386,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/inspect_inputs.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017"
}
```

## independent_input_inspection_complete
```json
{
  "stage": "independent_input_inspection_complete",
  "at": "2026-10-19T11:52:07.994749+00:00",
  "pid": 386,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/inspect_inputs.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "consumed": 64,
  "seeds": 50,
  "source_hashes": 12,
  "compact_files": 8,
  "activity": {
    "monomers": {
      "shape": [
        50,
        100,
        2892
      ],
      "active_seed_ticks": 759,
      "nonzero_delta_coordinates": 1726,
      "active_ticks_per_seed": [
        13,
        18,
        15,
        15,
        12,
        13,
        17,
        16,
        14,
        12,
        16,
        10,
        15,
        13,
        21,
        14,
        23,
        14,
        12,
        21,
        16,
        19,
        20,
        19,
        14,
        17,
        13,
        10,
        14,
        10,
        14,
        21,
        15,
        14,
        19,
        10,
        15,
        16,
        13,
        22,
        18,
        16,
        15,
        11,
        15,
        11,
        17,
        13,
        12,
        16
      ],
      "after_nonzero": 7680
    },
    "substrates": {
      "shape": [
        50,
        100,
        7
      ],
      "active_seed_ticks": 759,
      "nonzero_delta_coordinates": 4197,
      "active_ticks_per_seed": [
        13,
        18,
        15,
        15,
        12,
        13,
        17,
        16,
        14,
        12,
        16,
        10,
        15,
        13,
        21,
        14,
        23,
        14,
        12,
        21,
        16,
        19,
        20,
        19,
        14,
        17,
        13,
        10,
        14,
        10,
        14,
        21,
        15,
        14,
        19,
        10,
        15,
        16,
        13,
        22,
        18,
        16,
        15,
        11,
        15,
        11,
        17,
        13,
        12,
        16
      ],
      "after_nonzero": 4207
    }
  }
}
```

## fresh_frozen_controls_start
```json
{
  "stage": "fresh_frozen_controls_start",
  "at": "2026-10-19T11:53:34.329082+00:00",
  "pid": 587,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/run_controls.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "pytest_args": [
    "-q",
    "-rsxX",
    "-p",
    "no:cacheprovider",
    "--basetemp=artifacts/m1_cohort/m1_pt/independent_acceptance/scratch/pytest/controls",
    "--junitxml=artifacts/m1_cohort/m1_pt/independent_acceptance/controls.xml",
    "tests/vivarium/test_protein_translocation_sample_isolation.py",
    "tests/scripts/test_ptrans_published_attestation.py",
    "tests/vivarium/test_karr_protein_translocation_l2_replay.py",
    "tests/vivarium/test_ptransloc_design_a_full_vector.py::test_contract_1_translocation_adapter_preserves_2892_compartment_positions",
    "tests/vivarium/test_ptransloc_design_a_full_vector.py::test_contract_2_load_v2_ensemble_returns_2892_monomer_vectors",
    "tests/vivarium/test_ptransloc_design_a_full_vector.py::test_contract_3_run_protein_translocation_tick_preserves_non_authority_monomers",
    "tests/vivarium/test_ptransloc_design_a_full_vector.py::test_contract_4_planted_collapsed_sum_mutation_canary",
    "tests/vivarium/test_l2_no_oracle_dependency.py::test_l2_process_source_does_not_depend_on_replay_oracle[karr_protein_translocation.py]",
    "tests/vivarium/test_karr_protein_translocation.py",
    "tests/unit/test_karr_protein_translocation_strict_zero.py",
    "tests/vivarium/test_protein_translocation_stage2.py::test_c11_persistent_stream_and_fixture_order",
    "tests/vivarium/test_protein_translocation_stage2.py::test_canary_rejects_reseed_rng",
    "tests/vivarium/test_protein_translocation_stage2.py::test_canary_rejects_repeated_selection_stream_with_advancing_rng"
  ],
  "candidate_configuration": "ONLY publication module EVIDENCE_ROOT/BUNDLE retargeted"
}
```

## active_actual_owner_controls_start
```json
{
  "stage": "active_actual_owner_controls_start",
  "at": "2026-10-19T11:53:55.000975+00:00",
  "pid": 590,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/actual_owners.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017"
}
```

## active_actual_owner_controls_complete
```json
{
  "stage": "active_actual_owner_controls_complete",
  "at": "2026-10-19T11:54:00.938277+00:00",
  "pid": 590,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/actual_owners.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "calls": 6,
  "samples": [
    [
      0,
      2
    ],
    [
      1,
      2
    ]
  ],
  "distinct_actual_owners": 6,
  "changed_coordinates": [
    2,
    2,
    2,
    2,
    2,
    2
  ]
}
```

## fresh_frozen_controls_start
```json
{
  "stage": "fresh_frozen_controls_start",
  "at": "2026-10-19T11:55:23.321316+00:00",
  "pid": 395,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/run_controls.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "pytest_args": [
    "-q",
    "-s",
    "-rsxX",
    "-p",
    "no:cacheprovider",
    "--basetemp=artifacts/m1_cohort/m1_pt/independent_acceptance/scratch/pytest/controls_retry1",
    "--junitxml=artifacts/m1_cohort/m1_pt/independent_acceptance/controls_retry1.xml",
    "tests/vivarium/test_protein_translocation_sample_isolation.py",
    "tests/scripts/test_ptrans_published_attestation.py",
    "tests/vivarium/test_karr_protein_translocation_l2_replay.py",
    "tests/vivarium/test_ptransloc_design_a_full_vector.py::test_contract_1_translocation_adapter_preserves_2892_compartment_positions",
    "tests/vivarium/test_ptransloc_design_a_full_vector.py::test_contract_2_load_v2_ensemble_returns_2892_monomer_vectors",
    "tests/vivarium/test_ptransloc_design_a_full_vector.py::test_contract_3_run_protein_translocation_tick_preserves_non_authority_monomers",
    "tests/vivarium/test_ptransloc_design_a_full_vector.py::test_contract_4_planted_collapsed_sum_mutation_canary",
    "tests/vivarium/test_l2_no_oracle_dependency.py::test_l2_process_source_does_not_depend_on_replay_oracle[karr_protein_translocation.py]",
    "tests/vivarium/test_karr_protein_translocation.py",
    "tests/unit/test_karr_protein_translocation_strict_zero.py",
    "tests/vivarium/test_protein_translocation_stage2.py::test_c11_persistent_stream_and_fixture_order",
    "tests/vivarium/test_protein_translocation_stage2.py::test_canary_rejects_reseed_rng",
    "tests/vivarium/test_protein_translocation_stage2.py::test_canary_rejects_repeated_selection_stream_with_advancing_rng"
  ],
  "candidate_configuration": "ONLY publication module EVIDENCE_ROOT/BUNDLE retargeted"
}
```

## independent_numeric_population_start
```json
{
  "stage": "independent_numeric_population_start",
  "at": "2026-10-19T11:55:44.519080+00:00",
  "pid": 392,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/numeric_and_population.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017"
}
```

## independent_numeric_population_complete
```json
{
  "stage": "independent_numeric_population_complete",
  "at": "2026-10-19T11:55:47.906034+00:00",
  "pid": 392,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/numeric_and_population.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "calibrated_channels": [
    "substrates",
    "monomers"
  ],
  "process_verdict": "PASS",
  "thresholds": {
    "substrates": 143707.8017057143,
    "monomers": 1.0
  },
  "q95": {
    "substrates": 71853.90085285714,
    "monomers": 0.0006345193637621023
  }
}
```

## fresh_frozen_controls_complete
```json
{
  "stage": "fresh_frozen_controls_complete",
  "at": "2026-10-19T11:56:13.840138+00:00",
  "pid": 395,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/run_controls.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "exit_code": 0,
  "passed": 27,
  "skipped_or_xfail": [],
  "failures": [],
  "xml": "controls_retry1.xml",
  "publication_original_sha256": "3d7e27e2a220d80f6c75b75b46f49e7b3efd3ab258272d4b9cbe9a73f602e19d"
}
```

## independent_publication_audits_start
```json
{
  "stage": "independent_publication_audits_start",
  "at": "2026-10-19T11:57:36.525379+00:00",
  "pid": 617,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/publication_audits.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017"
}
```

## publication_child_started
```json
{
  "stage": "publication_child_started",
  "at": "2026-10-19T11:57:36.623122+00:00",
  "pid": 617,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/publication_audits.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "name": "independent_bundle",
  "command": [
    "/mnt/e/opencell/.venv-wsl/bin/python",
    "scripts/l22_evidence/generator.py",
    "bundle",
    "--source-root",
    "artifacts/l2_2_gates",
    "--bundle-root",
    "artifacts/m1_cohort/m1_pt/independent_acceptance/regenerated_bundle"
  ],
  "child_pid": 658,
  "started_at": "2026-10-19T11:57:36.618559+00:00",
  "log": "independent_bundle.log"
}
```

## publication_child_completed
```json
{
  "stage": "publication_child_completed",
  "at": "2026-10-19T11:57:37.117462+00:00",
  "pid": 617,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/publication_audits.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "name": "independent_bundle",
  "command": [
    "/mnt/e/opencell/.venv-wsl/bin/python",
    "scripts/l22_evidence/generator.py",
    "bundle",
    "--source-root",
    "artifacts/l2_2_gates",
    "--bundle-root",
    "artifacts/m1_cohort/m1_pt/independent_acceptance/regenerated_bundle"
  ],
  "child_pid": 658,
  "started_at": "2026-10-19T11:57:36.618559+00:00",
  "finished_at": "2026-10-19T11:57:37.103420+00:00",
  "exit_code": 0,
  "log": "independent_bundle.log",
  "log_sha256": "987df9017da9c68b7fe38dbb7bb9646dd7d4198f99138bf70d6de05b37a080e0"
}
```

## publication_child_started
```json
{
  "stage": "publication_child_started",
  "at": "2026-10-19T11:57:37.129498+00:00",
  "pid": 617,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/publication_audits.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "name": "independent_generate_strict",
  "command": [
    "/mnt/e/opencell/.venv-wsl/bin/python",
    "scripts/l22_evidence/generator.py",
    "generate",
    "--out",
    "artifacts/m1_cohort/m1_pt/independent_acceptance/candidate_index_strict.json",
    "--evidence-root",
    "artifacts/m1_cohort/m1_pt/evidence_bundle",
    "--verify-input-files"
  ],
  "child_pid": 659,
  "started_at": "2026-10-19T11:57:37.124248+00:00",
  "log": "independent_generate_strict.log"
}
```

## publication_child_completed
```json
{
  "stage": "publication_child_completed",
  "at": "2026-10-19T11:57:38.608822+00:00",
  "pid": 617,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/publication_audits.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "name": "independent_generate_strict",
  "command": [
    "/mnt/e/opencell/.venv-wsl/bin/python",
    "scripts/l22_evidence/generator.py",
    "generate",
    "--out",
    "artifacts/m1_cohort/m1_pt/independent_acceptance/candidate_index_strict.json",
    "--evidence-root",
    "artifacts/m1_cohort/m1_pt/evidence_bundle",
    "--verify-input-files"
  ],
  "child_pid": 659,
  "started_at": "2026-10-19T11:57:37.124248+00:00",
  "finished_at": "2026-10-19T11:57:38.589830+00:00",
  "exit_code": 0,
  "log": "independent_generate_strict.log",
  "log_sha256": "e6ea7186b9a44a7df99c205de92528797738b802f772370f6c3b9f1f2331a66a"
}
```

## publication_child_started
```json
{
  "stage": "publication_child_started",
  "at": "2026-10-19T11:57:38.620799+00:00",
  "pid": 617,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/publication_audits.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "name": "independent_audit_strict",
  "command": [
    "/mnt/e/opencell/.venv-wsl/bin/python",
    "scripts/l22_evidence/generator.py",
    "audit",
    "--index",
    "artifacts/m1_cohort/m1_pt/independent_acceptance/candidate_index_strict.json",
    "--evidence-root",
    "artifacts/m1_cohort/m1_pt/evidence_bundle",
    "--verify-input-files"
  ],
  "child_pid": 660,
  "started_at": "2026-10-19T11:57:38.615401+00:00",
  "log": "independent_audit_strict.log"
}
```

## publication_child_completed
```json
{
  "stage": "publication_child_completed",
  "at": "2026-10-19T11:57:41.168592+00:00",
  "pid": 617,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/publication_audits.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "name": "independent_audit_strict",
  "command": [
    "/mnt/e/opencell/.venv-wsl/bin/python",
    "scripts/l22_evidence/generator.py",
    "audit",
    "--index",
    "artifacts/m1_cohort/m1_pt/independent_acceptance/candidate_index_strict.json",
    "--evidence-root",
    "artifacts/m1_cohort/m1_pt/evidence_bundle",
    "--verify-input-files"
  ],
  "child_pid": 660,
  "started_at": "2026-10-19T11:57:38.615401+00:00",
  "finished_at": "2026-10-19T11:57:41.150369+00:00",
  "exit_code": 0,
  "log": "independent_audit_strict.log",
  "log_sha256": "47ea7177b520ae6558e2f1cc4daf9b2339543f545f274d21e32572e62fbc836e"
}
```

## publication_child_started
```json
{
  "stage": "publication_child_started",
  "at": "2026-10-19T11:57:41.195617+00:00",
  "pid": 617,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/publication_audits.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "name": "independent_audit_portable",
  "command": [
    "/mnt/e/opencell/.venv-wsl/bin/python",
    "scripts/l22_evidence/generator.py",
    "audit",
    "--index",
    "artifacts/m1_cohort/m1_pt/independent_acceptance/candidate_index_strict.json",
    "--evidence-root",
    "artifacts/m1_cohort/m1_pt/evidence_bundle"
  ],
  "child_pid": 664,
  "started_at": "2026-10-19T11:57:41.190300+00:00",
  "log": "independent_audit_portable.log"
}
```

## publication_child_completed
```json
{
  "stage": "publication_child_completed",
  "at": "2026-10-19T11:57:42.560717+00:00",
  "pid": 617,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/publication_audits.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "name": "independent_audit_portable",
  "command": [
    "/mnt/e/opencell/.venv-wsl/bin/python",
    "scripts/l22_evidence/generator.py",
    "audit",
    "--index",
    "artifacts/m1_cohort/m1_pt/independent_acceptance/candidate_index_strict.json",
    "--evidence-root",
    "artifacts/m1_cohort/m1_pt/evidence_bundle"
  ],
  "child_pid": 664,
  "started_at": "2026-10-19T11:57:41.190300+00:00",
  "finished_at": "2026-10-19T11:57:42.544306+00:00",
  "exit_code": 0,
  "log": "independent_audit_portable.log",
  "log_sha256": "47ea7177b520ae6558e2f1cc4daf9b2339543f545f274d21e32572e62fbc836e"
}
```

## publication_child_started
```json
{
  "stage": "publication_child_started",
  "at": "2026-10-19T11:57:42.572315+00:00",
  "pid": 617,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/publication_audits.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "name": "independent_generate_portable",
  "command": [
    "/mnt/e/opencell/.venv-wsl/bin/python",
    "scripts/l22_evidence/generator.py",
    "generate",
    "--out",
    "artifacts/m1_cohort/m1_pt/independent_acceptance/candidate_index_portable.json",
    "--evidence-root",
    "artifacts/m1_cohort/m1_pt/evidence_bundle"
  ],
  "child_pid": 665,
  "started_at": "2026-10-19T11:57:42.566883+00:00",
  "log": "independent_generate_portable.log"
}
```

## publication_child_completed
```json
{
  "stage": "publication_child_completed",
  "at": "2026-10-19T11:57:43.445784+00:00",
  "pid": 617,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/publication_audits.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "name": "independent_generate_portable",
  "command": [
    "/mnt/e/opencell/.venv-wsl/bin/python",
    "scripts/l22_evidence/generator.py",
    "generate",
    "--out",
    "artifacts/m1_cohort/m1_pt/independent_acceptance/candidate_index_portable.json",
    "--evidence-root",
    "artifacts/m1_cohort/m1_pt/evidence_bundle"
  ],
  "child_pid": 665,
  "started_at": "2026-10-19T11:57:42.566883+00:00",
  "finished_at": "2026-10-19T11:57:43.427874+00:00",
  "exit_code": 0,
  "log": "independent_generate_portable.log",
  "log_sha256": "b6dd6446b8c93771931ac6ef6390ee17ba0891bcf70a53d9493100bcef879710"
}
```

## publication_child_started
```json
{
  "stage": "publication_child_started",
  "at": "2026-10-19T11:57:43.458805+00:00",
  "pid": 617,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/publication_audits.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "name": "doer_candidate_audit_strict",
  "command": [
    "/mnt/e/opencell/.venv-wsl/bin/python",
    "scripts/l22_evidence/generator.py",
    "audit",
    "--index",
    "artifacts/m1_cohort/m1_pt/candidate_index_resume.json",
    "--evidence-root",
    "artifacts/m1_cohort/m1_pt/evidence_bundle",
    "--verify-input-files"
  ],
  "child_pid": 666,
  "started_at": "2026-10-19T11:57:43.452993+00:00",
  "log": "doer_candidate_audit_strict.log"
}
```

## publication_child_completed
```json
{
  "stage": "publication_child_completed",
  "at": "2026-10-19T11:57:45.985720+00:00",
  "pid": 617,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/publication_audits.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "name": "doer_candidate_audit_strict",
  "command": [
    "/mnt/e/opencell/.venv-wsl/bin/python",
    "scripts/l22_evidence/generator.py",
    "audit",
    "--index",
    "artifacts/m1_cohort/m1_pt/candidate_index_resume.json",
    "--evidence-root",
    "artifacts/m1_cohort/m1_pt/evidence_bundle",
    "--verify-input-files"
  ],
  "child_pid": 666,
  "started_at": "2026-10-19T11:57:43.452993+00:00",
  "finished_at": "2026-10-19T11:57:45.968030+00:00",
  "exit_code": 0,
  "log": "doer_candidate_audit_strict.log",
  "log_sha256": "47ea7177b520ae6558e2f1cc4daf9b2339543f545f274d21e32572e62fbc836e"
}
```

## publication_child_started
```json
{
  "stage": "publication_child_started",
  "at": "2026-10-19T11:57:45.998410+00:00",
  "pid": 617,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/publication_audits.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "name": "doer_candidate_audit_portable",
  "command": [
    "/mnt/e/opencell/.venv-wsl/bin/python",
    "scripts/l22_evidence/generator.py",
    "audit",
    "--index",
    "artifacts/m1_cohort/m1_pt/candidate_index_resume.json",
    "--evidence-root",
    "artifacts/m1_cohort/m1_pt/evidence_bundle"
  ],
  "child_pid": 667,
  "started_at": "2026-10-19T11:57:45.993029+00:00",
  "log": "doer_candidate_audit_portable.log"
}
```

## publication_child_completed
```json
{
  "stage": "publication_child_completed",
  "at": "2026-10-19T11:57:47.384238+00:00",
  "pid": 617,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/publication_audits.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "name": "doer_candidate_audit_portable",
  "command": [
    "/mnt/e/opencell/.venv-wsl/bin/python",
    "scripts/l22_evidence/generator.py",
    "audit",
    "--index",
    "artifacts/m1_cohort/m1_pt/candidate_index_resume.json",
    "--evidence-root",
    "artifacts/m1_cohort/m1_pt/evidence_bundle"
  ],
  "child_pid": 667,
  "started_at": "2026-10-19T11:57:45.993029+00:00",
  "finished_at": "2026-10-19T11:57:47.364909+00:00",
  "exit_code": 0,
  "log": "doer_candidate_audit_portable.log",
  "log_sha256": "47ea7177b520ae6558e2f1cc4daf9b2339543f545f274d21e32572e62fbc836e"
}
```

## independent_publication_audits_complete
```json
{
  "stage": "independent_publication_audits_complete",
  "at": "2026-10-19T11:57:48.581569+00:00",
  "pid": 617,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/publication_audits.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "stages": 7,
  "compact_regeneration_matches": 8,
  "rejected_wrong_descriptors": 64,
  "PT": "PASS",
  "aggregate": "NON_GREEN",
  "tally": {
    "MISSING_EVIDENCE": 23,
    "PASS": 1
  }
}
```

## parent_integration_metadata_start
```json
{
  "stage": "parent_integration_metadata_start",
  "at": "2026-10-19T11:59:03.736416+00:00",
  "pid": 461,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/integration_receipt.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017"
}
```

## parent_integration_metadata_complete
```json
{
  "stage": "parent_integration_metadata_complete",
  "at": "2026-10-19T11:59:04.799250+00:00",
  "pid": 461,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/integration_receipt.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "source_digest": "2b78bca95460efce2451e23b6f8f9b30fefaec24604297dae33485d13faa2ecc",
  "source_files": 140,
  "baseline_stale": true
}
```

## legacy_contiguous_actual_owner_start
```json
{
  "stage": "legacy_contiguous_actual_owner_start",
  "at": "2026-10-19T11:59:22.059664+00:00",
  "pid": 464,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/legacy_owner_receipt.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017"
}
```

## legacy_contiguous_actual_owner_complete
```json
{
  "stage": "legacy_contiguous_actual_owner_complete",
  "at": "2026-10-19T11:59:41.318126+00:00",
  "pid": 464,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/legacy_owner_receipt.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "ticks": 100,
  "distinct_owners": 1,
  "advancing_ticks": 20,
  "nonempty_updates": 13
}
```

## preservation_after_start
```json
{
  "stage": "preservation_after_start",
  "at": "2026-10-19T12:00:20.002438+00:00",
  "pid": 351,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/preservation.py",
    "after"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017"
}
```

## preservation_after_complete
```json
{
  "stage": "preservation_after_complete",
  "at": "2026-10-19T12:00:54.797915+00:00",
  "pid": 351,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/preservation.py",
    "after"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "files": 3649,
  "changes": [],
  "new_prior_outputs": [],
  "finished_at": "2026-10-19T12:00:54.786333+00:00"
}
```

## independent_verdict_finalization_start
```json
{
  "stage": "independent_verdict_finalization_start",
  "at": "2026-10-19T12:03:46.713996+00:00",
  "pid": 351,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/finish.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017"
}
```

## VERIFICATION — independent verdict COMPLETE

- **PTRANS-COMPLETE-ATTESTATION: ACCEPTED.**
- **PTRANS-SAMPLE-ISOLATION: ACCEPTED.**
- Frozen source: `65df71c26553f42dd95759b948de42647987bf68`; native tracked status/diff remain empty.
- Candidate source: `artifacts/m1_cohort/m1_pt/evidence_bundle/ProteinTranslocation/latest` (not the old tracked PT publication).
- Original doer sweep: 2026-10-19T10:19:44.791961Z to11:37:30.731084Z,4665.939118697001 seconds; sweepPID823/runnerPID831, nativeSHA65; final COMPLETE sentinel11:37:42.065907Z. This review inspected that real command/timing/consumption receipt, did not run a second full biological sweep.
- Predicted versus actual: N50 seeds0..49, M100, B1000, raw monomer[6,482], full projected[50,100,2892],64 consumed records (50oracle+14runtime),4fixture authorities,12source/contract hashes,7sentinel-bound sidecars and8compact candidate/live/regenerated files: all matched.
- Actual oracle monomer activity:759/5000 seed-ticks,1726 changed coordinates, every seed active. Substrate activity:759 seed-ticks/4197 changed coordinates. All5000 allocator summary rows match actual before vectors.
- Every accepted-population/copy/embeddedseed identity verified, every consumed path rehashed, and64 deliberately wrong descriptor hashes rejected without input mutation. Constructor actualreads and independent PT/TOA protein authority plus MacromolecularComplexation/RibosomeAssembly complex union verified.
- Original numeric fields re-scored: monomer W1=0, independently recalibrated q95=0.0006345193637621023, threshold1; substrate W1=0.005714285714285714, independent q95=71853.90085285714, threshold143707.8017057143. Both SEED_NOISE; mechanical PASS/no reasons/warnings. Recalibration matches retained values within floating-point arithmetic precision; no threshold/sample/RNG changes.
- Fresh controls: **27passed/0failed/0errors/0skipped/0xfail**; canonical WSL pytestPID395. XML `artifacts/m1_cohort/m1_pt/independent_acceptance/controls_retry1.xml`, SHA256 `77f7dfb662d34dcf5e3c116ae3922532ce2a5aac8707f9a232b514b0494cbe87`. Exact selectors/time/PID are in commands.jsonl, controls_retry1.log and control_test_mapping.json.
- Four original publication assertions pass after changing **only** their module EVIDENCE_ROOT/BUNDLE constants to the explicit new candidate. Original assertion/source bytes preserved: SHA256 `3d7e27e2a220d80f6c75b75b46f49e7b3efd3ab258272d4b9cbe9a73f602e19d`. Configuration receipt: publication_candidate_input_configuration.json.
- Frozen sample-isolation2/2 pass. Independent active actual-owner sequence A,A,B,A,B,A for A=(0,2),B=(1,2) used6distinct owners, initial derived RNGs,6nonempty updates/2changed coordinates each, full2892 widths, unchanged input payloads; metadata advancement and poison oracle-after/hint fields did not affect results. No execution RNG resets/cache clearing.
- Original contiguous100tick replay separately re-executed unchanged with observation:1persistent owner,100contiguous RNG transitions,20advancingticks,13nonempty updates; assertions pass. Public input/strict-zero and PT-only anti-oracle/collapsed-projection controls also pass.
- Independent generator bundle/generate/strict+portable audits:7child commands all exit0; PT PASS/green/reasons[]/warnings[],1PASS23unrelatedMISSING, aggregateNON_GREEN as expected. Strict, portable and doer-index normalized content hashes agree at `2f65efcd99ef565318b7242f3261f97b8abd3884e23508dd63b9c133d6325f06`. Candidate index SHA256 `77f852f802723fe49a09968ae3eb842678c8c4d2041548af20b6f6bb144c2383`.
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
- No original full OC tensors retained: original full N50/M100/B1000 biological execution is accepted via frozen producer/consumption/sentinel/actual input evidence, NOT claimed independently rerun in full.
- This reviewer independently recalibrated full Karr-only B1000 nulls and re-scored retained measured OC raw numeric fields. Original full OC W1 cannot be recomputed from absent tensors; actual fresh biological execution here is bounded active-owner samples, existing public-input controls and original100tick contiguous replay.
- W1=0 is equality of empirical value distributions, not coordinate-wise bit identity. Full2892 positions were retained; no collapsed482 proxy used. The existing standalone legacy replay provides its own narrower identity assertions.
- No retained deterministic-convergence/H12 warning exists in this packet. No old H12 support is assumed or promoted; existing approved mechanics/stage2 biological adjudication is reused rather than generically reopened.
- Portable audit used the existing default non-strict mode with raw data still mounted. No physical absent-raw clone was created and no raw files were hidden/deleted.
- The first pytest invocation failed in DrvFS file-descriptor capture (FileNotFoundError during truncate); it is not counted as PASS. Same frozen assertions passed27/27 in fresh retry XML with -s, changing only capture/scratch/output configuration.
- No publication/baseline/semantic/source/test/global-index/plan/journal edits, commits, nested agents, merge or push were performed. Parent owns persistent integrated eligibility.

### Parent integration contract
See VERDICT.json `parent_publication_instructions` for exact destination paths, commands and current source anchors.
Publish only the8byte-identical PT candidate files, verify original publication tests against the integrated copy, regenerate/audit the full global index explicitly from the integrated bundle without replacing unrelated rows, and record semantic/baseline closure. Preserve PTRANS-STAGE2-ALGORITHM and PTRANS-GENUINE-EVIDENCE as RESOLVED and all10VERIFIED semantic claims.
Current baseline source digest metadata is stale after the approved F1 delta: recorded `be95a0b307b08590de24a760183a631d37b96e490526016e17666de72e46809e` /140files versus actual frozen65 `2b78bca95460efce2451e23b6f8f9b30fefaec24604297dae33485d13faa2ecc` /140files. Parent must recompute at final integration; this is not a new PT biological rejection.
Stage tuple: code-reviewed=existingAPPROVED / gate-measured=PASS / candidate-bundled=COMPLETE / independent-accepted=ACCEPTED / committed-eligibility=PENDING_PARENT_PUBLICATION.

**VERDICT: matched — both requested PT candidate findings ACCEPTED.**

## independent_verdict_complete
```json
{
  "stage": "independent_verdict_complete",
  "at": "2026-10-19T12:03:47.051602+00:00",
  "pid": 351,
  "argv": [
    "artifacts/m1_cohort/m1_pt/independent_acceptance/finish.py"
  ],
  "cwd": "/mnt/e/opencell-worktrees/m1-pt-20261017",
  "findings": {
    "PTRANS-COMPLETE-ATTESTATION": "ACCEPTED",
    "PTRANS-SAMPLE-ISOLATION": "ACCEPTED"
  },
  "verdict_sha256": "2e868c3bf04831ba241cb3da4bf42ce8a5706ab2c5fb2151a8d9fef8acd481bf",
  "preservation_changes": 0,
  "scratch_cleanup": "only own review scratch removed",
  "children_running": 0
}
```
