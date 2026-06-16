# PC_T7_CHROMOSOME_PORT_DESIGN

## DAP Intent

Contract (Beat 1):
- Required behavior: port the Karr chromosome state into OpenCell as a real full-state surface for the 11 chromosome fields named by `scripts/matlab/serialize_chromosome_state.m`, while preserving enough compatibility for existing Karr-light consumers during migration.
- Done looks like a system property: the `chromosome` channel can carry and update normalized sparse-triple chromosome fields that satisfy the catalog's chromosome-primary projections for `Replication`, `DNARepair`, `DNASupercoiling`, and `DNADamage` (the four processes whose `primary_channel: chromosome`), and can serve as a chromosome-state input surface for `ReplicationInitiation` (whose `primary_channel: complexs` but which reads/writes chromosome state as a secondary channel).

Surface inventory intent (Beat 2):
- Evidence comes from the serializer, the local `CircularSparseMat` source, the current `karr_replication.py` and `karr_dna_supercoiling.py` ports, the authoritative `PROCESS_CATALOG.yaml`, commit history for `0ff0bb5` and `c5d5adb`, and direct load probes of `PROCESS_CATALOG.yaml`, `Chromosome_flat.mat`, and the catalog-declared trace paths.

Falsifiable expectation (Beat 3):
- If this design is correct, a future implementation will reject placeholder chromosome fixtures, load numeric sparse triples for the 11 chromosome fields, expose them on the `chromosome` store alongside temporary legacy mirrors, and let projection extraction read catalog-named chromosome deltas directly instead of inferring them from `fork_position_bp` or `supercoil_density`.

Inversion (Beat 4):
- Most embarrassing failure mode: the port adds new keys that look like full chromosome state, but they are seeded from broken fixture strings or kept permanently in sync by scalar proxy logic, so smoke tests pass while the catalog-facing chromosome surface is still fictional.

PM/operator sanity-check sentence:
- This design assumes the catalog's full chromosome projections are the authoritative target even though this checkout's local chromosome fixture/trace artifacts are stale or missing; if local artifact availability is meant to redefine scope, this design is too ambitious.

## 1) Design contract

Contract:
- Required behavior: OpenCell must be able to hold, read, and write the 11 Karr chromosome fields (`polymerizedRegions`, `linkingNumbers`, `monomerBoundSites`, `complexBoundSites`, `gapSites`, `abasicSites`, `damagedSugarPhosphates`, `damagedBases`, `intrastrandCrossLinks`, `strandBreaks`, `hollidayJunctions`) as normalized sparse-triple state on the `chromosome` channel, using circular-genome semantics compatible with the MATLAB serializer contract.
- Why this matters: four chromosome-primary L2.2 processes (`Replication`, `DNARepair`, `DNASupercoiling`, `DNADamage` — all with `primary_channel: chromosome`) are currently unwired because the existing OpenCell chromosome surface is scalar Karr-light. A fifth process (`ReplicationInitiation`, `primary_channel: complexs`) reads/writes chromosome state as a secondary channel and also needs the full surface.
- Done = (property statement, not command success): a process that mutates chromosome state can consume and emit top-level `chromosome.<field>` sparse triples plus required metadata, the L2.2 harness can measure the catalog's chromosome projections from those fields directly, and legacy scalar chromosome readers remain functional until explicitly retired.

Beat-4 inversion:
- Most plausible "looks right, is wrong" failure mode: the implementation stores sparse-triple-shaped dicts but populates them from placeholder fixture strings, missing traces, or scalar backfills rather than true chromosome state transitions.
- What would falsify this contract statement: any future probe showing placeholder strings instead of numeric `positions`/`strands`/`values`/`shape`, any projection path still derived from `fork_position_bp` or `supercoil_density`, or any circular-wrap edge case that clips instead of wraps would reopen the design.

## 2) Inventory of existing artifacts

