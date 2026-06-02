# L2.2 D1: Union Master List + Owner Manifest Design

Status: D1 expansion of the umbrella design decision recorded in `L2_2_HARNESS_DESIGN.md` § 5 (Decision D1).
Scope: implementation-level specification for the WID-set unification machinery that the v2 harness (`tests/vivarium/l2_2_replay_common_v2.py`) already contains in skeleton form. This doc back-fills the formal algorithm, defines its inputs/outputs, names the governance for the owner manifest, and closes operator questions QO1 + QO4 from the umbrella design.
Authors: agent (with operator review pending).
Related: `L2_2_HARNESS_DESIGN.md`, `data/schemas/per_process/*.toml` (28 F-tomls landed at sweep `6653ee6`), `tests/vivarium/l2_2_replay_common_v2.py`.

---

## Beat 1 — Contract

**Required behavior:** for any composition of k ∈ [2, 4] Karr processes under test, the L2.2 harness can construct a deterministic, per-observable union master WID list and per-process WID→master-index maps such that (a) any two processes that genuinely share a WID get the same master index for that WID; (b) any per-process observable value can be projected to the master space and back without information loss; (c) the resulting union ordering is stable across runs and machines; (d) each shared observable has exactly one designated owner whose tick-0 trace value is used to initialize the master vector.

**Why this matters:** without identity-based unification, harness-v1 silently compared positionally. `tick=5, RNAProcessing, substrates[5]` mismatched `H2O` (oc_val=0) vs `GLN` (karr_val=1.68e6) — the residue magnitude was real, but the diagnosis was wrong, and any "fix" against that residue would have been a fiction. D1 makes positional aliasing structurally impossible.

**Done (property statement, not command success):** there exists a function `build_union_master(process_specs) -> UnionMaster` such that for every pair (p_i, p_j) in the input, for every observable o, for every WID w shared by both, `master_map[p_i][o][p_i_idx(w)] == master_map[p_j][o][p_j_idx(w)]`; and the function is referentially transparent (same inputs → same outputs, byte-equal, regardless of host).

**Beat-4 inversion:**
- Most plausible "looks right, is wrong" mode: the union ordering is stable on machine A but differs on machine B because of Python dict insertion order or `set` iteration nondeterminism. Tests pass on developer machine, fail in CI.
- Falsifier: a unit test that hashes the union master tuple across two fresh Python processes; if hashes differ, ordering is unstable.

---

## Beat 2 — Inventory (machine-checkable, 13 entries ≥ N_inventory=8)

```
- [A01] path=tests/vivarium/l2_2_replay_common_v2.py | kind=code | role=v2 harness; already contains _build_union_master_wids, _master_wids_hash, _assign_master_maps, _build_owner_manifest, _validate_owner_manifest, _projection_via_master skeletons. D1 formalizes these.
- [A02] path=tests/vivarium/l2_2_replay_common.py | kind=code | role=v1 harness (positional overlay). Retained per umbrella D8; D1 explicitly does NOT modify it.
- [A03] path=data/schemas/per_process/*.toml | kind=schema | role=28 per-process schemas (F-tomls) extracted by scripts/extract_per_process_schema.py. Authoritative WID source for union construction. 20/28 have parsed `wids = [...]`; 8/28 carry `EXTRACTOR_FAILED` markers (see Risks § 9).
- [A04] path=scripts/extract_per_process_schema.py | kind=code | role=MATLAB-source → TOML extractor. Owner of the WID literal parser. Gaps here are the blocker for full D1 coverage.
- [A05] path=docs/phase_f/L2_2_HARNESS_DESIGN.md | kind=doc | role=umbrella L2.2 design. § 5 Decision D1 picked Option 1 (union master + owner manifest). This doc is its expansion.
- [A06] path=docs/phase_f/L2_2_HARNESS_V1_BASELINE.md | kind=doc | role=frozen v1 baseline failure. First mismatch: tick=5, RNAProcessing, substrates[5], H2O vs GLN. The D1 falsification target.
- [A07] path=tests/vivarium/test_l2_2_translation_plus_rna_processing.py | kind=code | role=first L2.2 pair test. D1 correctness is judged here.
- [A08] path=tests/vivarium/l2_replay_common.py | kind=code | role=L2.1 single-process helpers; D1 reuses cell_vector, infer_wids_for_observable, project_observable_from_state without modification.
- [A09] path=data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/*.m | kind=code | role=MATLAB oracle; the canonical WID source the F-tomls derive from. Last-resort reference if TOML extraction fails.
- [A10] path=opencell/vivarium/karr_*.py | kind=code | role=per-process Python ports. Each carries `<observable>_wids` runtime attributes; D1 reads these as a TOML-validation cross-check at init.
- [A11] path=docs/architecture/L2_specs/01_Metabolism.md | kind=doc | role=L2 spec; D1 union ordering policy must satisfy spec's observable enumeration.
- [A12] path=docs/prompts/DESIGN_TEMPLATE.md | kind=doc | role=this doc's structural template; D1 uses required section order.
- [A13] path=docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md | kind=doc | role=Beat 1-5 discipline; D1 inherits.
```

