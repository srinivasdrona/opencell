# ProteinActivation Semantic Audit

Process name: `ProteinActivation`  
Audited files:
- `data/schemas/per_process_wiring/ProteinActivation.yaml`
- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinActivation.m`
- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/@Simulation/evolveState.m`
- `docs/karr_extracts/process/20_ProteinActivation.md`
- `opencell/vivarium/karr_protein_activation.py`
- `opencell/vivarium/karr_composite.py`  
Scope policy: **strict completeness** (row does not declare an explicit non-exhaustive policy; entries labeled "Canonical ... example" are treated as ambiguous, not as an explicit scope contract).

## Deliberate Action Prefix v2

Beat 1 (contract):
- Required behavior: classify ProteinActivation row claims against executable MATLAB and OC semantics for S1-S6.
- Done means: claim-level verdicts are reproducible from cited source lines and use only `VERIFIED|ROW_WRONG|CODE_DEVIATES|MISSING`.

Beat 2 (surface):
- Row surface: `ProteinActivation.yaml` (`methods`, `allocator`, `consume_stoichiometry`, `produce_stoichiometry`, `compartment_routing`, `unit_conversion_chain`, `ordering_constraints`, `deviations`).
- MATLAB surface: `ProteinActivation.m` (`initializeConstants`, `calcResourceRequirements_Current`, `evolveState`, `evaluateActivationRules`) and `Simulation/evolveState.m` allocator/order loop.
- OC surface: `karr_protein_activation.py` (`ports_schema`, `_collect_rule_signals`, `next_update`) and `karr_composite.py` (topology/initial-state wiring).
- Suspect pattern named before verdicting: row anchored to doc extract prose while raw MATLAB exists in checkout.

Beat 3 (expected outcome):
- Deliver a claim table spanning all S1-S6 with deterministic IDs, aggregate verdict totals, and Priority-1 row-remediation items.

Beat 4 (invert / pre-mortem):
- Most likely false-pass mode: accepting prose/extract equivalence and missing executable differences in MATLAB `evaluateActivationRules` (unit conversion + compartment loop) versus OC flattened signal routing.

Beat 5 (act then verify):
- Verified each claim against executable code anchors in MATLAB/OC, plus `bin\oc-py` fixture probes for regulated WID sets (6 regulated proteins in OC fixture-backed process).

PM sanity-check sentence: **PM: I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.**

## Revision-Class Minimum

Design contract sentence:
- Semantic truth being checked: the row must truthfully represent MATLAB ProteinActivation behavior and current OC behavior for consume/produce surfaces, formulas, compartment routing, and allocator engagement.

Decision ledger (non-obvious attribution calls):
- D1: Scope policy attribution.
  - Options: exemplar-scoped vs strict completeness.
  - Chosen: strict completeness.
  - Why: row has no explicit non-exhaustive contract; "canonical example" notes are ambiguous.
- D2: Allocator mode attribution.
  - Options: classify MATLAB as allocator-engaged (method exists) vs bypass (effective no-request pathway).
  - Chosen: effective bypass with `judgment=required`.
  - Why: MATLAB defines `calcResourceRequirements_Current`, but returns zeros and ProteinActivation substrates are protein IDs, not metabolite allocation targets.
- D3: Compartment attribution.
  - Options: accept row cytosol-only routing vs treat OC as compartment projection/merge.
  - Chosen: projection/merge mismatch (`ROW_WRONG`).
  - Why: MATLAB loops over substrate compartment dimension; OC uses flat per-WID stores in process/composite wiring.

Risks (unresolved ambiguity):
- R1: Whether all six regulated proteins are effectively cytosol-only in a given runtime snapshot (could soften practical impact of S5 mismatch).
- R2: Vivarium implicit-port behavior for `inactivatedSubstrates` in composite topology is not explicitly documented in this audit run.
- R3: Rule-threshold parity depends on fixture scaling assumptions; MATLAB concentration conversion versus OC raw counts remains a semantic risk even when branch transfer math matches.

