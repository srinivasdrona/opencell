# Per-Process Wiring DB Schema

## DAP Intent

Contract (Beat 1):
- Required behavior: each process row must capture integration-layer wiring that the per-process TOMLs do not, including method correspondence, allocator requests and bypasses, stoichiometry, compartment routing, unit conversion, inter-process dependencies, ordering constraints, source anchors, and fixture provenance.
- Why this matters: the current per-process TOMLs are state-shape catalogs; they do not expose the wiring defects that let the lower-rung greens proceed while chassis-layer integration bugs accumulated.
- Done = property statement: for any process, a reviewer can reconstruct the process's wiring contract from the row alone and mechanically compare it to the MATLAB source and the current OC port.

Beat-4 inversion:
- Most plausible "looks right, is wrong" failure mode: the schema becomes a prettier copy of the TOML catalog and still omits the wiring surfaces that matter for allocator, LP, routing, and ordering checks.
- What would falsify this contract statement: if a row cannot be diff-checked against source anchors to answer "what does this process request, consume, produce, bypass, and route?" without opening another design doc.

PM/operator sanity-check:
- I am assuming the wiring DB should be YAML, one file per process, and string formulas are acceptable as long as the schema forces anchors and explicit deviation flags; if the operator wants executable ASTs instead, this revision is the wrong shape.

## 1) Design contract

Contract:
- Required behavior: the wiring DB must be the first place a reviewer looks to answer integration-layer questions about a Karr process. It must preserve the process identity, the MATLAB<->OC method map, allocator request logic, allocator bypasses, per-tick consume/produce stoichiometry, compartment routing, unit-conversion chain, inter-process dependencies, ordering constraints, source anchors, and fixture provenance.
- Why this matters: the existing `data/schemas/per_process/*.toml` files already answer "what state shapes exist?" but not "how does the process wire into the chassis?". The missing wiring surface is exactly what allowed Metabolism's LP-bounds source, compartment projection, and allocator assumptions to drift without being obvious from the catalog rows.
- Done = property statement: a row is done when a reviewer can answer, from the row alone, all 10 required schema questions and the 4 audit traceability questions. The row must make the current OC behavior and the Karr reference behavior comparable, not merely descriptive.

Beat-4 inversion:
- Most plausible "looks right, is wrong" failure mode: the row contains the right headings but the values are too coarse to expose the bug class, so a later checker can still wave through a broken allocator, a merged compartment projection, or a clipped writeback asymmetry.
- What would falsify this contract statement: if a row cannot be used to grep the exact MATLAB and OC anchors for a claimed request formula, routing rule, or deviation, then the contract is too weak.

## 5) Decision ledger

Decision D1
- Question: should the wiring DB be TOML or YAML?
- Options considered:
  1) TOML, to match `data/schemas/per_process/*.toml`.
  2) YAML, to carry nested formula blocks, anchors, and deviation notes without awkward escaping.
- Chosen option: YAML.
- Rationale: the wiring rows need nested structures (method maps, source-anchor blocks, unit-conversion chains, deviation notes). YAML is easier to read and to review when the payload is mostly descriptive but still structured.
- Tradeoffs accepted: YAML is more permissive and can drift into style noise if the schema is not strict enough.
- Beat-4 inversion (how chosen option could be wrong): YAML could become a dumping ground for prose unless the schema stays explicit about field names, required keys, and enum constraints.
- Falsifier (what evidence would force reopening D1): if later rows require heavy quoting or repeated escaping just to preserve formulas and anchors, or if reviewers cannot keep the nested shape stable, move to TOML-plus-generated sidecar.
- Operator escalation needed? no

Decision D2
- Question: should the DB live in one file per process or one combined file?
- Options considered:
  1) One file per process.
  2) Single combined DB for all 28 processes.
