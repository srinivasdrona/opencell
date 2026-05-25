# CONSOLIDATED_AUDIT_REPORT

## Executive summary
This document consolidates five passes from the same investigation window: reducer output, GPT-5.5 critique, composition audit (L0/L1/L2/L7), allocator-completeness audit (L3/L4/L6), and L5 helper-semantics audit. The reducer reported 181 total findings with 19 `blocks_b1` items; this report reclassifies only those items plus secondary-only additions. (swarm-reducer/opencell/validation/swarm/swarm_report.md:5; swarm-reducer/opencell/validation/swarm/swarm_report.md:7; swarm-composition/opencell/validation/swarm/composition/composition_audit.md:1; swarm-allocator/opencell/validation/swarm/allocator/allocator_audit.md:1; swarm-l5-semantics/opencell/validation/swarm/l5/zero_grant_contract_recommendation.md:1)

Compared with the reducer’s 19-item Track-A candidate list, the post-secondary status is:
- `confirmed`: 15
- `recategorized`: 3
- `gated`: 1
- `refuted`: 0 full drops

The biggest change is structural partitioning. The critique said the reducer’s allocator-bypass cluster mixed distinct seams (helper semantics, enrollment topology, key identity, request correctness, resource-vector completeness). Secondary audits closed that gap with explicit layer ownership: L5 strict-zero helper semantics, L2 enrollment/topology, L3 vector completeness, L4 key identity, and L6 request-calculator correctness. (swarm-reducer/opencell/validation/swarm/gpt55_critique.md:10; swarm-reducer/opencell/validation/swarm/gpt55_critique.md:20; swarm-composition/opencell/validation/swarm/composition/composition_audit.md:18; swarm-allocator/opencell/validation/swarm/allocator/allocator_audit.md:9; swarm-l5-semantics/opencell/validation/swarm/l5/zero_grant_contract_recommendation.md:16)

Track-A is now locked to five PRs: A1 strict-zero helper contract rollout, A2 direct-writer enrollment remediation, A3 key/request consistency fixes, A4 resource-vector completeness, A5 runtime-identity guardrails for TX/TL. Fixture replay pipeline rebuild and central-dogma re-audit remain deferred prerequisites, not part of this Track-A lock. (swarm-composition/opencell/validation/swarm/composition/composition_audit.md:7; swarm-composition/opencell/validation/swarm/composition/composition_audit.md:13; swarm-composition/opencell/validation/swarm/composition/composition_audit.md:48)

## Audit chronology
Date anchor: critique is dated 2026-05-25; reducer spot-check artifacts use seed `20260525`.

| order | pass | branch | date anchor |
|---|---|---|---|
| 1 | reducer synthesis (`swarm_report.md`, `bugs_to_fix.md`) | `swarm/reducer` | 2026-05-25 window |
| 2 | GPT-5.5 structural critique (`gpt55_critique.md`) | `swarm/reducer` | 2026-05-25 explicit |
| 3 | composition audit (L0/L1/L2/L7) | `swarm/composition` | post-critique, same window |
| 4 | allocator completeness (L3/L4/L6) | `swarm/allocator-completeness` | post-critique, same window |
| 5 | L5 helper semantics | `swarm/l5-semantics` | post-critique, same window |

Evidence: (swarm-reducer/opencell/validation/swarm/swarm_report.md:8; swarm-reducer/opencell/validation/swarm/spot_check_log.jsonl:1; swarm-reducer/opencell/validation/swarm/gpt55_critique.md:3; swarm-composition/opencell/validation/swarm/composition/composition_audit.md:1; swarm-allocator/opencell/validation/swarm/allocator/allocator_audit.md:1; swarm-l5-semantics/opencell/validation/swarm/l5/zero_grant_contract_recommendation.md:1)

## Findings catalog (revised)
Status semantics: `confirmed` = in Track-A scope, `recategorized` = real but moved layer, `gated` = needs explicit precondition/decision.

| # | reducer finding | status | Track-A PR | citation |
|---|---|---|---|---|
| 1 | ChromosomeCondensation zero-grant fallback | confirmed | A1 | l5/l5_call_sites.csv:2 |
| 2 | ChromosomeSegregation zero-grant fallback | confirmed | A1 | l5/l5_call_sites.csv:4 |
| 3 | Cytokinesis zero-grant fallback | confirmed | A1 | l5/l5_call_sites.csv:6 |
| 4 | DNADamage not allocator-enrolled | gated | deferred | composition/composition_audit.md:29 |
| 5 | DNARepair zero-grant fallback | confirmed | A1 | l5/l5_call_sites.csv:8 |
| 6 | DNASupercoiling ATP-only allocation | recategorized (L3) | A4 | composition/composition_audit.md:27; allocator/allocator_audit.md:11 |
| 7 | MacromolecularComplexation consume-with-zero-demand path | confirmed | A3 | composition/composition_audit.md:24; allocator/allocator_audit.md:44 |
| 8 | Metabolism direct writer, non-enrolled | confirmed | A2 | composition/composition_audit.md:20 |
| 9 | ProteinDecay direct writer bypass path | confirmed | A3 | composition/composition_audit.md:25 |
| 10 | ProteinFolding zero-grant fallback | confirmed | A1 | l5/l5_call_sites.csv:16 |
| 11 | ProteinModification zero-grant fallback | confirmed | A1 | l5/l5_call_sites.csv:18 |
| 12 | ProteinProcessingI zero-grant fallback | confirmed | A1 | l5/l5_call_sites.csv:19 |
| 13 | RNAProcessing zero-grant fallback | confirmed | A1 | l5/l5_call_sites.csv:24 |
| 14 | Replication zero-grant fallback | confirmed | A1 | l5/l5_call_sites.csv:12 |
| 15 | ReplicationInitiation zero-grant fallback | confirmed | A1 | l5/l5_call_sites.csv:14 |
| 16 | Transcription direct drains without enrollment | recategorized (runtime v3 path) | A2 | composition/composition_audit.md:10; composition/composition_audit.md:21 |
| 17 | Translation direct drains without enrollment | recategorized (runtime v3 path) | A2 | composition/composition_audit.md:11; composition/composition_audit.md:22 |
| 18 | tRNAAminoacylation zero-grant fallback | confirmed | A1 | l5/l5_call_sites.csv:25 |
| 19 | ProteinDecay allocator default-key mismatch | confirmed | A3 | allocator/allocator_audit.md:34 |

