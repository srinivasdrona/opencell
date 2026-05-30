# D-Residue Clusters for Wave 10+ Planning

## Scope and provenance

- This pass uses the latest branch-side `L2_STATUS` snapshot from git object `10ef0c2` (file removed from current checkout but present in history), then applies the subsequent `ProteinFolding` GREEN closure (`a2b3285`) to reach the current **9 GREEN / 19 RED** state.  
  Evidence: `10ef0c2:docs/phase_e/L2_STATUS.md:22`, `a2b3285` commit message line 5.
- Pattern taxonomy baseline comes from `L2_STATUS` where A/B/C are closed and D is the remaining bucket.  
  Evidence: `10ef0c2:docs/phase_e/L2_STATUS.md:62-65`.
- L2.0 observable-surface context comes from `docs/phase_e/L2_0_SCHEMA_AUDIT.md`.  
  Evidence: `docs/phase_e/L2_0_SCHEMA_AUDIT.md:25-52`.
- Sweep WIP activity is taken from `git --no-pager log --oneline --grep "[wip]"` on `audit/l2-1-sweep-v2`.  
  Evidence: `l2-1-sweep-v2 log(wip):1-17`.
- Prior-wave worktree presence is taken from `git worktree list`.  
  Evidence: `git worktree list:1-61`.

---

## 1) Census (19 RED D-residues)

### WIP detection rule used in this table
- `yes` means at least one process-specific `[wip]` commit exists in the sweep branch snapshot (`dna-supercoiling`, `replication-initiation`, `translation`, `rna-modification`, `rna-processing`, `protein-processing-ii`).  
  Evidence: `l2-1-sweep-v2 log(wip):1-17`.
- `no` means no process-specific `[wip]` hit in that snapshot.

### Table

| Process | First-mismatch tick | Observable | Sign | Magnitude \|diff\| | Already has WIP? | Worktree exists from prior wave? |
|---|---:|---|---:|---:|---|---|
| ChromosomeCondensation | 0 | substrates | + | 3 | no | yes (`wave9-chromcond`) |
| DNASupercoiling | 0 | enzymes | + | 3 | yes (`946509a`, `58e851d`) | yes (`fix-dna-supercoil`, `dna-supercoil-deep`, `l2-dna-supercoiling`) |
| FtsZPolymerization | 0 | substrates | - | 2 | no | yes (`wave9-ftsz`) |
| Metabolism | 0 | substrates (ADP) | + | 3622 | no | no (no process-named prior-wave worktree) |
| ProteinActivation | 28 | substrates | + | 1 | no | no (no process-named prior-wave worktree) |
| ProteinDecay | 3 | substrates | - | 6 | no | yes (`probe-bug9-decay`) |
| ProteinModification | 43 | substrates (real biology drift) | ? | n/r in `L2_STATUS` | no | yes (`fix-pmod-allocator-zero`) |
| ProteinProcessingII | 2 | unprocessedMonomers | + | 1 | yes (`3524332`) | yes (`fix-pp2-enzyme-seed`, `wave8-pp2`) |
| Replication | 0 | substrates | + | 46 | no | yes (`l2-replication`) |
| ReplicationInitiation | 0 | boundEnzymes | - | 2 | yes (`e3cfb21`) | yes (`fix-rep-init`) |
| RibosomeAssembly | 96 | substrates | + | 2 | no | no (no process-named prior-wave worktree) |
| RNADecay | 0 | substrates | - | 20 | no | yes (`wave9-rnadecay`) |
| RNAModification | 6 | substrates (AMP) | + | 1 | yes (`dd91335`, `06595c2`, `9acdb32`, `505cfff`) | yes (`l2-rna-modification`, `wave8-rnamod`) |
| RNAProcessing | 4 | processedRNAs | + | 1 | yes (`e159c5b`) | yes (`fix-rna-processing`, `swarm-dead-rna_processing`) |
| TerminalOrganelleAssembly | 6 | substrates | - | 1 | no | no (no process-named prior-wave worktree) |
| Transcription | 0 | substrates | - | 27 | no | yes (`swarm-dead-rc_transcription`) |
| TranscriptionalRegulation | 15 | enzymes | + | 1 | no | no (no process-named prior-wave worktree) |
| Translation | 0 | enzymes | - | 12 | yes (`bff5585`, `8baa161`) | yes (`fix-translation`, `swarm-dead-rc_translation`) |
| tRNAAminoacylation | 0 | substrates | - | 37 | no | yes (`l2-trna-aminoacylation`) |