---

## Beat 3 — Interaction-surface map

D1 sits between:

- **Upstream (inputs):** per-process F-TOMLs (`data/schemas/per_process/<process>.toml`) → list of `(observable, [WID])` tuples per process. Optional: live runtime cross-check against `opencell.vivarium.karr_<process>.<Process>().<observable>_wids`.
- **Downstream (consumers):** v2 harness `_build_context`, `_projection_via_master`, `_apply_update`, and the CAUSE_1 diagnostic.
- **Sibling artifacts:** owner manifest (`data/schemas/owner_manifest.toml`, NEW; format defined in § 6 below). Required by `_build_owner_manifest` validation.
- **Test surface:** `tests/vivarium/test_l2_2_*_replay.py` — D1 must not change L2.1 test surfaces (single-process tests use per-process WIDs directly without master mapping).
- **Out of scope:** L3 full-chassis composition (k > 4); MATLAB-side trace extraction (D1 consumes traces, does not produce them); per-tick RNG-stream alignment (separate Class C work in L2.1 matrix).

---

## Beat 4 — Decision ledger (D1 sub-decisions D1.1 … D1.5)

### D1.1 — Union ordering policy (closes umbrella QO1)

- **Question:** how should the union master list be ordered so that (a) ordering is reproducible across runs/machines/branches, (b) ordering is human-readable/auditable, (c) ordering is stable when a new process is added to the composition?
- **Options:**
  1. Insertion order following composition's `under_test_processes` list (e.g. processes A, B, C in that order; each process contributes its WIDs in TOML order; deduplicate by first-appearance).
  2. Lexicographic sort over the union set (alphabetical by WID string).
  3. Karr-source-defined canonical ordering (use the WID ordering from the KnowledgeBase root list).
  4. Hash-stable ordering (e.g. `sha256(wid)` sort).
- **Chosen:** **Option 1 (first-appearance over `under_test_processes` order, then TOML order within each process).**
- **Rationale:**
  - Reproducible: deterministic given the (sorted) input.
  - Human-readable: developer can trace which process "introduced" each WID.
  - Stable when adding a process: existing indices for already-included WIDs do not change (new WIDs are appended).
  - Option 2 (lex sort) wins on simplicity but loses stability under insertion (alphabetic insertion shifts every later index).
  - Option 3 (Karr canonical) is appealing but the KB ordering is not currently extracted and would introduce a new dependency.
  - Option 4 (hash) is stable but unreadable; reject.
- **Tradeoffs:** the user must commit to a canonical `under_test_processes` order (alphabetical by process class name) to get fully deterministic ordering across test invocations.
- **Beat-4 inversion:** if a developer reorders `under_test_processes` in a test, union indices shift silently. Mitigation: D1 implementation MUST hash-stamp the union master and store the hash in the test's failure record; mismatch in hash across runs surfaces the instability.
- **Falsifier:** unit test `test_union_master_stable_across_process_order` constructs union with (A,B,C) and (C,B,A), asserts that for every WID, its master index is identical regardless of process order. (For first-appearance policy, this requires canonical-sorting `under_test_processes` BEFORE union construction — codified in implementation.)
- **Implementation note:** `_build_union_master_wids` must canonically sort `under_test_processes` by process class name (Python `sorted()`, stable, ASCII-bytewise) before iteration.

