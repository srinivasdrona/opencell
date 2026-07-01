# DNADamage Semantic Audit

## Header
- Process name: `DNADamage` (`dna_damage`)
- Header note: `COMPLETE`
- Audited files:
  - `data/schemas/per_process_wiring/DNADamage.yaml`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/DNADamage.m`
  - `docs/karr_extracts/process/04_DNADamage.md`
  - `opencell/vivarium/karr_dna_damage.py`
  - `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m` (allocator/order evidence)
  - `opencell/vivarium/karr_composite.py` (OC wiring evidence)
- Scope policy: `strict completeness` (executed consume/produce semantics, not exemplar-scoped).

## DELIBERATE_ACTION_PREFIX_v2
- Beat 1 (contract): Verify that DNADamage row claims are semantically true against executable MATLAB and OC behavior for consume/produce, formulas, routing, and allocator engagement. Done means claim-level verdicts are reproducible from cited code paths, not from prose anchors alone.
- Beat 2 (surface): Row semantics in `data/schemas/per_process_wiring/DNADamage.yaml`; MATLAB behavior in `DNADamage.m` + simulation allocator loop in `@Simulation/evolveState.m`; OC behavior in `karr_dna_damage.py` + composite wiring in `karr_composite.py`; extract used only as secondary context.
- Beat 3 (expected outcome): A deterministic S1-S6 claim table with allowed verdicts only (`VERIFIED`, `ROW_WRONG`, `CODE_DEVIATES`, `MISSING`), plus aggregate totals and Priority-1 row-fix list.
- Beat 4 (invert / pre-mortem): Most likely false-pass mode is treating radiation-gating or extract prose as equivalent to substrate consumption and allocator bypass; this audit prevents that by grounding claims in `evolveState` writeback lines and allocation injection lines.
- Beat 5 (act/verify): Claims below cite executable branches/formulas; totals and remediation list included.

PM sanity-check sentence: PM: I am assuming row scope is strict completeness over executed semantics (not exemplar snippets); if that assumption is wrong, S1/S3 completeness verdicts should be reclassified.

## Revision-Class Minimum
Design contract sentence: This audit checks the semantic truth of DNADamage wiring claims by testing whether row assertions match MATLAB and OC executed behavior at substrate, formula, compartment, and allocator levels.

### Decision ledger (non-obvious attribution calls)
- D1: Consume/produce completeness basis
  - Choice: Use executed writeback semantics (`this.substrates` updates) rather than raw matrix presence alone.
  - Why: Avoid misclassifying radiation gates as consumptive stoichiometry.
- D2: Radiation entries classification
  - Choice: Treat `UVB_radiation`/`gamma_radiation` as gating factors, not consumed substrates.
  - Why: MATLAB multiplies probabilities by radiation counts (`DNADamage.m:550`, `:485-487`) but does not decrement radiation in substrate writeback (`DNADamage.m:567-568`).
- D3: OC wiring source for routing/allocator claims
  - Choice: Include composite topology evidence from `karr_composite.py`.
  - Why: Per-process code alone can expose read intent, but semantic wiring requires checking whether ports are actually connected.

### Risks (unresolved ambiguity)
- R1: Compartment labels (`cytosol`/`extracellular`) are inferred from row text plus fixture compartment index classes (`metabolite=1`, `stimulus=3`), not from explicit compartment-name arrays in this fixture extract.
- R2: OC topology evidence is from `opencell/vivarium/karr_composite.py`; alternate composites could wire DNADamage differently.
- R3: MATLAB substrate set evidence is materialized via `DNADamage_flat.mat`; if fixture generation drifts from source, re-audit against regenerated constants is needed.

## Claims
| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| DNADAMAGE-S1-01 | S1 | `consume_stoichiometry` includes `H2O` (`DNADamage.yaml:126-158`). | Executed substrate consume path is via `this.substrates += n * reactionSmallMoleculeStoichiometryMatrix(:,j)` (`DNADamage.m:567-568`); `H2O` is consumptive in that matrix family (`DNADamage.m:388-391`). | `next_update` emits chromosome-only update (`karr_dna_damage.py:289-294`). | VERIFIED | Strict executed-consume policy still has MATLAB-consumed `H2O` represented in row; `judgment=required` (radiation gate classification policy). |
| DNADAMAGE-S2-01 | S2 | Row encodes `UVB_radiation`/`gamma_radiation` as consume stoichiometry `-1 per lesion` (`DNADamage.yaml:104-125`). | Radiation multiplies reaction probability (`DNADamage.m:549-553`, `:485-487`), but substrate writeback uses only small-molecule matrix (`DNADamage.m:567-568`), so no executed radiation decrement path. | OC multiplies `rate_per_s` by `gate_count` (`karr_dna_damage.py:250-253`) and never decrements substrates. | ROW_WRONG | Gating was labeled as consumption. |
| DNADAMAGE-S2-02 | S2 | Row explicitly notes H2O entries and OC non-writeback (`DNADamage.yaml:126-158`). | MATLAB consumes H2O through small-molecule stoichiometry in evolve path (`DNADamage.m:567-568`). | OC has no substrate consume writeback in `next_update` (chromosome-only return, `karr_dna_damage.py:289-294`). | CODE_DEVIATES | Row accurately captures MATLAB-vs-OC consume divergence for H2O. |
| DNADAMAGE-S3-01 | S3 | Row produce list is `AD, CSN, GN, THY, DR5P` (`DNADamage.yaml:159-214`). | MATLAB small-molecule products include `AD, CO2, CSN, GN, H, NH3, THY` (product sign in small-molecule matrix family, `DNADamage.m:454-455`, applied by `:567-568`). | OC emits no substrate stoichiometry deltas (`karr_dna_damage.py:289-294`). | MISSING | Row omits MATLAB products `CO2`, `H`, and `NH3` under strict completeness. |
| DNADAMAGE-S3-02 | S3 | Row claims `DR5P` is a produced free-metabolite outcome (`DNADamage.yaml:204-210`). | `DR5P` is assigned into DNA-factorized substrate set (`DNADamage.m:357`, `:366-367`), while evolve writeback uses small-molecule matrix only (`DNADamage.m:567-568`). | OC does not emit metabolite/product deltas (`karr_dna_damage.py:289-294`). | ROW_WRONG | `DR5P` production claim does not match executed MATLAB small-molecule produce path. |
| DNADAMAGE-S3-03 | S3 | Row produce entries for `AD/CSN/GN/THY` retain OC note “does not emit substrate deltas” (`DNADamage.yaml:160-203`). | MATLAB does produce these through small-molecule writeback (`DNADamage.m:454-455`, `:567-568`). | OC is lesion-creation only and returns chromosome update only (`karr_dna_damage.py:289-294`). | CODE_DEVIATES | Row correctly records this implementation deviation. |
| DNADAMAGE-S4-01 | S4 | Row documents OC per-tick `lam = rate_per_s * dt` Poisson sampling (`DNADamage.yaml:281-293`) and partial evolve implementation (`:31-54`). | MATLAB evolves per reaction with `maxReactions` cap (`DNADamage.m:542`), selection probability (`:550-553`), and motif-constrained `setSiteDamaged` (`:559-561`). | OC samples per-kind Poisson events (`karr_dna_damage.py:255-260`) and lacks per-reaction stoich coupling/maxReactions logic. | CODE_DEVIATES | Formula families are not equivalent; row flags narrowed OC semantics. |
| DNADAMAGE-S4-02 | S4 | Row marks `calcResourceRequirements_Current` as not implemented / allocator N/A (`DNADamage.yaml:14-30`, `:77-80`). | MATLAB defines `calcResourceRequirements_Current` with explicit formula `max(0, -reactionSmallMoleculeStoichiometryMatrix * calcExpectedReactionRates())` (`DNADamage.m:469-471`), and rates include radiation factor (`:484-487`). | OC has no corresponding request formula path in process implementation (`karr_dna_damage.py:179-226`, `:228-294`). | ROW_WRONG | MATLAB-side method existence/formula is misattributed in row. |
| DNADAMAGE-S5-01 | S5 | Row sets `compartment_routing` mismatches to false and states no projection merge (`DNADamage.yaml:215-280`, `:374`). | MATLAB separates substrate classes by compartment-index families during constant setup (`DNADamage.m:285-293`), with fixture-local classes showing metabolite-vs-stimulus compartment separation. | OC substrate access is flat WID dictionary (`karr_dna_damage.py:214-217`, `:243-253`) without explicit compartment tuple axis. | ROW_WRONG | OC tuple projection/flattening exists at process surface; `judgment=required` (compartment name inference from index classes). |
| DNADAMAGE-S5-02 | S5 | Row implies DNADamage substrate routing is active through shared substrate surface (`DNADamage.yaml:220`, `:225`, `:293`). | MATLAB wiring supplies substrates/stimuli each cycle before evolve (`@Simulation/evolveState.m:30`, `:68-70`). | In `karr_composite.py`, `karr_dna_damage` topology maps only `"chromosome"` (`karr_composite.py:2129-2131`), so shared substrate routing is absent in this composition. | ROW_WRONG | Semantic wiring claim depends on composition; `judgment=required` if auditing a different composite. |
| DNADAMAGE-S6-01 | S6 | Row allocator mode says `karr: bypass`, `oc_current: bypass` (`DNADamage.yaml:73-80`). | MATLAB simulation computes `calcResourceRequirements_Current` for each process and injects allocations before evolve (`@Simulation/evolveState.m:31`, `:37`, `:63-70`). | OC DNADamage has no `requests`/`substrates_allocated` ports (`karr_dna_damage.py:179-226`), and no allocation consumer registration (`karr_composite.py:1752-1784`). | ROW_WRONG | MATLAB is allocator-engaged; OC is bypassed. |
| DNADAMAGE-S6-02 | S6 | Row says no DNADamage-specific hard ordering exception (only tRNA<Translation canonical note, `DNADamage.yaml:299-304`). | MATLAB process evaluation is randomized with only tRNA-vs-Translation constraint (`@Simulation/evolveState.m:48-57`). | OC request/allocation flow has explicit step edges, while DNADamage has no allocator-coupled request edge (`karr_composite.py:2335-2357`, `:2129-2131`). | VERIFIED | No DNADamage-specific allocator-coupled order rule is encoded; `judgment=required` (runtime scheduling models differ). |

## Aggregate Counts
- VERIFIED: 2
- ROW_WRONG: 6
- CODE_DEVIATES: 3
- MISSING: 1

## Priority-1 fixes
- `DNADAMAGE-S2-01` (`ROW_WRONG`): Reclassify `UVB_radiation` and `gamma_radiation` from consume stoichiometry to radiation-gating inputs (non-consumptive in executed paths).
- `DNADAMAGE-S3-01` (`MISSING`): Add missing MATLAB-produced substrates `CO2`, `H`, and `NH3` to `produce_stoichiometry` (or explicitly declare exemplar scope policy).
- `DNADAMAGE-S3-02` (`ROW_WRONG`): Remove or qualify `DR5P` as free-metabolite product in executed MATLAB evolve path.
- `DNADAMAGE-S4-02` (`ROW_WRONG`): Correct row method metadata to acknowledge MATLAB `calcResourceRequirements_Current` implementation and formula.
- `DNADAMAGE-S5-01` (`ROW_WRONG`): Update compartment-routing claim to acknowledge OC flat substrate projection semantics.
- `DNADAMAGE-S5-02` (`ROW_WRONG`): Align row OC routing claims with composite topology actually used (or scope row to process-local code only, explicitly).
- `DNADAMAGE-S6-01` (`ROW_WRONG`): Correct allocator mode to `karr: request/grant engaged` vs `oc_current: bypass`.

## Known-deviation mapping (optional)
- `DD-DEV-01` -> `DNADAMAGE-S2-02`: H2O consume present in MATLAB, omitted in OC lesion-only port.
- `DD-DEV-02` -> `DNADAMAGE-S3-03`: AD/CSN/GN/THY products present in MATLAB, omitted in OC lesion-only port.
- `DD-DEV-03` -> `DNADAMAGE-S4-01`: MATLAB reaction-wise damage kinetics vs OC per-kind Poisson simplification.

## Auditor discretion list
- `DNADAMAGE-S1-01` (consume scope policy and radiation classification).
- `DNADAMAGE-S5-01` (compartment-name inference from fixture index classes).
- `DNADAMAGE-S5-02` (composition-dependent routing claim).
- `DNADAMAGE-S6-02` (cross-runtime ordering comparability).