### Fingerprint sources for Section 1 rows

- ChromosomeCondensation: `10ef0c2:docs/phase_e/L2_STATUS.md:29`
- DNASupercoiling: `10ef0c2:docs/phase_e/L2_STATUS.md:34`
- FtsZPolymerization: `10ef0c2:docs/phase_e/L2_STATUS.md:35`
- Metabolism: `10ef0c2:docs/phase_e/L2_STATUS.md:38`
- ProteinActivation: `10ef0c2:docs/phase_e/L2_STATUS.md:39`
- ProteinDecay: `10ef0c2:docs/phase_e/L2_STATUS.md:40`
- ProteinModification: `10ef0c2:docs/phase_e/L2_STATUS.md:42`
- ProteinProcessingII: `10ef0c2:docs/phase_e/L2_STATUS.md:44`
- Replication: `10ef0c2:docs/phase_e/L2_STATUS.md:46`
- ReplicationInitiation: `10ef0c2:docs/phase_e/L2_STATUS.md:47`
- RibosomeAssembly: `10ef0c2:docs/phase_e/L2_STATUS.md:48`
- RNADecay: `10ef0c2:docs/phase_e/L2_STATUS.md:49`
- RNAModification: `10ef0c2:docs/phase_e/L2_STATUS.md:50`
- RNAProcessing: `10ef0c2:docs/phase_e/L2_STATUS.md:51`
- TerminalOrganelleAssembly: `10ef0c2:docs/phase_e/L2_STATUS.md:52`
- Transcription: `10ef0c2:docs/phase_e/L2_STATUS.md:53`
- TranscriptionalRegulation: `10ef0c2:docs/phase_e/L2_STATUS.md:54`
- Translation: `10ef0c2:docs/phase_e/L2_STATUS.md:55`
- tRNAAminoacylation: `10ef0c2:docs/phase_e/L2_STATUS.md:56`

---

## 2) Clustering

### Cluster A — Tick-0 substrate stoichiometry micro/mid drifts (allocation-facing)

- Members: `ChromosomeCondensation`, `FtsZPolymerization`, `Replication`, `RNADecay`, `Transcription`, `tRNAAminoacylation`.
- Shared structure:
  - Tick bucket: mostly `t=0`.
  - Observable: `substrates`.
  - Sign: mixed (+ and -).
  - Magnitude bucket: tiny/small/mid (`2` to `46`), except no extreme outlier.
  - Biological role: DNA/cell-cycle + central-dogma substrate chemistry.
- Hypothesized shared root-cause class:
  - Per-process substrate stoichiometry and early-step gating mismatches (not a proven global harness artifact after H2 refutation).
- GREEN analogs:
  - `DNARepair` GREEN came from restoring a missing side-reaction stoichiometry path (`AMET -> AHCYS + H`), showing that single omitted chemistry edges can close small residues quickly.  
    Evidence: `7c17ec9 commit message lines 5-7`, `10ef0c2:docs/phase_e/L2_STATUS.md:33`.
  - `ProteinProcessingI` GREEN came from a local enzyme-availability fallback affecting substrate-side residue closure, again process-local and narrow.  
    Evidence: `10ef0c2:docs/phase_e/L2_STATUS.md:43`.

### Cluster B — Enzyme/boundEnzyme accounting residues after Pattern C closure

- Members: `DNASupercoiling`, `ReplicationInitiation`, `TranscriptionalRegulation`, `Translation`.
- Shared structure:
  - Tick bucket: mostly `t=0` (except `TranscriptionalRegulation` at `t=15`).
  - Observable: `enzymes` / `boundEnzymes`.
  - Sign: mixed.
  - Magnitude bucket: tiny/small (`1` to `12`).
  - Biological role: DNA topology/initiation + transcription/translation control.
- Hypothesized shared root-cause class:
  - Binding-event bookkeeping and enzyme-state transition semantics (not generic `_PASS_THROUGH` anymore).