### D1.2 — Owner manifest format and storage (closes umbrella QO4)

- **Question:** how should the per-observable owner be declared, stored, and governed?
- **Options:**
  1. Inline `[owner]` table per F-TOML (each process declares which observables it owns).
  2. Standalone `data/schemas/owner_manifest.toml` (single global manifest enumerating owner per observable per composition).
  3. Computed lazily at runtime from per-process schemas (`writes`/`reads` annotations).
- **Chosen:** **Option 2 (standalone `data/schemas/owner_manifest.toml`).**
- **Rationale:**
  - Owner is a *composition* property, not a *process* property. Two different L2.2 compositions of the same process may pick different owners.
  - Standalone file is auditable in one place; reviewable in PRs.
  - Computed-at-runtime (Option 3) hides governance and breaks under processes with overlapping writes (multiple "owners").
- **Tradeoffs:** manual maintenance. Mitigated by `_validate_owner_manifest` failing harness setup if manifest references a missing process/observable.
- **Beat-4 inversion:** owner manifest drifts from reality (process X claims to own substrates but no longer writes them). Mitigation: validation step cross-checks declared owner against runtime `process.next_update()` written observables in a smoke run; mismatch = harness setup fail.
- **Falsifier:** test that injects an owner-manifest entry naming a non-existent observable and asserts harness raises a structured `OwnerManifestError` before tick loop starts.

Owner manifest schema (initial draft):

```toml
# data/schemas/owner_manifest.toml
schema_version = 1

[[ownership]]
composition = "Translation+RNAProcessing"   # canonical-sorted, "+"-joined class names
observable = "substrates"
owner_process = "Translation"
rationale = "Translation initializes the amino-acid pool first per Karr execution order"

[[ownership]]
composition = "Translation+RNAProcessing"
observable = "enzymes"
owner_process = "RNAProcessing"
rationale = "..."
```

- One `[[ownership]]` entry per (composition, observable) pair. Missing entry = harness setup fail with `OwnerManifestError("no owner declared for ...")`.

### D1.3 — TOML → WID extraction completeness handling

- **Question:** 8/28 F-TOMLs carry `EXTRACTOR_FAILED` for substrate WIDs. How should D1 behave for compositions involving these processes?
- **Options:**
  1. Hard-fail union construction if any participating process has EXTRACTOR_FAILED for any observable.
  2. Permit but emit a `WID_INFERRED_FROM_RUNTIME` warning, falling back to `<Process>().<observable>_wids` runtime attribute.
  3. Skip the affected observable from union, comparing only the well-defined ones.
- **Chosen:** **Option 2 with strict logging.**
- **Rationale:**
  - Option 1 blocks 8 processes from L2.2 entirely until the extractor is fixed (Phase F.1 work). Too restrictive given L2.2 timeline.
  - Option 3 silently weakens the test contract — exactly the v1 failure mode D1 is meant to prevent.
  - Option 2 preserves coverage and surfaces the gap loudly in test output.
- **Tradeoffs:** runtime fallback ties D1 correctness to the Python port's WID attribute being correct. Acceptable since L2.1 GREEN already validates that attribute for each process.
- **Beat-4 inversion:** runtime WID list differs from MATLAB's true WID list, D1 unifies on a wrong basis. Mitigation: when fallback is used, harness MUST emit a CI-visible warning that names the process+observable; operator review is gated on extractor fix before declaring L2.2 GREEN.
- **Falsifier:** test that constructs union for a composition including one EXTRACTOR_FAILED process; asserts (a) union builds, (b) a `WID_INFERRED_FROM_RUNTIME` record appears in the harness's structured-warning log.

### D1.4 — Master-vector dtype and missing-value semantics

- **Question:** when projecting a per-process value into the master vector (or vice versa), what is the value at master indices that are not covered by the source process?
- **Options:**
  1. Zero-fill (numpy default).
  2. NaN-fill (forces explicit handling downstream).
  3. Sentinel `MISSING_FROM_PROCESS` mask + zero value.