- [A01] path=docs/prompts/DELIBERATE_ACTION_PREFIX_v2.md | kind=doc | role=defines mandatory Beats 1-5 carryover and inversion discipline for this design doc
- [A02] path=docs/prompts/DESIGN_TEMPLATE.md | kind=doc | role=authoritative section order, inventory rules, operator-question minimums, and 9-point acceptance bar
- [A03] path=docs/prompts/COMPOSITION_MANDATE_v2.md | kind=doc | role=authoritative slot mechanics and spec-authority rule anchoring `PROCESS_CATALOG.yaml` as the target contract
- [A04] path=data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+state/Chromosome.m | kind=code | role=primary MATLAB chromosome source requested by the task; probe: filename search found no local copy in this worktree, so exact method semantics remain an evidence gap
- [A05] path=scripts/matlab/serialize_chromosome_state.m | kind=code | role=names the 11 chromosome properties and defines the sparse-triple extraction contract via `find(v)` into `positions`/`strands`/`values`/`shape`
- [A06] path=data/karr_fixtures/m_source/CircularSparseMat.m | kind=code | role=local MATLAB sparse-wrapper source; constructor proves circular-dimension wrapping, and the file contains no local `find` override
- [A07] path=opencell/vivarium/karr_dna_supercoiling.py | kind=code | role=current Karr-light chromosome writer limited to scalar `chromosome.supercoil_density` and replay hints rather than full `linkingNumbers`
- [A08] path=opencell/vivarium/karr_replication.py | kind=code | role=current Karr-light chromosome writer limited to `chromosome.fork_position_bp` plus replay hints rather than full `polymerizedRegions`
- [A09] path=docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml | kind=schema | role=authoritative L2.2 spec; probe: `yaml.safe_load` succeeds with `schema_version=4`, and the five chromosome-primary entries verify the target `primary_channel`, `primary_projection`, and `karr_artifact` fields
- [A10] path=data/karr_fixtures/per_process/Chromosome_flat.mat | kind=fixture | role=current chromosome seed artifact; probe: `sequenceLen=580076` and `nCompartments=4` load, but all 11 chromosome sparse fields currently load as `<flatten-error:...>` strings, so this fixture is not usable for `pc-t7` as-is
- [A11] path=data/m1_sources/karr_native/per_process_traces_v2_s{000..049}/Replication_100ticks.mat | kind=trace | role=50-seed v2 Replication oracle with chromosome sparse triples (post-`0ff0bb5` serializer fix); PRESENT on disk. Content probe: chromosome field is a group with 11 sparse-triple sub-structs (positions/strands/values/shape). These 100-tick mid-cycle traces are the L2.2 Design-A oracle; they contain real chromosome state but are NOT full-cycle traces needed for L2.event.
- [A12] path=data/m1_sources/karr_native/per_process_traces_v2_s{000..049}/ReplicationInitiation_100ticks.mat | kind=trace | role=50-seed v2 ReplicationInitiation oracle; PRESENT on disk with chromosome sparse triples post-serializer fix.
- [A13] path=data/m1_sources/karr_native/per_process_traces_v2_s{000..049}/DNARepair_100ticks.mat | kind=trace | role=50-seed v2 DNARepair oracle; PRESENT on disk with chromosome sparse triples.
- [A14] path=data/m1_sources/karr_native/per_process_traces_v2_s{000..049}/DNASupercoiling_100ticks.mat | kind=trace | role=50-seed v2 DNASupercoiling oracle; PRESENT on disk with chromosome sparse triples. Verified in Day-28 10-tick smoke: linkingNumbers shows real per-tick deltas.
- [A15] path=data/m1_sources/karr_native/per_process_traces_v2_s{000..049}/DNADamage_100ticks.mat | kind=trace | role=50-seed v2 DNADamage oracle; PRESENT on disk with chromosome sparse triples. Day-28 audit: 0/50 seeds have substrate-change events in this 100-tick window (process is EVENT_CLASS).
- [A16] path=docs/phase_f/l2_2_design_a/STATUS_chrom_projections_design.md | kind=status | role=prior chromosome-projection status artifact referenced by catalog notes and commit history; not opened because this task's fixed read-set forbids additional document exploration
- [A17] path=0ff0bb5 | kind=commit | role=provenance for the Day-28 serializer fix; `git show --stat` confirms `serialize_chromosome_state.m` was introduced here
- [A18] path=c5d5adb | kind=commit | role=provenance for chromosome-primary projection wiring; `git show --stat` confirms `PROCESS_CATALOG.yaml` and `STATUS_chrom_projections_design.md` changed here

Beat-4 inversion for inventory:
- What critical artifact could still be missing from this list? The missing local `Chromosome.m` source is the biggest gap, and a refreshed chromosome v2 seed fixture or local chromosome-primary trace bundle may also exist outside this checkout.
- What check did you run to reduce that risk? I searched for `Chromosome.m` in `data/` and repo-wide by exact filename, probed the catalog-declared trace paths directly, and verified the two named commits so the design distinguishes between repo history and locally loadable artifacts.
- What could be WRONG in the artifacts we listed? `A10` is present but broken for the 11 sparse fields; `A11-A15` are authoritative paths in the catalog but absent locally; `A09` names target projections but does not prove the local trace bundle exists; `A17-A18` prove intent in git history but not artifact sync in this worktree. Data-source content checks were run for `A09-A15`, and every trace/fixture result is stated explicitly rather than assumed usable.

## 3) Interaction-surface map

