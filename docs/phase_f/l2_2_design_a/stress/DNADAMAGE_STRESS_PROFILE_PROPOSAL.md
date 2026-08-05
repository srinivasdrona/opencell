# DNADamage synthetic mechanism-fidelity profile

**Status:** preregistered predictions frozen (2026-06-14); OC-side canary
EXECUTED 2026-08-05 (N=50 seeds x M=20 ticks); still non-gating.

## Execution update (2026-08-05)

The canary described below has been executed:
`scripts/dna_damage_mechanism_canary.py` -> checked-in result
`DNADAMAGE_MECHANISM_CANARY_RESULT.json`. It runs the real
`KarrDNADamageProcess.next_update` across the frozen 50x20 design under
`no_stimulus`, `uvb_mechanism`, and `gamma_mechanism`, and compares OC's
empirical firing/payload against the Karr-analytical (fixture-derived, never
fabricated) expectation for every `primary_projection` channel in the
catalog. Result: both stimulus conditions verdict `MECHANISM_MISMATCH` (OC's
lumped per-kind Poisson rate model diverges sharply from Karr's per-reaction
`calcExpectedReactionRates` formula -- UVB overfires ~988/1000 pooled ticks
vs an analytical expectation of ~97; gamma underfires 0/1000 vs an
analytical expectation of ~96), `no_stimulus` stays `NOT_APPLICABLE` (never
scored as a pass), and `hollidayJunctions` is reported
`NOT_GATEABLE_MISSING_OC_CHANNEL` (OC's `ports_schema()` does not wire it).
This is real, non-trivial, source-backed OC-side evidence -- it is still
explicitly **not** a claim about the biological L2.2 event-class gate, which
remains `MISSING_EVIDENCE` in `evidence_index.json` because no
NONTRIVIAL (stimulus-conditioned) empirically-executed Karr trace exists
under any stimulus condition (no MATLAB toolchain available in this
environment). Three DNADamage traces DO exist on disk
(`per_process_traces`, `per_process_traces_v2`, `dnadamage_fullcycle`) and
have been individually scanned and classified: all three carry only
ambient radiation-substrate values (`UVB_radiation` == 0.0,
`gamma_radiation` ~= 2.8e-11 constant across every tick) -- 9-12 orders of
magnitude below the frozen spec's own injected doses -- so every one of
them is classified `vacuous_no_stimulus`, not `stimulus_conditioned`. The
precise blocker is therefore "no NONTRIVIAL stimulus-conditioned Karr
trace", never "no files exist". See the result JSON's
`biological_l2_2_event_class_gate` for the precise required extraction
contract. `PROCESS_CATALOG.yaml`'s DNADamage `notes`/`blocked_on` fields have
been corrected accordingly (the prior "L2.2 GREEN. blocked_on cleared." note
was a zero==zero quiescent-replay artifact and has been retracted).

## Remediation update (2026-08-05, review follow-up)

A review pass identified 6 required follow-ups, all addressed on the same
branch prior to merge:

1. **Rule 8 fix.** `KarrDNADamageProcess` previously carried a dead
   `_load_trace_kind_rates`/`trace_path`/`use_trace_rates_if_available`
   mechanism that attempted to override `kind_rates_per_s` from a per-tick
   oracle trace (`DNADamage_100ticks.mat`); it was silently inert only
   because `scipy.io.loadmat` cannot parse the v7.3/HDF5 trace format --
   a latent violation, not an absent one. This mechanism has been removed
   entirely from production; `kind_rates_per_s` is now always exactly the
   canonical default or an explicit caller-supplied override. A regression
   test (including a `_100ticks` source-text scan) guards against
   reintroduction, and the canary result now records
   `kind_rates_provenance` confirming no trace-rate override path exists or
   was used.
2. **Trace inventory broadened + correctly classified.** The blocker probe
   now scans `per_process_traces`, `per_process_traces_v2`, and
   `dnadamage_fullcycle` (previously only the nonexistent
   `per_process_traces_v2_event_s*` glob was checked) and classifies each
   found trace as `vacuous_no_stimulus` or `stimulus_conditioned` against
   the frozen spec's own injected doses, rather than reporting a bare
   found/not-found boolean.
3. **Structurally-absent fields are now schema-derived**, computed live
   from `KarrDNADamageProcess({}).ports_schema()["chromosome"]` rather than
   a hardcoded frozenset.
4. **Fire predicate restricted to each condition's
   `allowed_chromosome_fields`** (per the frozen spec's own
   `support_design.fire_predicate` and per-condition field lists), so an
   unrelated, unradiated pathway (e.g. spontaneous depurination writing
   `abasicSites`) can never be silently pooled into a stimulus condition's
   fire count. Any such out-of-scope nonzero delta is now measured and
   explicitly flagged rather than hidden.
5. **`execution_status` reconciled without a biological claim.** The
   frozen spec's `execution_status` (`PREREGISTERED_NOT_EXECUTED`) describes
   only whether a real Karr/MATLAB run has ever executed -- it has not, and
   this remains unchanged and true. A new, additive
   `mechanism_canary_status` field (and a matching
   `oc_mechanism_canary_execution_status`/
   `oc_mechanism_canary_is_biological_l2_2_evidence` pair in the result
   JSON) now separately and explicitly tracks that the OC-side mechanism
   canary itself has executed, while stating plainly that this is not
   biological L2.2 evidence.
6. **Provenance.** A new, superseding (not amended) provenance log entry
   references the corrected commit for this remediation.

The local Karr source contains no nonzero calibrated UVB or gamma condition:
the concrete condition fixtures set radiation to zero. Therefore this profile
does **not** claim a biological dose or a cell-phenotype stress response.

It instead defines two source-valid mechanism conditions by injecting only
Karr's existing `UVB_radiation` or `gamma_radiation` substrate. Each value is
derived from `DNADamage.m::calcExpectedReactionRates` and the fixture so the
50-seed x 20-tick cohort has 100 expected pooled **damaged-site events**.
The gate's repeated-firing count is seed-tick incidence, for which the
preregistered expectations are 97.22 UVB and 96.02 gamma fire ticks
(1.94x/1.92x the floor). Values are frozen in
`DNADAMAGE_SYNTHETIC_MECHANISM_SPEC.json` before any MATLAB execution.

The negative control remains correctly quiescent and cannot pass by
zero-equals-zero. Stimulus conditions must reach Karr support or refuse.
Comparisons are distributional, using Karr-only seed-cluster nulls; exact
claims are limited to directionality, field mapping, bounds and separation
from DNARepair. Per-kind incidence is gateable only for preregistered kinds
whose own expected support clears the floor; unsupported rare kinds remain
descriptive rather than becoming zero-equals-zero passes. Gamma may write
`damagedBases` or `strandBreaks`; UVB writes `intrastrandCrossLinks`.
A fired tick is defined as a **net nnz increase** in those allowed fields;
an in-place subtype conversion at an existing site is deliberately not a
fire.

This work can support a later `CONDITION_GATED_CANDIDATE` decision. It cannot
change the current DNADamage verdict, unblock L2.5, or support L5 phenotype
claims. Live catalog, registry and evidence-index edits remain serialized and
are not part of this preregistration.
