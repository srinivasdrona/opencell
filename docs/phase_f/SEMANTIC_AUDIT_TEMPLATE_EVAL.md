# Semantic Audit Template Fitness Evaluation

Process used as the representative non-Metabolism case:
- `ProteinTranslocation`

Sources reviewed:
- `docs/prompts/SEMANTIC_AUDIT_TEMPLATE.md`
- `docs/prompts/PROMPT_semantic_audit_TEMPLATE.md`
- `docs/phase_f/audits/Metabolism_semantic_audit.md`
- `data/schemas/per_process_wiring/ProteinTranslocation.yaml`
- `data/m1_sources/WholeCell/src/+edu/+stanford/+covert/+cell/+sim/+process/ProteinTranslocation.m`
- `opencell/vivarium/karr_protein_translocation.py`
- `docs/phase_f/sut_audits/ptransloc_oc_vs_karr.md`
- `docs/karr_extracts/process/22_ProteinTranslocation.md`

PM sanity-check:
- I am assuming row scope (full vs exemplar) is explicit; if not, completeness verdicts may be mis-attributed.

## Q1

S1 and S2 are mostly mechanical for `ProteinTranslocation`: the row only claims ATP, GTP, and H2O consumption, and both Karr and OC expose those same substrate names in obvious places (`ProteinTranslocation.m:318-368`, `karr_protein_translocation.py:352-442`).  
S3 is also mostly mechanical because the produce side is the aggregate ADP/GDP/PI/H writeback from the same hydrolysis ledger (`ProteinTranslocation.m:362-368`, `karr_protein_translocation.py:431-442`).  
S4 is where mini starts needing real judgment: Karr is a per-copy, globally randomized, break-on-first-failure loop, while OC is a batched species-phase algorithm with allocator-granted budget and raw enzyme counts (`ProteinTranslocation.m:324-347`; `karr_protein_translocation.py:387-442`).  
Deciding whether that gap is `CODE_DEVIATES`, `ROW_WRONG`, or a deliberate reimplementation is not a grep problem; it requires interpreting what the row is claiming and what level of equivalence the template expects.  
S5 is mechanically simple for the substrate stoichiometry itself because every substrate in the row is cytosolic, but it becomes judgment-sensitive if the auditor starts mixing protein-location routing with substrate compartment routing.  
S6 is the weakest point for mini: the row admits MATLAB demand is inferred from extracts and fixture scalars, while OC reads `substrates_allocated` and floors current-pool values before comparing against need (`ProteinTranslocation.yaml:78-81, 116-145`; `karr_protein_translocation.py:302-305, 314-355`).  
That means the audit has to distinguish provenance from semantics, not just confirm that strings exist.  
The most likely mistake is silent overconfidence: marking an inferred or ambiguous claim `VERIFIED` instead of `judgment=required`, especially in S4/S6.  
For this process, mini can follow the structure, but it cannot reliably self-police the semantic boundary between “same enough,” “row wrong,” and “code deviates.”  

## Q2

Using a representative 18-claim row audit for this process, I estimate:
- Pure mechanical: 7/18 = 39%
- Mostly mechanical: 4/18 = 22%
- Judgment required: 7/18 = 39%

The judgment-heavy slice is driven by S4 and S6, plus any claim that depends on the indirect MATLAB provenance path instead of a raw local `.m` body.  
That puts judgment-required clearly above the 30% danger line, so the template is not reliable enough for a 27-process fleet without further constraints.  

## Q3

1. Indirect-source overconfidence in S4/S6.
   - Check(s): formula match and allocator engagement.
   - Failure shape: mini treats doc extracts and parity notes as if they were the same as a locally available executable MATLAB body, then emits `VERIFIED` without `judgment=required`.
   - Frequency: about 1 in 4 complex rows, higher whenever the raw MATLAB file is absent or only partially cited.

2. Row/code attribution confusion around reimplementation.
   - Check(s): S4 and S6.
   - Failure shape: mini flips `CODE_DEVIATES` and `ROW_WRONG`, especially for batching-vs-per-copy differences and allocator-floor behavior (`ProteinTranslocation.m:324-347`; `karr_protein_translocation.py:387-442`).
   - Frequency: about 1 in 3 complex rows.

3. Scope drift and hidden completeness assumptions.
   - Check(s): S1, S3, and S5.
   - Failure shape: mini silently assumes strict completeness when the row is exemplar-scoped, or misses implicit compartment-projection behavior and produces the wrong omission label.
   - Frequency: about 1 in 5 rows.

## Q4

The template is close, but not ready for mini as-is.

Concrete improvements:
- Add an explicit source hierarchy: raw MATLAB > checked-in extract > parity audit note. If the raw MATLAB body is absent, dependent claims should default to `judgment=required` or `BLOCKED`, not be inferred silently.
- Add a prefilled claim skeleton per process with stable claim IDs for S1-S6 and an explicit source-type field so indirect evidence cannot masquerade as executable code.
- Add worked examples for common edge cases: inferred request formulas, allocator floor vs need, batching-vs-per-copy divergence, and sign-dependent stoichiometry.
- Add a short command recipe block for each check family so the mechanical subset is truly mechanical, not “find it by reading the file until it looks right.”
- The current `judgment=required` fallback is necessary, but it is not sufficient because it only labels ambiguity after interpretation; it does not prevent provenance mistakes up front.

## Q5

**RED**

Mini can follow the template structure, but the representative `ProteinTranslocation` case already pushes too much work into judgment-heavy territory: S4 and S6 require semantic attribution across a per-copy Karr loop, a batched OC port, and allocator behavior that is only partially grounded in local executable source (`ProteinTranslocation.m:307-368`; `karr_protein_translocation.py:307-442`; `ProteinTranslocation.yaml:78-81, 116-145`).  
With an estimated 39% judgment-required claims, I do not expect mini to stay below the requested false-positive/false-negative envelope across a 27-process fleet.  
The template would benefit from stronger provenance rules and claim scaffolding, but in its current form it will generate too much semantic noise for fleet-scale delegation.