- GREEN analogs:
  - `ProteinTranslocation` GREEN was a pathway-classification semantic fix (SRP vs direct), not harness projection changes.  
    Evidence: `10ef0c2:docs/phase_e/L2_STATUS.md:45`, `l2-1-sweep-v2 log -80:21`.
  - `ProteinFolding` GREEN fixed enzyme gating semantics (catalytic treatment vs ATP hard-gating).  
    Evidence: `a2b3285 commit message lines 5-7`.

### Cluster C — Mid-tick product-state drifts (mostly ±1) in maturation pipelines (tentative)

- Members: `ProteinActivation`, `ProteinDecay`, `ProteinModification`, `ProteinProcessingII`, `RNAModification`, `RNAProcessing`.
- Shared structure:
  - Tick bucket: early-mid (`t=2` to `t=43`).
  - Observable surface: product/maturation vectors (`processed*`, `modified*`) or coupled substrate echoes.
  - Sign: mostly +1 / -1 with one medium (`ProteinDecay` -6).
  - Magnitude bucket: tiny/small.
  - Biological role: protein/RNA maturation and downstream processing.
- Hypothesized shared root-cause class:
  - Event-order and gating parity in maturation reaction paths (often one-count slips), likely process-specific.
- Confidence: **tentative** (ProteinModification first-fail value is not numerically reported in `L2_STATUS`; only “t=43 drift” is given).
- GREEN analogs:
  - `ProteinProcessingI` GREEN demonstrates that one local replay-state gating correction can remove a persistent maturation residue.  
    Evidence: `10ef0c2:docs/phase_e/L2_STATUS.md:43`.
  - `ProteinFolding` GREEN similarly closed a one-count folded-monomer drift via semantic gating correction.  
    Evidence: `a2b3285 commit message lines 5-7`.

### Cluster D — Outlier substrate tails (late or very high magnitude)

- Members: `Metabolism`, `RibosomeAssembly`, `TerminalOrganelleAssembly`.
- Shared structure:
  - Tick bucket: mixed (`t=0`, `t=6`, `t=96`).
  - Observable: `substrates`.
  - Magnitude bucket: one huge outlier (`Metabolism +3622`) plus two tiny late/peripheral residues.
  - Biological role: energy/core metabolism and peripheral assembly.
- Hypothesized shared root-cause class:
  - Not one class; these are structurally outlier, process-specific tails with low transfer learning between them.
- GREEN analogs:
  - No strong direct analog cluster-wide; this cluster is the least pattern-coherent and should be split during execution planning.

---

## 3) Cross-reference to closed Patterns A/B/C

| Cluster | A/B/C re-emergence or new? | Notes |
|---|---|---|
| Cluster A | Mostly new D; partial historical A/B ancestry in `Transcription` | `Transcription`/`Translation` went through A then B closures and now remain D, so current residues are post-closure semantics, not unresolved A/B. |
| Cluster B | **Closest to “Pattern C 2.0” shape, but not C reopening** | Pattern C root cause (`_PASS_THROUGH` non-honoring) is already closed. Remaining enzyme residues occur after C closure and include process-semantic shifts under WIP, so treat as new per-process D subclass. |
| Cluster C | New D (tentative) | Former C-adjacent processes (`ProteinProcessingII`) now fail at non-t0 maturation surfaces; this is not the original t0 vector-projection bug class. |
| Cluster D | New D outliers | Neither width, integrality, nor pass-through signatures match A/B/C closure classes. |

Pattern closure references:
- Pattern A closed: `10ef0c2:docs/phase_e/L2_STATUS.md:62`
- Pattern B closed: `10ef0c2:docs/phase_e/L2_STATUS.md:63`
- Pattern C closed: `10ef0c2:docs/phase_e/L2_STATUS.md:64`

---

## 4) Ranked next-fanout candidates (wave 10+)

### Ranking notes

- Excluded for redundancy/in-flight constraints from this top-10:
  - `ProteinProcessingII` (active WIP and wave8 worktree),
  - `RNAModification` (multi-attempt re-fire and wave8 worktree),
  - `FtsZPolymerization`, `RNADecay`, `ChromosomeCondensation` (wave9 worktrees),
  - `ProteinFolding` (already GREEN).  
  Evidence: `git worktree list:56-61`, `l2-1-sweep-v2 log -80:1-2,15-20`.