| Surface ID | Producer | Consumer | Contract unit | Failure if mismatched | Evidence anchor |
|---|---|---|---|---|---|
| S1 | MATLAB `serialize_chromosome_state.m` | Python loaders for seed fixtures and traces | 11 sparse-triple fields with `positions`, `strands`, `values`, `shape` metadata | Python sees placeholder strings, missing fields, or wrong shapes and silently seeds fictional chromosome state | A05, A10, A11-A15, A17 |
| S2 | MATLAB `CircularSparseMat` semantics | Python chromosome helper layer | Circular normalization of genome coordinates and `find`-compatible sparse extraction semantics | Boundary-crossing regions clip or duplicate instead of wrapping, corrupting `delta_nnz` and value sums | A04, A06 |
| S3 | `PROCESS_CATALOG.yaml` | Future pc-t7 ports and L2.2/L2.event harnesses | `primary_channel`, `primary_projection`, `primary_distance`, and `blocked_on` contract for the five chromosome-primary processes | Ports expose the wrong store keys or the harness keeps measuring scalar proxies | A03, A09, A18 |
| S4 | `chromosome` store | `KarrDNASupercoilingProcess` | Full `linkingNumbers` field plus temporary scalar compatibility mirror for `supercoil_density` | Port looks green on scalar sigma while the catalog-facing `linkingNumbers` surface remains unwired | A07, A09 |
| S5 | `chromosome` store | `KarrReplicationProcess` and future `ReplicationInitiation` port | Full `polymerizedRegions` field plus temporary compatibility for `replication_state` and `fork_position_bp` | Fork counters move while `polymerizedRegions` stays absent or synthetic | A08, A09 |
| S6 | `chromosome` store | Future `DNARepair` port | Damage/repair fields (`damagedBases`, `strandBreaks`, `gapSites`, `abasicSites`, `damagedSugarPhosphates`) as writable sparse state | Repair stays expressed as pathway aggregates or substrate side effects instead of chromosome edits | A09, A10, A13 |
| S7 | `chromosome` store | Future `DNADamage` port and L2.event harness | Damage-creation fields plus event-class gating semantics | Per-tick no-op passes mask the fact that the chromosome surface is still missing or wrong | A09, A10, A15 |
| S8 | Future chromosome helper/serializer | Vivarium store updaters and projection extraction code | Canonical whole-field `set` payload for each touched chromosome field | Duplicate coordinates, unstable ordering, or non-canonical triples produce false projection deltas | A05, A06, A09 |
| S9 | Chromosome-primary process execution order | Later same-tick readers plus projection extraction | Whole-field canonicalization must happen before any sibling reader or delta measurement observes the updated chromosome field | Intermediate non-canonical state leaks into replay or projection code, creating order-dependent behavior | A07, A08, A09 |
| S10 | Transitional compatibility layer | Existing Karr-light readers downstream of `chromosome` | Legacy scalar keys remain readable while full fields are introduced | Incremental rollout strands sibling callers that still expect `supercoil_density` or `fork_position_bp` | A07, A08 |

Beat-4 inversion:
- Which cross-surface assumption is most likely false? The most fragile assumption is that refreshed local artifacts will match the catalog's expected path and field names exactly once synced.
- What observation would expose that quickly? A loader probe that opens the refreshed fixture/trace bundle and prints one field summary per chromosome property will immediately expose placeholder strings, missing files, or mismatched field names.

## 4) Baseline facts and constraints

Hard constraints from project/session context:
- This task is design-only: no production edits under `opencell/**`, no existing test edits, no catalog edits, and no MATLAB invocation.
- The fixed read-set limits source exploration; the design must stay anchored to the named files plus direct existence/content probes needed for inventory rule 5.
- `STATUS_chrom_port_3slot_v2.md` must be written in the repo root, and the design doc must follow the template structure exactly.

Fidelity constraints from primary source:
- `serialize_chromosome_state.m` treats all 11 chromosome properties as `CircularSparseMat` values and serializes them as sparse triples with shape metadata.
- The local `CircularSparseMat.m` constructor wraps configured dimensions modulo the matrix size; the chromosome port therefore cannot treat genome coordinates as linear-with-clipping.
- The catalog's chromosome-primary projections now target `polymerizedRegions`, `linkingNumbers`, and specific damage-field deltas directly; reconstructing these from substrate or scalar chromosome proxies would violate the authoritative spec.

Existing implementation facts (single-component only):
- `karr_dna_supercoiling.py` currently exposes `chromosome.supercoil_density`, `chromosome.replication_state`, and `chromosome.supercoiled`, not `linkingNumbers`.
- `karr_replication.py` currently exposes `chromosome.replication_state`, `chromosome.fork_position_bp`, and `chromosome.events.replication_complete`, not `polymerizedRegions`.
- `karr_replication.py` reads `Chromosome_flat.mat` for scalar metadata (`sequenceLen`, `sequenceGCContent`) but does not consume the full chromosome sparse fields.
- The local `Chromosome_flat.mat` fixture contains the 11 chromosome field names, but their content is currently placeholder flatten-error strings rather than numeric sparse triples.

Known failures and anti-patterns:
- Local artifact presence is not a valid proxy for usable content; the current chromosome fixture demonstrates the exact failure mode the new inventory rule was added to catch.
- The catalog points at `per_process_traces_v2/*.mat` for chromosome-primary verification, but those exact files are absent in this checkout, so design claims cannot assume local oracle availability.
- Current Karr-light ports rely on scalar chromosome summaries and `trace_hint` replay assistance; these surfaces can mask missing full-state semantics if treated as proof of chromosome fidelity.
- The missing local `Chromosome.m` source means method names such as `setRegionPolymerized`, `setRegionUnwound`, `setSiteDamaged`, and `mergeAdjacentRegions` are known from the task prompt, but their exact edge behavior is not proven from code in this checkout.

Beat-4 inversion:
- Which baseline "fact" is inferred rather than proven? The biggest inference is that a future refreshed artifact bundle will use the serializer's sparse-triple shape directly enough for Python to load without additional normalization glue.
- What would invalidate it? A refreshed artifact probe that still exposes MATLAB object placeholders, alternative field names, or a different container layout would invalidate that assumption.