| Claim ID | Category | Row Says | MATLAB Says | OC Says | Verdict | Note |
|---|---|---|---|---|---|---|
| PA-S1-00 | S1 | `consume_stoichiometry` lists 4 entries and labels each as canonical example, but no explicit non-exhaustive scope contract (`ProteinActivation.yaml:109-157`). | Regulated set includes six proteins (`ProteinActivation.m:26-34`), and transition logic applies across the substrate index set (`ProteinActivation.m:360-366`). | OC regulated set is explicitly six proteins and looped exhaustively (`karr_protein_activation.py:20-27`, `250-251`). | ROW_WRONG | Scope declaration is ambiguous for completeness auditing; `judgment=required`. |
| PA-S1-01 | S1 | Consume list contains `MG_101`, `MG_127`, `MG_205`, `MG_409` only (`ProteinActivation.yaml:109-157`). | Consume-side behavior applies to all regulated proteins, including `MG_085_HEXAMER` and `MG_236_MONOMER` (`ProteinActivation.m:26-34`, `364-366`). | OC also executes consume-side branch for all six regulated proteins (`karr_protein_activation.py:20-27`, `250-264`). | MISSING | Missing consume claims for `MG_085_HEXAMER` and `MG_236_MONOMER` under strict policy. |
| PA-S2-01 | S2 | Each listed consume entry is anchored to OC `next_update` transfer logic (`ProteinActivation.yaml:117-157`). | MATLAB consume branch is deactivation (`j = ~i`) and activation-source depletion on true branch (`ProteinActivation.m:361-366`). | OC has real consume deltas in both branches (`karr_protein_activation.py:257-264`). | VERIFIED | Fabrication check passed for listed entries; `judgment=required` (sign/branch-dependent consume semantics). |
| PA-S3-01 | S3 | Produce list contains `MG_101`, `MG_127`, `MG_205`, `MG_409` only (`ProteinActivation.yaml:158-206`). | Produce-side behavior applies to all regulated proteins, including `MG_085_HEXAMER` and `MG_236_MONOMER` (`ProteinActivation.m:26-34`, `361-365`). | OC produce deltas also run across all six regulated proteins (`karr_protein_activation.py:20-27`, `250-264`). | MISSING | Missing produce claims for `MG_085_HEXAMER` and `MG_236_MONOMER` under strict policy. |
| PA-S3-02 | S3 | Listed produce entries claim active/inactive pool writes through `next_update` (`ProteinActivation.yaml:166-206`). | MATLAB produce branches are `substrates(i)+=inactivated(i)` and `inactivated(j)+=substrates(j)` (`ProteinActivation.m:361-366`). | OC emits corresponding positive-side deltas (`karr_protein_activation.py:259-260`, `263-264`). | VERIFIED | Fabrication check passed for listed produce entries; `judgment=required` (sign/branch-dependent produce semantics). |
| PA-S4-01 | S4 | Row claims rule-gated active/inactive toggling (`ProteinActivation.yaml:44-60`). | MATLAB branch formulas are all-or-nothing transfers between active/inactive pools (`ProteinActivation.m:360-366`). | OC branch formulas are mathematically equivalent transfer moves (`karr_protein_activation.py:257-264`). | VERIFIED | Transfer-family formula match holds modulo syntax. |
| PA-S4-02 | S4 | Row `unit_conversion_chain` says no conversion and no known MATLAB↔OC deviation (`ProteinActivation.yaml:233-245`, `339-341`). | MATLAB converts non-stimulus rule signals to concentration before eval and evaluates per compartment (`ProteinActivation.m:370-375`, `379-393`). | OC uses raw scalar values from flat `substrates`/`stimuli` dicts with no concentration conversion (`karr_protein_activation.py:229-238`, `251`). | ROW_WRONG | Row misses a load-bearing formula-family mismatch (signal source/scaling semantics). |
| PA-S5-01 | S5 | Row states same cytosol routing and `shared_pool_projection_merges_compartments: false` (`ProteinActivation.yaml:207-232`, `336`). | MATLAB retains substrate compartments and evaluates/writes by `(substrate, compartment)` matrix indices (`ProteinActivation.m:238-240`, `379-394`, `361-366`). | OC process ports are flat per-WID scalars; composite maps `substrates` to `activation_substrates` without compartment axis (`karr_protein_activation.py:197-204`; `karr_composite.py:2090-2093`, `2239-2240`). | ROW_WRONG | Compartment projection/merge behavior exists in OC relative to MATLAB compartmented tuples; `judgment=required`. |
| PA-S6-01 | S6 | Row allocator mode says `karr=bypass`, `oc_current=bypass` (`ProteinActivation.yaml:79-82`). | MATLAB defines `calcResourceRequirements_Current` as zeros (`ProteinActivation.m:354-356`) and allocator loop applies only metabolite-indexed requirements/allocation (`Simulation/evolveState.m:31-37`, `63-64`), yielding no effective resource request for this protein-state process. | OC has no `requests`/`substrates_allocated` port for ProteinActivation topology (`karr_composite.py:2089-2093`) and no request-calculator consumer entry (`karr_composite.py:1752-1784`). | VERIFIED | Engagement-mode parity is effectively bypass on both sides; `judgment=required` (method exists in MATLAB but is zero-demand). |
| PA-S6-02 | S6 | Row `request_formula.matlab` says ProteinActivation has no `calcResourceRequirements_Current` (`ProteinActivation.yaml:84`). | MATLAB contains `calcResourceRequirements_Current` explicitly (`ProteinActivation.m:354-356`). | OC indeed has no request-calculator path for ProteinActivation (`karr_composite.py:2089-2093`, `2320-2331`). | ROW_WRONG | MATLAB-side method-existence claim is false. |
| PA-S6-03 | S6 | Row says no ProteinActivation-specific ordering exception (`ProteinActivation.yaml:255-260`). | MATLAB randomizes process order with only tRNA-before-translation hard rule (`Simulation/evolveState.m:48-57`). | OC allocation flow is fixed across request calculators, and ProteinActivation is not allocator-coupled in that flow (`karr_composite.py:2334-2357`, `1752-1784`). | VERIFIED | Allocator-coupled ordering claim is effectively non-applicable for this process; `judgment=required`. |