- Chosen option: one file per process.
- Rationale: it matches the existing per-process catalog pattern, keeps review diffs local, and lets a single process row be updated without churning a giant shared file. It also makes the row the unit of extraction, provenance, and red/green comparison.
- Tradeoffs accepted: cross-process grepping becomes a little harder, so later work may want a generated index or manifest.
- Beat-4 inversion (how chosen option could be wrong): one-per-process can hide cross-row inconsistencies until late if no index or checker exists.
- Falsifier (what evidence would force reopening D2): if cross-row consistency becomes the dominant review cost, add a generated combined index without changing the row format.
- Operator escalation needed? no

Decision D3
- Question: should formulas be string-typed symbolic expressions or structured ASTs?
- Options considered:
  1) String-typed symbolic formulas.
  2) Structured ASTs.
- Chosen option: string-typed symbolic formulas.
- Rationale: the first job of this DB is auditability, not execution. Strings keep MATLAB-symbolic expressions grep-friendly and easy to compare against anchors, while still allowing the schema to require explicit source links and enum-checked fields.
- Tradeoffs accepted: strings are less machine-executable and can hide precedence errors if later tools do not parse them.
- Beat-4 inversion (how chosen option could be wrong): a string formula can look precise while quietly being ambiguous to a future parser or reviewer.
- Falsifier (what evidence would force reopening D3): if a later checker cannot reliably normalize the formulas, or if authors start encoding many implicit operators in comments, move to a structured expression tree.
- Operator escalation needed? no

Decision D4
- Question: how should MATLAB<->OC method correspondence be encoded?
- Options considered:
  1) Flat list of method pairs.
  2) Nested under method names.
  3) Separate `method_map.yaml` cross-reference.
- Chosen option: nested under method names.
- Rationale: the row should answer "where is this method wired?" without a second lookup. Nesting keeps the MATLAB method, the OC symbol, and the status/notes together, which is the right shape for a per-process wiring row.
- Tradeoffs accepted: cross-process method comparison is less convenient than a single normalized crosswalk file.
- Beat-4 inversion (how chosen option could be wrong): nested names can conceal aliasing or missing methods if later authors invent inconsistent labels.
- Falsifier (what evidence would force reopening D4): if method names diverge too much across rows, generate a normalized index as a derivative artifact rather than changing the row contract.
- Operator escalation needed? no

Decision D5
- Question: what versioning policy should govern schema evolution?
- Options considered:
  1) No explicit versioning, rely on git history.
  2) A single global version with hand-edited compatibility notes.
  3) Per-row `schema_version` with semver-style additive minors and breaking majors.
- Chosen option: per-row `schema_version` with semver-style evolution.
- Rationale: rows will be written in batches by different models over time. A row-local version lets later rows evolve without forcing a simultaneous rewrite of every existing file.
- Tradeoffs accepted: the schema author must be disciplined about compatibility boundaries and sentinel values such as `NOT_IMPLEMENTED`.
- Beat-4 inversion (how chosen option could be wrong): a lax version policy could let incompatible rows masquerade as valid and make later auditing impossible.
- Falsifier (what evidence would force reopening D5): if a breaking field change can be introduced without a version bump and without a visible parser failure, the policy is not strict enough.
- Operator escalation needed? yes, if a future row requires a breaking shape change

## 10) Risks

R1. Stale rows when MATLAB or OC code changes
- Likelihood: high, because the wiring DB is derived from source anchors that will drift as ports continue.
- Impact: high, because stale anchors can turn a useful audit row into a false green.
- Detection: compare row anchors against current file:line anchors and require a freshness check when the referenced code moves.
- Mitigation: keep the schema row local to the process, require anchor updates in the same change as code edits, and treat stale anchors as a review failure.
- Owner: the process port maintainer plus the wiring-row maintainer.

R2. Manual-extraction bias
- Likelihood: medium to high, because different models will author rows with different levels of completeness.
- Impact: high, because one partial row can hide a missing consume/produce edge or an allocator bypass.
- Detection: require the self-audit table, compare row fields against the source anchors, and flag missing required sections.
- Mitigation: use the same field order and the same canonical example shape for every process; later, add a checker that scores completeness per row.
- Owner: the extraction batch owner.