## 5) Decision ledger

Decision D1
- Question: How should each chromosome field be represented in Python and on the Vivarium store?
- Options considered:
  1) Dense `numpy.ndarray` of shape `[580076, 4]` for every field.
  2) `scipy.sparse` matrix objects stored directly on the state tree.
  3) A normalized sparse-triple record (`positions`, `strands`, `values`, `shape`) with a Python helper class for operations and round-trips.
- Chosen option: 3.
- Rationale: the sparse-triple record matches the serializer contract, is easy to validate with simple probes, is stable to serialize into Vivarium state, and aligns directly with the catalog projection vocabulary.
- Tradeoffs accepted: OpenCell must own a small helper layer for canonicalization and mutation rather than outsourcing everything to `scipy.sparse`.
- Beat-4 inversion (how chosen option could be wrong): the helper could preserve projection-level totals while still mishandling region adjacency, duplicate coordinates, or update ordering.
- Falsifier (what evidence would force reopening D1): any round-trip probe where load -> mutate -> serialize changes `nnz`, coordinate ordering, or summed values for an unchanged field.
- Operator escalation needed? no

Decision D2
- Question: How should circular chromosome semantics be preserved without MATLAB runtime support?
- Options considered:
  1) Treat the chromosome as a bounded linear array and clip out-of-range coordinates.
  2) Implement point updates only and leave region operations to ad hoc process code.
  3) Implement a dedicated helper that normalizes modulo `sequenceLen`, coalesces duplicate coordinates, and exposes region/site operations corresponding to the Karr chromosome concepts.
- Chosen option: 3, with phase gating.
- Rationale: the constructor behavior in `CircularSparseMat.m` proves circular normalization is core semantics, and the task's named methods imply reusable region/site operations rather than one-off point patches.
- **Phase gating (MAJOR-4 fix):** Phase 1 implements coordinate normalization and sparse-triple CRUD (proven from `CircularSparseMat.m` source). Phase 2 implements region-mutation helpers (`setRegionPolymerized`, `setRegionUnwound`, `setSiteDamaged`, `mergeAdjacentRegions`) ONLY after `Chromosome.m` source or golden boundary-case traces are available to verify edge behavior. Until then, phase 1's sparse CRUD is sufficient for store/loader/projection work; the mutation helpers are NOT implemented from prompt-inferred method names alone.
- Tradeoffs accepted: phase 2 is blocked on operator providing `Chromosome.m` or golden trace fixtures. This is an explicit dependency, not a silent assumption.
- Beat-4 inversion (how chosen option could be wrong): phase 1 may look complete while phase 2 remains indefinitely deferred, leaving mutation helpers as TODO stubs.
- Falsifier (what evidence would force reopening D2): operator-supplied `Chromosome.m` code or trace probes showing different results for wraparound or adjacency cases than the phase-1 normalization assumes.
- Operator escalation needed? yes + QO1

Decision D3
- Question: How should the full chromosome state integrate with the existing Vivarium store?
- Options considered:
  1) Replace the existing `chromosome` store entirely with full sparse fields.
  2) Add a sibling store such as `chromosome_full` and keep the current `chromosome` store unchanged.
  3) Extend the existing `chromosome` store with the 11 full sparse fields and metadata while retaining the current scalar keys during migration.
- Chosen option: 3.
- Rationale: the catalog already names `primary_channel: chromosome`; extending that channel avoids catalog churn, keeps the authoritative surface name stable, and permits incremental migration of existing readers.
- Tradeoffs accepted: the `chromosome` store will temporarily mix sparse full-state fields with legacy scalar summaries, and the rollout must prevent them from drifting.
- Beat-4 inversion (how chosen option could be wrong): both surfaces may coexist, but only the scalar mirror gets updated in practice because it is easier to test.
- Falsifier (what evidence would force reopening D3): any parity probe where a process changes `fork_position_bp` or `supercoil_density` without a corresponding full-field mutation, or vice versa.
- Operator escalation needed? no

Decision D4
- Question: What updater contract should chromosome-primary processes use when they touch full chromosome fields?
- Options considered:
  1) Emit per-coordinate delta fragments and merge them in a custom store updater.
  2) Materialize a helper object inside the process and emit whole-field `set` replacements only for the chromosome fields touched that tick.
  3) Replace the entire chromosome state blob on every tick.