## New findings surfaced
1. `ProteinTranslocation` L3 vector gap (ATP-only in Python request/enrollment vs ATP+GTP+H2O in extracted Karr contract). (allocator/allocator_audit.md:17)
2. L7 fixture provenance: 28/28 fixtures are single-snapshot and non-replay-capable (`fixture_n_ticks=1`, no I/O channels). (composition/composition_audit.md:7; composition/composition_audit.md:32)
3. `MacromolecularComplexation` L4 default-key drift (`d2_real` vs `karr_macromolecular_complexation`). (allocator/allocator_audit.md:26)
4. L0 runtime-class mismatch explicitly surfaced for `Transcription` and `Translation`. (composition/composition_audit.md:4; composition/composition_audit.md:10; composition/composition_audit.md:11)
5. L5 expansion: critique seeded 6 helper-fallback cases, while L5 fix-locus inventory identifies 15 strict-zero-sensitive helper/inline sites (9 beyond the critique seed). (swarm-reducer/opencell/validation/swarm/gpt55_critique.md:12; l5/zero_grant_contract_recommendation.md:33; l5/zero_grant_contract_recommendation.md:48)

## Critique structural verdict - closure
| critique concern | closure |
|---|---|
| allocator-bypass partitioning was symptom-shaped | Closed by layer split across L2/L3/L4/L5 with dedicated hot lists and ownership. (swarm-reducer/opencell/validation/swarm/gpt55_critique.md:10; composition/composition_audit.md:18; allocator/allocator_audit.md:9; l5/zero_grant_contract_recommendation.md:16) |
| t0-cluster instability mixed heterogeneous evidence | Closed by L7 classification that distinguishes replay incapability, positive mismatch-absent evidence, and scoped mismatches. (swarm-reducer/opencell/validation/swarm/gpt55_critique.md:22; composition/composition_audit.md:35; composition/composition_audit.md:37) |
| audit redundancy/order (helper decision vs fleet audit; replay vs t0) | Closed by explicit sequencing: strict-zero decision first, replay pipeline called out as deferred prerequisite. (swarm-reducer/opencell/validation/swarm/gpt55_critique.md:26; l5/zero_grant_contract_recommendation.md:18; composition/composition_audit.md:48) |
| missing composition layer | Closed: dedicated composition audit delivered L0/L1/L2/L7 matrices and hot lists. (swarm-reducer/opencell/validation/swarm/gpt55_critique.md:46; composition/composition_audit.md:3) |

## Track-A scope (locked)
| PR | layer | scope | est LOC | dependencies |
|---|---|---|---:|---|
| A1 | L5 | Enforce strict-zero semantics at all audited helper/inline fallback sites. | 180-260 | none |
| A2 | L2 | Remediate direct-writer/non-enrolled substrate traffic for Metabolism + TX/TL runtime v3 paths. | 220-320 | A1, A5 |
| A3 | L4/L6 | Fix key/request seams: `d2_real` drift, ProteinDecay key drift, and zero-demand-while-consuming path. | 120-200 | A1 |
| A4 | L3 | Add missing allocation/request vector members for DNASupercoiling and ProteinTranslocation. | 120-190 | A1 |
| A5 | L0 | Add runtime-identity guardrails so fixes/tests target v6 runtime classes for TX/TL. | 70-130 | none |

Scope basis: (l5/zero_grant_contract_recommendation.md:24; composition/composition_audit.md:20; composition/composition_audit.md:21; composition/composition_audit.md:22; allocator/allocator_audit.md:11; allocator/allocator_audit.md:17; allocator/allocator_audit.md:26; allocator/allocator_audit.md:44)

## Deferred work
1. Fixture pipeline rebuild for replay-capable per-process fixtures (`inputs`/`outputs`, tick-indexed channels). (composition/composition_audit.md:7; composition/composition_audit.md:48)
2. Central-dogma re-audit on canonical runtime classes after A5. (composition/composition_audit.md:13)
3. DNADamage substrate/enrollment decision after model-parity scope decision (currently no substrate traffic path in runtime topology). (composition/composition_audit.md:29; allocator/allocator_audit.md:75)

## Open questions
1. Should L4 key consistency be enforced against allocator defaults only, effective chassis overrides, or both? (allocator/allocator_audit.md:78)
2. Should default aliases (`d2_real`, `protein_decay_light`) be normalized globally to canonical process keys? (composition/composition_audit.md:47)
3. Is fixture channel extraction a hard gate for closing replay/t0 findings, or can it remain a follow-on phase after Track-A contract fixes? (composition/composition_audit.md:48)