- Sunk-cost handling:
  - `RNAModification` has >2 WIP attempts in current log snapshot and is deprioritized despite low magnitude.  
    Evidence: `l2-1-sweep-v2 log(wip):9-17`.

### Top 10

| Rank | Candidate | Why this one | Risk | Expected fix surface |
|---:|---|---|---|---|
| 1 | ReplicationInitiation | Early tick, small magnitude (`-2`), single enzyme surface, representative of Cluster B | low | `opencell/vivarium/karr_replication_initiation.py` around `next_update` (`~189-280`) |
| 2 | DNASupercoiling | Early tick, small (`+3`), same Cluster B mechanism class, already showing productive shifts | medium | `opencell/vivarium/karr_dna_supercoiling.py` around `next_update` (`~261-380`) |
| 3 | TerminalOrganelleAssembly | Tiny (`-1`), single substrate lane, not currently WIP-saturated | medium | `opencell/vivarium/karr_terminal_organelle_assembly.py` around `next_update` (`~225-320`) |
| 4 | RNAProcessing | Tiny (`+1`) and early (`t=4`), strong representative for Cluster C maturation-event drifts | medium | `opencell/vivarium/karr_rna_processing.py` around `next_update` (`~293-430`) |
| 5 | ProteinDecay | Early (`t=3`) small (`-6`) and not currently in [wip] churn | medium | `opencell/vivarium/karr_protein_decay_light.py` around `next_update` (`~193-320`) |
| 6 | TranscriptionalRegulation | Tiny (`+1`) enzyme-surface residue, useful Cluster B coverage outside translation/initiation | medium | `opencell/vivarium/karr_transcriptional_regulation.py` around `next_update` (`~326-450`) |
| 7 | Replication | Tick-0 substrate (`+46`), high representativeness for Cluster A chemistry lane | medium-high | `opencell/vivarium/karr_replication.py` around `next_update` (`~215-360`) |
| 8 | tRNAAminoacylation | Tick-0 substrate (`-37`), central-dogma leverage, Cluster A representative | medium-high | `opencell/vivarium/karr_trna_aminoacylation.py` around `next_update` (`~162-290`) |
| 9 | Transcription | Tick-0 substrate (`-27`), post-A/B residue now clearly D and biologically central | high | `opencell/vivarium/karr_transcription_v3.py` around `next_update` (`~170-290`) |
| 10 | Translation | Enzyme surface (`-12`) with productive prior shifts but already 2 WIP attempts; keep low in queue | high | `opencell/vivarium/karr_translation_v3.py` around `next_update` (`~161-310`) |

Fix-surface provenance:
- Code pointer baselines from `PROCESS_STATUS_ALL_29`: `docs/phase_e/PROCESS_STATUS_ALL_29.md:76-104`.
- Class/`next_update` anchors from source files:
  - replication-initiation: `opencell/vivarium/karr_replication_initiation.py:53,189`
  - dna-supercoiling: `opencell/vivarium/karr_dna_supercoiling.py:87,261`
  - terminal-organelle: `opencell/vivarium/karr_terminal_organelle_assembly.py:79,225`
  - rna-processing: `opencell/vivarium/karr_rna_processing.py:56,293`
  - protein-decay-light: `opencell/vivarium/karr_protein_decay_light.py:193`
  - tx-reg: `opencell/vivarium/karr_transcriptional_regulation.py:224,326`
  - replication: `opencell/vivarium/karr_replication.py:71,215`
  - trna-aa: `opencell/vivarium/karr_trna_aminoacylation.py:63,162`
  - transcription-v3: `opencell/vivarium/karr_transcription_v3.py:32,170`
  - translation-v3: `opencell/vivarium/karr_translation_v3.py:31,161`

---

## 5) Refuted hypotheses (record)

- H1 (`_PASS_THROUGH` centralization): deferred. In the current 19-red census, enzyme-side residues are present (4/19) but distributed across distinct biology domains and mixed tick surfaces, not a single obvious harness-wide fingerprint.  
  Evidence for post-C enzyme distribution: `10ef0c2:docs/phase_e/L2_STATUS.md:34,47,54,55`; Pattern C closure baseline: `10ef0c2:docs/phase_e/L2_STATUS.md:64`.