- **Chosen:** **Option 3 (mask + zero).**
- **Rationale:**
  - Zero-fill conflates "process does not see this WID" with "process sees zero of this WID" — a bug magnet.
  - NaN-fill cascades NaN into delta arithmetic and breaks `assert_delta_integral`.
  - Mask is explicit and harness checks can assert "mismatches at masked indices are not failures."
- **Implementation note:** `UnionMaster` is a dataclass with `master_wids: tuple[str, ...]`, `per_process_to_master: dict[str, dict[str, np.ndarray]]` (process → observable → index map), and `coverage_mask: dict[str, dict[str, np.ndarray]]` (process → observable → bool mask of master length).

### D1.5 — Cross-tick stability + cache key

- **Question:** is the union master rebuilt per tick or once per harness invocation?
- **Chosen:** once per harness invocation. Cached in the harness context.
- **Cache key:** `sha256((tuple(sorted(under_test_processes)), schema_version, owner_manifest_hash, tuple(toml_file_mtimes)))`.
- **Rationale:** WID sets are static within a run; rebuilding per tick is waste. Cache key includes manifest hash so manifest edits invalidate cache.

---

## Beat 5 — Expected outcomes and verification claims

**Claim C1 (positional aliasing eliminated):** after D1, the first L2.2 failure for Translation+RNAProcessing must NOT report `substrates[5] H2O vs GLN`. It must either resolve to a non-substrate observable, OR report substrates with same WID on both sides (proving the mismatch is value-divergence, not WID-misalignment).

**Claim C2 (ordering stability):** `python -c "from tests.vivarium.l2_2_replay_common_v2 import _build_union_master_wids; print(_master_wids_hash(_build_union_master_wids([...])))"` produces the same hex digest in two fresh Python processes on two machines.

**Claim C3 (owner manifest enforcement):** running harness against a composition with no manifest entry fails with `OwnerManifestError` BEFORE tick loop begins, not during.

**Claim C4 (extractor-failed coverage):** running harness on a composition including 1+ EXTRACTOR_FAILED processes succeeds with non-empty structured warning log containing `WID_INFERRED_FROM_RUNTIME` records.

**Claim C5 (cache invalidation):** modifying `data/schemas/owner_manifest.toml` between two invocations causes union master to be rebuilt (provable via mtime check on a cache-key debug file).

---

## Beat 6 — Open questions for operator (6 entries ≥ N_questions=5)

1. **QD1.1 (governance):** who owns `data/schemas/owner_manifest.toml`? Suggest: same owner as F-TOMLs (extracted/curated alongside). Operator decision.
2. **QD1.2 (extractor priority):** the 8 EXTRACTOR_FAILED F-TOMLs are `chromosome_condensation, chromosome_segregation, cytokinesis, dna_damage, dna_repair, ...` (full list to enumerate from a sweep TOML scan). Do we fix the extractor as Phase F.1 immediately, or defer to after L2.2 v2 first pair lands GREEN?
3. **QD1.3 (compositions list):** what's the canonical list of L2.2 compositions to test in the v2 baseline? The umbrella design implies k ∈ [2, 4]; do we want all `C(28, 2) = 378` pairs, or a curated subset of Karr-meaningful pairings (e.g., transcription+rna_decay, translation+protein_decay)?
4. **QD1.4 (cache invalidation in CI):** should the union-master cache be process-local or persisted to disk for cross-pytest-invocation reuse? Recommend: process-local (rebuild per pytest session).
5. **QD1.5 (ordering policy ratification):** Option 1 (first-appearance over sorted process list) was chosen for D1.1. Operator concur or prefer Option 3 (Karr canonical, deferred to Phase F.1)?
6. **QD1.6 (manifest format ratification):** the proposed `[[ownership]]` schema is a starting point. Operator concur or prefer JSON / YAML / a `data/schemas/owners/` folder of per-composition files?

---

## Beat 7 — Scope boundary

**In scope:**
- Union master construction algorithm + caching.
- Per-process WID→master index maps + coverage masks.
- Owner manifest schema, validation, error semantics.
- Integration points into existing `_build_context`, `_projection_via_master`, CAUSE_1 diagnostic in `l2_2_replay_common_v2.py`.
- Unit tests for ordering stability, manifest validation, EXTRACTOR_FAILED fallback.