- Chosen option: 2.
- Rationale: whole-field replacement for touched sparse fields keeps canonicalization local to the helper, avoids fragile merge logic in the store, and is simpler to verify against the sparse-triple contract than a blob-level replacement.
- **Concrete schema example (MAJOR-5 fix):** for `chromosome.linkingNumbers`, the `ports_schema()` entry would be:
  ```python
  "chromosome": {
      "linkingNumbers": {
          "positions": {"_default": np.array([], dtype=np.int64), "_updater": "set", "_emit": True},
          "strands": {"_default": np.array([], dtype=np.int8), "_updater": "set", "_emit": True},
          "values": {"_default": np.array([], dtype=np.int32), "_updater": "set", "_emit": True},
          "shape": {"_default": np.array([580076, 4], dtype=np.int64), "_updater": "set", "_emit": True},
      },
      # Legacy compatibility mirror (temporary):
      "supercoil_density": {"_default": -0.06, "_updater": "set", "_emit": True},
  }
  ```
  Each process that writes a chromosome field emits the ENTIRE sparse triple for that field via `_updater: set`. No partial delta merging. The helper canonicalizes (sorted positions, coalesced duplicates, stable ordering) BEFORE emitting. Copy semantics: Vivarium's `set` updater replaces the value — no in-place mutation of arrays across ticks. Validation: the store's `_emit: True` makes before/after snapshots available to L2.2 projection code.
- Tradeoffs accepted: per-tick payloads are larger than coordinate deltas, and performance must be verified before large L2.2 ensembles rely on this path.
- Beat-4 inversion (how chosen option could be wrong): smoke runs may look fine while whole-field replacement becomes the dominant runtime or memory cost at ensemble scale.
- Falsifier (what evidence would force reopening D4): performance probes showing helper serialization or store replacement cost overwhelming current L2 budgets.
- Operator escalation needed? no

Decision D5
- Question: How should pc-t7 preserve current L2.1/Karr-light behavior while the full chromosome ports are rolled out incrementally?
- Options considered:
  1) Remove the light chromosome scalars immediately and migrate every consumer in one cutover.
  2) Keep scalar compatibility mirrors (`supercoil_density`, `fork_position_bp`, `replication_state`, related events) until all affected consumers are migrated.
  3) Freeze current ports and create separate v2 process modules for every chromosome-primary process.
- Chosen option: 2.
- Rationale: the current codebase already depends on light scalar surfaces, and a compatibility window reduces the risk that pc-t7 breaks unrelated callers before the full chromosome ports are in place.
- Tradeoffs accepted: dual semantics increase verification burden because the design must prove the mirrors are transitional rather than a new permanent source of truth.
- Beat-4 inversion (how chosen option could be wrong): the compatibility mirrors may become the operational truth forever, and the new full fields may exist only to satisfy schema checks.
- Falsifier (what evidence would force reopening D5): any supposedly completed chromosome-primary port whose projections still depend on scalar proxies or replay hints rather than full sparse fields.
- Operator escalation needed? yes + QO2

Decision D6
- Question: What artifact strategy should seed and verify the full chromosome state?
- Options considered:
  1) Trust the current `Chromosome_flat.mat` path as the seed source.
  2) Reconstruct the full chromosome state from the current scalar/light chromosome surface.
  3) Require refreshed serializer-v2 artifacts (`Chromosome_flat.mat` or an equivalent replacement) and catalog-declared chromosome-primary traces before implementation proceeds.
- Chosen option: 3.
- Rationale: the current fixture is demonstrably broken for the 11 sparse fields, and scalar reconstruction would recreate the exact placeholder-era anti-pattern the catalog already moved away from.
- Tradeoffs accepted: implementation is gated on artifact refresh or sync outside this design doc.
- Beat-4 inversion (how chosen option could be wrong): a refreshed artifact bundle may exist but still carry partial fields, mislabeled data, or stale placeholder values, and a weak loader could miss that.
- Falsifier (what evidence would force reopening D6): a content probe on the refreshed artifact bundle failing to load numeric sparse triples for any required chromosome field.
- Operator escalation needed? yes + QO3

Decision D7
- Question: In what order should the five chromosome-primary processes be re-ported once the shared state layer exists?
- Options considered:
  1) Big-bang all five processes in one branch.
  2) Start with damage/repair because those processes are the most visibly blocked.
  3) Build shared infra first, then single-field writers, then the polymerization pair, then the multi-field damage writers.
- Chosen option: 3.
- Rationale: `DNASupercoiling` exercises one field (`linkingNumbers`) and is the smallest useful proving ground; `Replication` and `ReplicationInitiation` share polymerization semantics; `DNARepair` and `DNADamage` touch the widest field set and benefit from a stabilized helper; `DNADamage` remains last because L2.event still blocks its full gate even after pc-t7 lands.
- Tradeoffs accepted: the coexistence window lasts longer, and process-specific adapters must exist temporarily.
- Beat-4 inversion (how chosen option could be wrong): the helper could overfit `linkingNumbers` and `polymerizedRegions`, forcing a redesign when the damage fields arrive.
- Falsifier (what evidence would force reopening D7): DNARepair or DNADamage implementation discovering it cannot express a catalog-named projection cleanly with the shared helper/store contract.
- Operator escalation needed? no

## 6) Expected outcomes and verification claims