- H2 (disable allocator-mirror): refuted in wave 7; no target-six GREEN gains and 3 GREEN regressions (`MacromolecularComplexation`, `ProteinProcessingI`, `ProteinTranslocation`).  
  Evidence: `harness-h2-allocator/H2_REPORT.md:61-69,82-84`.
- H3 (shadow-write to `protein.enzyme_counts`): refuted for the tested candidates (`ProteinFolding`, `ProteinProcessingII`, `RNAModification`); 0 fingerprint shifts, 0 new GREENs.  
  Evidence: `H3_REPORT.md:18-20,39-41`.

### Implication for interpretation

- Treat these 19 as primarily per-process semantic gaps.
- Use clusters only to prioritize fanout order and fix-pattern reuse; do not treat clusters as proof of a single remaining global harness defect.

---

## 6) Open questions for next-wave planning

1. `ProteinModification` has `t=43 real biology drift` but no explicit first-fail value/sign in `L2_STATUS`; should we refresh the exact fingerprint before assigning wave-10 priority?  
   Evidence gap: `10ef0c2:docs/phase_e/L2_STATUS.md:42`.
2. `PROCESS_STATUS_ALL_29` still describes `karr_transcriptional_regulation` as missing in v6, while L2 replay status tracks it as active and RED at `t=15`; which tracker is canonical for current chassis state?  
   Evidence: `docs/phase_e/PROCESS_STATUS_ALL_29.md:104`, `10ef0c2:docs/phase_e/L2_STATUS.md:54`.
3. `RNAProcessing` already has a WIP shift report (`t=4 processedRNAs` -> `t=9 unprocessedRNAs`); should wave planning use the pre- or post-shift fingerprint as canonical?  
   Evidence: `l2-1-sweep-v2/STATUS.md:1-8`, `l2-1-sweep-v2 log -30:6`.
4. For `Transcription`/`Translation`, do post-A/B D fingerprints remain stable across seed ensemble, or are we ranking on single-trace artifacts?  
   Evidence: `10ef0c2:docs/phase_e/L2_STATUS.md:53,55,62-63`; `STATUS_PATTERN_A_RESIDUE.md:23`.
5. Are wave9 worktree branches (`chromcond`, `ftsz`, `rnadecay`) expected to land with updated fingerprints before wave10 fanout starts, or should they be treated as frozen exclusions?  
   Evidence: `git worktree list:59-61`, `l2-1-sweep-v2 log -30:2`.

---

## Appendix: 8 GREEN-producing commits used as positive examples

| Commit | GREEN effect used in this analysis | Root-cause pattern extracted |
|---|---|---|
| `80393e4` | Baseline `MacromolecularComplexation` GREEN | Real bit-identity achieved without extra harness knobs; confirms not all processes are structurally blocked. |
| `a4b8422` | `ChromosomeSegregation`, `Cytokinesis`, `DNADamage` TRIVIAL-GREEN baseline | No-op traces can pass; GREEN count alone must be read with trace-activity context. |
| `3ef618f` | `HostInteraction` TRIVIAL-GREEN baseline | Same no-op caution as above. |
| `ea5a2bf` | `DNADamage` GREEN after Pattern B' closure | Tight numeric guardrail fix in harness resolved oracle-noise false fail. |
| `699f1c4` | `ProteinTranslocation` GREEN | Pathway classification parity (SRP vs direct) can fully clear a D residue. |
| `b6b6cbe` | `ProteinProcessingI` GREEN | Local replay-state enzyme-availability semantics can collapse substrate residue. |
| `7c17ec9` | `DNARepair` GREEN | Restoring a missing side reaction can close a small deterministic substrate drift. |
| `a2b3285` | `ProteinFolding` GREEN (8→9 GREEN transition) | Correct catalytic gating semantics vs hard substrate gate closed folded-monomer residue. |

Commit evidence:
- `l2-1-sweep-v2 log -80:1,5,14,21,24,34-35,38`
- `STATUS_l2_1_sweep.md:18,62-66`
- `STATUS_PATTERN_B_FIXES.md:33-43`
- `a2b3285 commit message lines 5-7`
- `7c17ec9 commit message lines 5-7`