## Aggregate Counts

- VERIFIED: 5
- ROW_WRONG: 4
- CODE_DEVIATES: 0
- MISSING: 2

## Priority-1 Fixes

- `PA-S1-00` (`ROW_WRONG`): make row scope policy explicit (strict vs exemplar) instead of implicit "canonical example" notes.
- `PA-S1-01` (`MISSING`): add consume claims for `MG_085_HEXAMER` and `MG_236_MONOMER` (or explicitly declare exemplar scope).
- `PA-S3-01` (`MISSING`): add produce claims for `MG_085_HEXAMER` and `MG_236_MONOMER` (or explicitly declare exemplar scope).
- `PA-S4-02` (`ROW_WRONG`): correct formula section to acknowledge MATLAB concentration-conversion/per-compartment rule evaluation versus OC raw-signal evaluation.
- `PA-S5-01` (`ROW_WRONG`): correct compartment-routing/deviation fields to represent MATLAB compartmented tuples vs OC flattened projection.
- `PA-S6-02` (`ROW_WRONG`): fix MATLAB request-formula statement to reflect existing zero-return `calcResourceRequirements_Current`.

## Known-Deviation Mapping

- No A1-A4 style deviation IDs are encoded for ProteinActivation in the current row; current mismatches are attributed as row defects (`ROW_WRONG`) or omissions (`MISSING`).

## Auditor Discretion List (`judgment=required`)

- `PA-S1-00` (scope-policy ambiguity)
- `PA-S2-01` (sign-dependent consume semantics)
- `PA-S3-02` (sign-dependent produce semantics)
- `PA-S5-01` (practical impact of flattened compartment routing)
- `PA-S6-01` (zero-demand method existence vs effective bypass classification)
- `PA-S6-03` (allocator-coupled ordering non-applicability)