Claim C1:
- If design is correct, we should observe: the seed chromosome artifact used by implementation loads numeric sparse-triple content for all required chromosome fields instead of placeholder strings.
- Measurement method / command / assertion: a Python probe (`scipy.io.loadmat` or equivalent) prints one summary per field and confirms numeric `positions`, `strands`, `values`, and integer `shape`. Additionally, each sparse-triple sub-struct must have `error` field absent or empty string (the serializer writes an `error` field on extraction failure), arrays must be non-scalar, dtypes must be integer, and `shape == [sequenceLen, 4]`.
- Threshold or exact value: no chromosome field may load as a string placeholder such as `<flatten-error:...>`; no field may have a non-empty `error` string; every required field must expose numeric sparse-triple subfields with consistent lengths (`len(positions) == len(strands) == len(values)`).
- Why this distinguishes from alternatives: path existence alone would still pass if the artifact were stale or placeholder-filled; checking only for string placeholders would miss fields where the struct exists but `error` is populated and arrays are empty.

Claim C2:
- If design is correct, we should observe: chromosome-primary ports expose the catalog-named full chromosome fields on the `chromosome` store while retaining temporary scalar compatibility mirrors.
- Measurement method / command / assertion: inspect each port's `ports_schema()` and confirm presence of both the new full-field keys (for that port's touched chromosome fields) and the legacy keys needed during migration.
- Threshold or exact value: `DNASupercoiling` must expose `chromosome.linkingNumbers`; `Replication` and `ReplicationInitiation` must expose `chromosome.polymerizedRegions`; `DNARepair` and `DNADamage` must expose their catalog-named damage fields; legacy mirrors stay present until the migration step that retires them.
- Why this distinguishes from alternatives: a light-surface-only port can still pass legacy smoke checks without satisfying the catalog-facing chromosome contract.

Claim C3:
- If design is correct, we should observe: L2 projection extraction reads chromosome deltas directly from before/after sparse fields, not from scalar fork or sigma proxies.
- Measurement method / command / assertion: a unit-level projection probe over synthetic before/after chromosome states computes `polymerizedRegions.delta_value_sum_strand_*`, `polymerizedRegions.delta_nnz`, `linkingNumbers.delta_value_sum`, `linkingNumbers.delta_nnz`, and the damage-field `delta_nnz` values from sparse-field comparisons alone.
- Threshold or exact value: the projection code path must not read `fork_position_bp`, `supercoil_density`, or pathway aggregate repair counters for these catalog projections.
- Why this distinguishes from alternatives: a proxy-based implementation can look numerically plausible while still violating the spec.

Claim C4:
- If design is correct, we should observe: circular boundary cases canonicalize deterministically regardless of update order.
- Measurement method / command / assertion: helper tests apply logically equivalent wraparound updates in different orders and compare normalized sparse-triple outputs.
- Threshold or exact value: positions remain within `1..580076`, duplicates are coalesced, ordering is stable, and repeated normalization is idempotent.
- Why this distinguishes from alternatives: basic process smokes can pass even when rare wraparound cases are wrong.

Claim C5:
- If design is correct, we should observe: loaders fail loudly when pointed at missing or placeholder chromosome artifacts instead of silently seeding broken state.
- Measurement method / command / assertion: probe the current broken `Chromosome_flat.mat` and a missing catalog trace path through the intended loader path.
- Threshold or exact value: the loader must raise or return an explicit invalid-artifact error naming the offending field/path; silent fallback to scalar synthesis is forbidden.
- Why this distinguishes from alternatives: silent fallback is exactly how a full-state surface can appear implemented while staying fictional.

Beat-4 inversion:
- How could these claims pass while design is still wrong? The most likely hole is an implementation tuned to the exact projections and smoke fixtures but not to the true chromosome mutation semantics, especially for region adjacency and rare damage-field combinations.
- Additional guardrail to close that hole: require at least one helper-level round-trip/canonicalization probe and one process-level projection probe per chromosome-primary writer before calling the port complete.

## 7) Open questions for operator

QO1. Can the operator provide the local `Chromosome.m` source or explicitly bless proceeding without it for initial implementation?
- Why unresolved: the task asked for a skim of the properties block and key methods, but no local copy exists in this worktree.
- Options:
  1) Provide the source (or the relevant method excerpts) before implementation.
  2) Proceed from the serializer contract, task prompt method names, and refreshed traces only.
- Recommended default (if no response): proceed, but treat wraparound/merge edge semantics as provisional until boundary-case probes or source excerpts confirm them.
- Risk if wrong: the helper could diverge from MATLAB in exactly the cases that sparse projections do not immediately expose.

QO2. How long should legacy scalar chromosome keys remain first-class compatibility surfaces after pc-t7 starts landing?
- Why unresolved: the design prefers temporary mirrors, but the intended retirement point is a product decision as much as an implementation detail.
- Options:
  1) Keep them only through the chromosome-primary migration window.
  2) Keep them indefinitely as documented derived summaries.
- Recommended default (if no response): keep them through migration only, and mark them as compatibility outputs rather than the primary truth.
- Risk if wrong: indefinite dual truth increases maintenance burden and invites future proxy-based regressions.

QO3. Should refreshed full-state seed data replace `data/karr_fixtures/per_process/Chromosome_flat.mat` in place, or land under a new v2 path?
- Why unresolved: the current path is already consumed by `karr_replication.py`, but its chromosome sparse fields are broken.
- Options:
  1) Replace `Chromosome_flat.mat` in place once the v2 artifact is ready.
  2) Introduce a new path and migrate consumers explicitly.