R3. Cross-row consistency drift
- Likelihood: medium, because `produces_inputs_for` and `consumes_outputs_of` must be reciprocal across 28 independent files.
- Impact: high, because a broken reciprocal link makes the DB internally inconsistent even if each row looks plausible.
- Detection: a future cross-row checker can diff the inverse edges and flag any asymmetric pair.
- Mitigation: keep each row explicit about both directions and do not infer reciprocity silently.
- Owner: the future cross-row consistency checker, not the row author.

## Self-Audit

| Schema requirement | SCHEMA.md section | _schema field path | Metabolism.yaml example |
|---|---|---|---|
| 1. Process identity & method correspondence | §1, §5(D4) | `process.*`, `methods.*` | `process.name`, `process.matlab_class`, `methods.calcResourceRequirements_Current`, `methods.evolveState`, `methods.calcFluxBounds` |
| 2. Allocator integration (requests + bypasses) | §1, §5(D1), §10(R2) | `allocator.mode`, `allocator.request_formula`, `allocator.requests`, `allocator.bypasses` | `allocator.mode.karr`, `allocator.mode.oc_current`, `allocator.requests`, `allocator.bypasses` |
| 3. Consume stoichiometry | §1 | `consume_stoichiometry[]` | `consume_stoichiometry[GLC]`, `consume_stoichiometry[O2]`, `consume_stoichiometry[ATP]` |
| 4. Produce stoichiometry | §1 | `produce_stoichiometry[]` | `produce_stoichiometry[ADP]`, `produce_stoichiometry[PI]`, `produce_stoichiometry[H]` |
| 5. Compartment routing | §1, §10(R3) | `compartment_routing[]` | `compartment_routing[GLC]`, `compartment_routing[O2]`, `compartment_routing[ATP]` |
| 6. Unit conversion chain | §1 | `unit_conversion_chain.*` | `unit_conversion_chain.steps[]` |
| 7. Inter-process dependencies | §1 | `dependencies.produces_inputs_for`, `dependencies.consumes_outputs_of` | `dependencies.produces_inputs_for[]`, `dependencies.consumes_outputs_of[]` |
| 8. Ordering constraints | §1, §5(D5) | `ordering_constraints.hard_before`, `ordering_constraints.hard_after`, `ordering_constraints.soft_before`, `ordering_constraints.soft_after` | `ordering_constraints.hard_before[]`, `ordering_constraints.hard_after[]` |
| 9. Source anchors (matlab + oc) | §1, §5(D4) | `source_anchors.matlab_blocks`, `source_anchors.oc_blocks` | `source_anchors.matlab_blocks.resource_req`, `source_anchors.oc_blocks.dynamic_update`, `source_anchors.oc_blocks.flat_projection` |
| 10. Knowledge-base provenance | §1, §10(R1) | `provenance.fixture_files`, `provenance.kb_version`, `provenance.extraction_date_utc` | `provenance.fixture_files[]`, `provenance.kb_version` |
| A1 audit traceability (allocator cap) | §5(D1), §10(R1) | `allocator.request_formula`, `methods.calcResourceRequirements_Current`, `deviations.known_deviations[]` | `allocator.request_formula.matlab`, `methods.calcResourceRequirements_Current.oc.source` |
| A2 audit traceability (process order) | §5(D5), §10(R3) | `ordering_constraints.*` | `ordering_constraints.hard_before[]`, `ordering_constraints.soft_before[]` |
| A3 audit traceability (LP bounds source) | §5(D1), §10(R1) | `deviations.lp_bounds_source.karr`, `deviations.lp_bounds_source.oc_current` | `deviations.lp_bounds_source.karr`, `deviations.lp_bounds_source.oc_current` |
| A3b audit traceability (consumption clip) | §1, §10(R1) | `deviations.known_deviations[]`, `source_anchors.oc_blocks.writeback_clip` | `deviations.known_deviations[]`, `source_anchors.oc_blocks.writeback_clip` |
| A4 audit traceability (compartment merge) | §1, §10(R3) | `deviations.shared_pool_projection_merges_compartments`, `source_anchors.oc_blocks.flat_projection` | `deviations.shared_pool_projection_merges_compartments`, `source_anchors.oc_blocks.flat_projection` |