**Out of scope:**
- Fixing the 8 EXTRACTOR_FAILED F-TOMLs (Phase F.1).
- L3 full-chassis composition (k > 4).
- Modifying the v1 harness `l2_2_replay_common.py`.
- Modifying L2.1 single-process tests or per-process Python ports.
- MATLAB-side trace extraction.
- Per-tick RNG-stream alignment (L2.1 matrix work).

---

## Beat 8 — Migration and rollout

1. Land this doc on `audit/l2-1-sweep-v2`. No code change yet.
2. Operator review + answers to QD1.1 … QD1.6.
3. Land `data/schemas/owner_manifest.toml` with entries for the v2-baseline pair `Translation+RNAProcessing` (plus any other operator-prioritized compositions).
4. Implement remaining hooks in `_build_union_master_wids`, `_assign_master_maps`, `_build_owner_manifest`, `_validate_owner_manifest`, `_projection_via_master` per this design. (Most skeletons already exist.)
5. Add unit tests in `tests/vivarium/test_l2_2_union_master.py` covering claims C1–C5.
6. Re-run `tests/vivarium/test_l2_2_translation_plus_rna_processing.py`. Expected: RED reclassifies away from CAUSE_1 (positional WID aliasing) toward CAUSE_4 (upstream pollution) or CAUSE_5 (intrinsic divergence) — those are the next layer to repair.
7. Backout: delete `data/schemas/owner_manifest.toml` and revert harness imports. v1 harness remains intact per umbrella D8.

---

## Beat 9 — Risks and residual unknowns

- **R1 (extractor fragility):** if Phase F.1 stalls, 8 processes remain on the runtime-fallback path; D1 coverage is technically complete but trust is partial. Mitigation: structured warnings + operator gate before L2.2 GREEN claim.
- **R2 (KB canonical ordering deferred):** D1.1 picks Option 1 (first-appearance) over Option 3 (KB canonical) for pragmatism. If later we discover Karr's MATLAB code assumes KB ordering implicitly somewhere, we may have to migrate.
- **R3 (owner manifest combinatorics):** if QD1.3 picks all pairs (378), the manifest becomes a large hand-curated artifact. Auto-generation script becomes a Phase F.2 follow-up.
- **R4 (cache key under TOML regeneration):** if the extractor is rerun and produces byte-identical TOMLs with different mtimes, the cache invalidates needlessly. Acceptable cost; revisit only if test suite slowdown is measurable.
- **R5 (silent dtype coercion):** numpy int32/int64 coercion when projecting between master and per-process arrays. Mitigation: explicit `astype(np.int64, casting='safe')` at projection boundaries.

---

## Operator review checklist

- [ ] D1.1 ordering policy: concur with Option 1 (first-appearance over sorted process list)?
- [ ] D1.2 owner manifest format + storage location: concur with standalone TOML at `data/schemas/owner_manifest.toml`?
- [ ] D1.3 EXTRACTOR_FAILED fallback policy: concur with runtime-attribute fallback + structured warning?
- [ ] D1.4 missing-value semantics: concur with mask + zero (Option 3)?
- [ ] D1.5 cache scope: concur with process-local (no disk persistence)?
- [ ] QD1.2 extractor priority: Phase F.1 immediately, or defer until first L2.2 pair GREEN?
- [ ] QD1.3 composition coverage: curated subset or all C(28,2) pairs?
- [ ] Doc reviewed for the 9 DESIGN_TEMPLATE acceptance bar items.

---

## Provenance

- Drafted: Day 18 evening, in parallel with 3 L2.1 codex jobs (dna_super-randperm port, rna_decay-extraction extension, pdecay-4820 lift).
- Inputs: `L2_2_HARNESS_DESIGN.md` § 5 D1, `L2_2_HARNESS_V1_BASELINE.md`, sweep tip `6653ee6` F-TOMLs (28 files, 20 OK / 8 EXTRACTOR_FAILED), existing `_build_union_master_wids` etc. skeletons in `l2_2_replay_common_v2.py`.
- Not yet implemented; spec-only.