- Recommended default (if no response): use a new v2 path `data/karr_fixtures/per_process/Chromosome_v2.mat` during rollout, then collapse back to the legacy path only after content probes prove parity. The implementation pre-requisite deliverable is: (a) generate `Chromosome_v2.mat` via a MATLAB script that calls `serialize_chromosome_state` on a freshly-bootstrapped Chromosome object, (b) run the C1 content probe against it, (c) commit the generation script + probe results as the artifact-acceptance gate.
- **Concrete artifact plan (MAJOR-6 fix):** before any implementation code is written, the following must exist:
  - `scripts/matlab/generate_chromosome_v2_fixture.m` — generates the v2 fixture
  - `data/karr_fixtures/per_process/Chromosome_v2.mat` — the refreshed fixture with numeric sparse triples for all 11 fields
  - `tests/vivarium/test_chromosome_fixture_content.py` — a pytest that loads the fixture, runs C1's full validation (no placeholders, no error strings, shapes match, dtypes correct), and fails if any field is broken
  - All 50-seed v2 traces at `per_process_traces_v2_s{000..049}/` already contain real chromosome data (confirmed present per A11-A15)
- Risk if wrong: in-place replacement can surprise existing light-surface readers, while a new path can prolong artifact divergence.

QO4. Is `ReplicationInitiation` expected to perform full chromosome writes in the first pc-t7 implementation, or only consume the new chromosome surface while its primary L2.2 gate remains on `complexs`?
- Why unresolved: the catalog makes `complexs` its primary channel, so the chromosome role is secondary but still important.
- Options:
  1) Include full chromosome writes for initiation in pc-t7 phase 1.
  2) Limit phase 1 to chromosome reads plus compatibility preservation, then add full writes after the polymerization pair settles.
- Recommended default (if no response): include it after `Replication`, once `polymerizedRegions` semantics are already proven by one writer.
- Risk if wrong: deferring too much leaves an unwired process behind; doing it too early may conflate two sources of failure.

QO5. Should `DNADamage` code-port work land before the L2.event harness exists, or wait until that harness can verify it properly?
- Why unresolved: the catalog explicitly keeps `DNADamage` blocked on both L2.event and pc-t7.
- Options:
  1) Land the state port and process code first, with smoke-level verification only.
  2) Wait until event-class verification work is ready to validate it end-to-end.
- Recommended default (if no response): land the chromosome-surface implementation after `DNARepair`, but keep `DNADamage` flagged as verification-incomplete until L2.event exists.
- Risk if wrong: a code path can appear finished while remaining effectively unverified.

QO6. Is whole-field `set` replacement acceptable for sparse chromosome fields under current ensemble wall-time budgets?
- Why unresolved: the design chooses whole-field replacement for touched fields, but no performance probe was run in this task.
- Options:
  1) Accept whole-field `set` initially and revisit only if performance fails.
  2) Require an early performance spike before committing to that updater contract.
- Recommended default (if no response): accept whole-field `set` initially and make performance a checkpoint after `DNASupercoiling` and `Replication`.
- Risk if wrong: a correct design may still strand the implementation on runtime or memory cost.

## 8) Scope boundary

In scope:
1. Define the target chromosome-state data model and its sparse-triple contract.
2. Define how the full chromosome surface integrates with the existing `chromosome` store while preserving compatibility for current light-surface readers.
3. Define artifact gating rules, verification expectations, and rollout sequencing for the five chromosome-primary processes.

Out of scope:
1. Editing production code under `opencell/**`.
2. Editing existing tests or the process catalog.
3. Running MATLAB or regenerating the chromosome artifacts in this task.
4. Designing the full L2.event harness beyond the specific pc-t7 dependency boundary.

Deferred follow-ups:
1. Refresh or sync the serializer-v2 chromosome fixture and chromosome-primary trace bundle into the local repo/worktree.
2. Implement the chromosome helper/store changes and per-process ports.
3. Add projection probes, canonicalization tests, and performance checks once coding begins.

Beat-4 inversion:
- Most likely scope-creep vector: turning this design pass into a disguised implementation plan for L2.event, catalog rewrites, or artifact regeneration mechanics.
- How this doc prevents it: the migration path names those dependencies explicitly but keeps code changes, catalog changes, and MATLAB regeneration outside the scope of this document.

## 9) Migration and rollout path

1. Strategy (revert, parallel-v2, in-place refactor, or hybrid): hybrid rollout on the existing `chromosome` channel, adding full sparse fields and compatibility mirrors together rather than replacing the channel outright.
2. Sequence of steps:
   1) Sync or regenerate a usable serializer-v2 chromosome seed artifact and the chromosome-primary trace bundle, then run content probes before any code trusts them.
   2) Add the Python chromosome helper layer and extend the `chromosome` store/schema with full sparse fields plus metadata and temporary scalar mirrors.
   3) Re-port `DNASupercoiling` first on `linkingNumbers`.
   4) Re-port `Replication`, then `ReplicationInitiation`, on `polymerizedRegions`.
   5) Re-port `DNARepair` on the damage/repair fields.
   6) Re-port `DNADamage` last on the full chromosome surface, while keeping its L2.event verification dependency explicit.
   7) Retire scalar proxy-based projection code only after all chromosome-primary consumers and harness paths are reading the full fields directly.
3. Backout trigger and backout method:
   1) Trigger: refreshed artifacts still fail content probes, helper semantics cannot express required projections, or whole-field replacement blows the ensemble budget.
   2) Method: keep current Karr-light scalar ports as the active path, stop short of removing legacy keys, and revert the new full-field writers without touching the catalog.
4. Compatibility period (if dual paths coexist): full sparse fields and legacy scalar mirrors coexist until every chromosome-primary writer and every relevant downstream reader has switched to the full state and passed its projection/canonicalization checks.

Beat-4 inversion:
- How migration could strand partially-updated code: a port could begin writing one full chromosome field while sibling code still reads only the scalar mirror, creating a split-brain chromosome channel.
- Checkpoint or guard to detect that state: each migrated process should have a parity checkpoint that asserts both the new full-field key and the required compatibility mirror are updated together during the coexistence window.

## 10) Risks and residual unknowns

R1. Local artifact sync is behind the design target.
- Likelihood: high
- Impact: high
- Detection: refreshed-content probe still shows placeholder strings or missing chromosome-primary trace paths.
- Mitigation: make artifact validation a hard precondition for implementation, not a follow-up nicety.
- Owner: operator + implementer

R2. Missing local `Chromosome.m` source leaves edge semantics under-specified.
- Likelihood: high
- Impact: medium-high
- Detection: helper behavior disagrees with later source excerpts or boundary-case traces.
- Mitigation: escalate QO1, add wraparound/merge probes early, and treat those semantics as an explicit risk.
- Owner: operator

R3. Whole-field sparse replacements may be too expensive at ensemble scale.
- Likelihood: medium
- Impact: medium-high
- Detection: per-tick serialization dominates runtime or memory during the first migrated process runs.
- Mitigation: checkpoint performance after `DNASupercoiling` and `Replication`; reopen D4 if needed.
- Owner: implementer

R4. Compatibility mirrors may drift from the full sparse state.
- Likelihood: medium
- Impact: high
- Detection: parity probes show scalar mirrors changing without corresponding full-field deltas, or vice versa.
- Mitigation: make mirror updates process-local and temporary, and forbid projection code from using the mirrors once full fields exist.
- Owner: implementer

R5. Helper design may underfit damage-field complexity.
- Likelihood: medium
- Impact: high
- Detection: `DNARepair` or `DNADamage` cannot express one of the catalog-named projections cleanly with the shared helper.
- Mitigation: sequence the rollout so single-field writers validate the base helper before the damage writers arrive, and reopen D7 if the damage fields expose new primitives.
- Owner: implementer

R6. `DNADamage` may look "done" before event-class verification exists.
- Likelihood: medium
- Impact: medium
- Detection: the code path lands, but the only validation available is smoke/no-op behavior rather than L2.event evidence.
- Mitigation: keep the L2.event dependency explicit in the rollout and status, and do not describe `DNADamage` as fully verified until that harness exists.
- Owner: operator + implementer

## 11) Operator review checklist

1. Did inventory list concrete artifacts and include the missing `Chromosome.m` source, current broken fixture, and commit-history provenance rather than only the obvious code files?
2. Are the cross-surfaces explicit and testable, especially serializer -> artifact -> loader, store -> process, and catalog -> projection boundaries?
3. Does each major decision include options, rationale, inversion, and a falsifier?
4. Are operator decisions clearly separated from implementer assumptions, especially around artifact refresh, mirror lifetime, and missing source?
5. Is scope boundary tight enough to keep this as a chromosome-port design rather than a catalog rewrite or L2.event redesign?

## Acceptance bar checklist

1. [x] Design contract is stated as a system property: section 1 defines success as a durable `chromosome`-channel capability, not a passing test.
2. [x] Inventory manifest is present, machine-checkable, and has at least 8 entries: section 2 lists 18 concrete artifacts using the required `path|kind|role` schema.
3. [x] Interaction-surface map explicitly names cross-component/process/schema/store boundaries: section 3 covers serializer, artifact, catalog, store, helper, and compatibility boundaries.
4. [x] Every major decision has options considered, chosen option, rationale, and Beat-4 inversion: section 5 provides seven decision cards with falsifiers and escalation markers.
5. [x] Falsifiable expected outcomes are stated for the chosen design before implementation: section 6 defines five measurable claims, including artifact rejection and canonicalization behavior.
6. [x] Open questions for operator section has at least 5 entries: section 7 contains six explicit operator questions with defaults and risks.
7. [x] Scope boundary section clearly states in-scope and out-of-scope: section 8 separates design work from code changes, catalog edits, MATLAB runs, and L2.event redesign.
8. [x] Migration/backout path is documented for existing code/artifacts: section 9 specifies hybrid rollout steps, backout triggers/method, and the compatibility window.
9. [x] Risks and residual unknowns are explicit (no silent assumptions): section 10 names six unresolved risks, and section 2 applies rule 5 by probing every schema/fixture/trace artifact and flagging broken or missing content explicitly.
