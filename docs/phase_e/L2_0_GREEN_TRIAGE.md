# L2.0 AMBER->GREEN Triage (2026-05-30)

## 1) L2.0 measurement summary
L2.0 in this repo is a static schema-surface check, not a dynamic replay check. The harness reads Karr observables as top-level keys under `states_before/` from each per-process trace (`karr_observables`) and compares them to top-level keys returned by each OC process `ports_schema()` (`oc_schema_keys`). The overlap is computed as a set intersection of those top-level port names only (`scripts/probe_l2_0_schema_audit.py:65-70`, `scripts/probe_l2_0_schema_audit.py:72-83`, `scripts/probe_l2_0_schema_audit.py:90`).

Operationally, GREEN means full set inclusion (`karr_obs ⊆ oc_obs`), AMBER means non-empty partial overlap, and RED means zero overlap (`scripts/probe_l2_0_schema_audit.py:87-95`). So partial overlap is explicitly allowed but still AMBER; GREEN requires complete key-surface coverage. This probe does not compare per-port nested WID membership directly; it compares top-level port keys only (`scripts/probe_l2_0_schema_audit.py:87-95`, `scripts/probe_l2_0_schema_audit.py:149-151`).

For the current audit artifacts, markdown and JSON agree on counts: 0 GREEN / 24 AMBER / 4 RED / 0 ERROR (`docs/phase_e/L2_0_SCHEMA_AUDIT.md:15-19`, `docs/phase_e/L2_0_SCHEMA_AUDIT.json:2-7`).

## 2) Per-process tractability matrix
Notes:
- WID-set sizes below are from `fixture__<port>` array first-dimension lengths in `data/karr_fixtures/per_process/<Process>.npz`.
- L2.1 risk uses the provided GREEN list in task prompt (`PROMPT.md:40`).
- One drift was found: audit says DNASupercoiling misses `boundEnzymes`, but current code already declares it (`docs/phase_e/L2_0_SCHEMA_AUDIT.json:183-186`, `opencell/vivarium/karr_dna_supercoiling.py:229`).

| Process | L2.0 | Karr ports OC is missing (WID size) | Tractability | Risk to existing L2.1 GREEN | File:line (`ports_schema`) |
|---|---|---|---|---|---|
| ChromosomeCondensation | AMBER | boundEnzymes (2), enzymes (2) | medium | no | `opencell/vivarium/karr_chromosome_condensation.py:193` |
| ChromosomeSegregation | AMBER | boundEnzymes (5), enzymes (5) | medium | yes | `opencell/vivarium/karr_chromosome_segregation.py:182` |
| Cytokinesis | AMBER | boundEnzymes (4), enzymes (4) | medium | yes | `opencell/vivarium/karr_cytokinesis.py:145` |
| DNADamage | RED | boundEnzymes (0), enzymes (0), substrates (48) | low | yes | `opencell/vivarium/karr_dna_damage.py:123` |
| DNARepair | AMBER | boundEnzymes (15), enzymes (15) | high | yes | `opencell/vivarium/karr_dna_repair.py:250` |
| DNASupercoiling | AMBER | boundEnzymes (3), enzymes (3) | high | no | `opencell/vivarium/karr_dna_supercoiling.py:206` |
| FtsZPolymerization | AMBER | boundEnzymes (11), enzymes (11) | medium | no | `opencell/vivarium/karr_ftsz_polymerization.py:148` |
| HostInteraction | RED | boundEnzymes (15), enzymes (15), substrates (0) | low | yes | `opencell/vivarium/karr_host_interaction.py:216` |
| MacromolecularComplexation | AMBER | boundEnzymes (0), complexs (147), enzymes (0) | medium | yes | `opencell/vivarium/karr_macromolecular_complexation.py:173` |
| Metabolism | AMBER | boundEnzymes (104), enzymes (104) | low | no | `opencell/vivarium/karr_metabolism.py:242` |
| ProteinActivation | AMBER | boundEnzymes (0), enzymes (0) | high | no | `opencell/vivarium/karr_protein_activation.py:169` |
| ProteinDecay | AMBER | boundEnzymes (9), complexs (1206), enzymes (9), monomers (4820) | medium | no | `opencell/vivarium/karr_protein_decay_light.py:147` |
| ProteinFolding | AMBER | boundEnzymes (5), enzymes (5), foldedMonomers (482), unfoldedMonomers (482) | medium | yes | `opencell/vivarium/karr_protein_folding.py:184` |
| ProteinModification | AMBER | boundEnzymes (3), enzymes (3), modifiedMonomers (482), unmodifiedMonomers (482) | high | no | `opencell/vivarium/karr_protein_modification.py:127` |
| ProteinProcessingII | AMBER | boundEnzymes (2), enzymes (2), processedMonomers (482), unprocessedMonomers (482) | medium | no | `opencell/vivarium/karr_protein_processing_ii.py:140` |
| ProteinProcessingI | AMBER | boundEnzymes (2), enzymes (2), processedMonomers (482), unprocessedMonomers (482) | medium | yes | `opencell/vivarium/karr_protein_processing_i.py:121` |
| ProteinTranslocation | AMBER | boundEnzymes (4), enzymes (4), monomers (482) | medium | yes | `opencell/vivarium/karr_protein_translocation.py:245` |
| RNADecay | AMBER | boundEnzymes (2), enzymes (2) | medium | no | `opencell/vivarium/karr_rna_decay.py:182` |
| RNAModification | AMBER | boundEnzymes (13), enzymes (13), modifiedRNAs (347), unmodifiedRNAs (347) | high | no | `opencell/vivarium/karr_rna_modification.py:115` |
| RNAProcessing | AMBER | boundEnzymes (5), enzymes (5), processedRNAs (347), unprocessedRNAs (335) | medium | no | `opencell/vivarium/karr_rna_processing.py:255` |
| ReplicationInitiation | AMBER | boundEnzymes (15), enzymes (15) | high | no | `opencell/vivarium/karr_replication_initiation.py:148` |
| Replication | AMBER | boundEnzymes (13), enzymes (13) | medium | no | `opencell/vivarium/karr_replication.py:138` |
| RibosomeAssembly | AMBER | boundEnzymes (6), complexs (2), enzymes (6), monomers (52) | medium | no | `opencell/vivarium/karr_ribosome_assembly.py:149` |
| TerminalOrganelleAssembly | RED | boundEnzymes (4), enzymes (4), substrates (8) | low | no | `opencell/vivarium/karr_terminal_organelle_assembly.py:157` |
| Transcription | AMBER | boundEnzymes (6), enzymes (6) | medium | no | `opencell/vivarium/karr_transcription.py:80` |
| TranscriptionalRegulation | RED | boundEnzymes (5), enzymes (5), substrates (0) | low | no | `opencell/vivarium/karr_transcriptional_regulation.py:269` |
| Translation | AMBER | boundEnzymes (16), enzymes (16), monomers (482) | medium | no | `opencell/vivarium/karr_translation.py:64` |
| tRNAAminoacylation | AMBER | aminoacylatedRNAs (37), boundEnzymes (58), enzymes (58), freeRNAs (37) | high | no | `opencell/vivarium/karr_trna_aminoacylation.py:118` |

## 3) Top 5 candidates for L2.0 GREEN (ranked)

### 1. DNASupercoiling
Rank rationale: this is the cleanest near-GREEN candidate because `boundEnzymes` is already in `ports_schema()` and the delta is effectively one missing top-level key (`docs/phase_e/L2_0_SCHEMA_AUDIT.json:183-186`, `opencell/vivarium/karr_dna_supercoiling.py:229-231`). The process already has canonical `self.enzyme_wids` loaded from fixture and split into protein/complex routing, so no new state model is needed (`opencell/vivarium/karr_dna_supercoiling.py:156`, `opencell/vivarium/karr_dna_supercoiling.py:128-137`). Risk to current L2.1 GREEN set is none (not in provided list).

Diff sketch (in `ports_schema()` around `opencell/vivarium/karr_dna_supercoiling.py:229`):
```python
"enzymes": {
    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
    for wid in self.enzyme_wids
},
```
WID list source: `self.enzyme_wids` (`opencell/vivarium/karr_dna_supercoiling.py:156`).
Expected verdict after change: GREEN.
Data re-extract needed: no, code-only schema declaration.

### 2. ReplicationInitiation
Rank rationale: this process already loads enzyme WIDs and already has dual-path logic for detailed enzyme pools vs aggregate DnaA pool, so adding Karr-named ports is structurally aligned (`opencell/vivarium/karr_replication_initiation.py:90`, `opencell/vivarium/karr_replication_initiation.py:195-201`, `opencell/vivarium/karr_replication_initiation.py:213-216`). The missing L2.0 surface is only `boundEnzymes` + `enzymes` (`docs/phase_e/L2_0_SCHEMA_AUDIT.json:676-679`). This is a high-value representative of the "enzyme-only AMBER" cluster.

Diff sketch (in `ports_schema()` after protein block at `opencell/vivarium/karr_replication_initiation.py:166`):
```python
"enzymes": {
    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
    for wid in self.enzyme_wids
},
"boundEnzymes": {
    wid: {"_default": 0.0, "_updater": "set", "_emit": False}
    for wid in self.enzyme_wids
},
```
WID list source: `self.enzyme_wids` (`opencell/vivarium/karr_replication_initiation.py:90`).
Expected verdict after change: GREEN.
Data re-extract needed: no, code-only schema declaration.

### 3. RNAModification
Rank rationale: this file already tracks RNA in split stores and already supports legacy top-level fallbacks (`states.get("unmodifiedRNAs")`, `states.get("modifiedRNAs")`), which makes Karr-name declarations low-risk (`opencell/vivarium/karr_rna_modification.py:182-197`). It also already computes enzyme vectors from existing protein/complex stores using `self.enzyme_wids` (`opencell/vivarium/karr_rna_modification.py:108`, `opencell/vivarium/karr_rna_modification.py:215-223`). This candidate represents the RNA-split alias cluster.

Diff sketch (in `ports_schema()` near `opencell/vivarium/karr_rna_modification.py:121`):
```python
"unmodifiedRNAs": {
    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
    for wid in self.unmodified_rna_wids
},
"modifiedRNAs": {
    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
    for wid in self.modified_rna_wids
},
"enzymes": {wid: {"_default": 0.0, "_updater": "set", "_emit": False} for wid in self.enzyme_wids},
"boundEnzymes": {wid: {"_default": 0.0, "_updater": "set", "_emit": False} for wid in self.enzyme_wids},
```
WID list sources: `self.unmodified_rna_wids`, `self.modified_rna_wids`, `self.enzyme_wids` (`opencell/vivarium/karr_rna_modification.py:106-108`).
Expected verdict after change: GREEN.
Data re-extract needed: no, code-only schema declaration.

### 4. ProteinModification
Rank rationale: this process already has explicit modified/unmodified monomer channels under `protein.*_counts` and a legacy top-level fallback for `unmodifiedMonomers`, so Karr-surface alias ports are straightforward (`opencell/vivarium/karr_protein_modification.py:138-145`, `opencell/vivarium/karr_protein_modification.py:206-209`). Enzyme routing is already explicit across protein/complex stores (`opencell/vivarium/karr_protein_modification.py:94-99`, `opencell/vivarium/karr_protein_modification.py:191-199`). This represents the monomer-split alias cluster.

Diff sketch (in `ports_schema()` around `opencell/vivarium/karr_protein_modification.py:133`):
```python
"unmodifiedMonomers": {
    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
    for wid in self.unmodified_monomer_wids
},
"modifiedMonomers": {
    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
    for wid in self.modified_monomer_wids
},
"enzymes": {wid: {"_default": 0.0, "_updater": "set", "_emit": False} for wid in self.enzyme_wids},
"boundEnzymes": {wid: {"_default": 0.0, "_updater": "set", "_emit": False} for wid in self.enzyme_wids},
```
WID list sources: `self.unmodified_monomer_wids`, `self.modified_monomer_wids`, `self.enzyme_wids` (`opencell/vivarium/karr_protein_modification.py:94`, `opencell/vivarium/karr_protein_modification.py:112-115`).
Expected verdict after change: GREEN.
Data re-extract needed: no, code-only schema declaration.

### 5. tRNAAminoacylation
Rank rationale: like RNAModification, this process already has explicit split RNA channels and legacy fallback reads for `freeRNAs` / `aminoacylatedRNAs`, which directly matches the missing Karr keys (`opencell/vivarium/karr_trna_aminoacylation.py:124-133`, `opencell/vivarium/karr_trna_aminoacylation.py:187-202`). Enzyme handling is also already explicit and split across protein/complex (`opencell/vivarium/karr_trna_aminoacylation.py:83-91`, `opencell/vivarium/karr_trna_aminoacylation.py:216-219`). It is high-tractability and covers a distinct central-dogma cluster.

Diff sketch (in `ports_schema()` around `opencell/vivarium/karr_trna_aminoacylation.py:124`):
```python
"freeRNAs": {
    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
    for wid in self.free_rna_wids
},
"aminoacylatedRNAs": {
    wid: {"_default": 0.0, "_updater": "accumulate", "_emit": False}
    for wid in self.aminoacylated_rna_wids
},
"enzymes": {wid: {"_default": 0.0, "_updater": "set", "_emit": False} for wid in self.enzyme_wids},
"boundEnzymes": {wid: {"_default": 0.0, "_updater": "set", "_emit": False} for wid in self.enzyme_wids},
```
WID list sources: `self.free_rna_wids`, `self.aminoacylated_rna_wids`, `self.enzyme_wids` (`opencell/vivarium/karr_trna_aminoacylation.py:107-109`).
Expected verdict after change: GREEN.
Data re-extract needed: no, code-only schema declaration.

## 4) Defer list
Mark as defer until M2 or after L2.1 closes:
- DNADamage (RED): current process intentionally focuses on lesion events in chromosome channels and defers richer chemistry/state; matching Karr `substrates/enzymes/boundEnzymes` is not a pure alias add (`opencell/vivarium/karr_dna_damage.py:7-10`, `docs/phase_e/L2_0_SCHEMA_AUDIT.json:118-122`).
- HostInteraction (RED): current schema is cell/protein-only and module is already treated as peripheral/deferred in status docs (`opencell/vivarium/karr_host_interaction.py:216-230`, `docs/phase_e/PROCESS_STATUS_ALL_29.md:147`).
- TerminalOrganelleAssembly (RED): schema is protein activity + cell assembly state; adding Karr substrate/enzyme surfaces would require new state path, not just aliasing (`opencell/vivarium/karr_terminal_organelle_assembly.py:157-176`, `docs/phase_e/L2_0_SCHEMA_AUDIT.json:771-775`).
- TranscriptionalRegulation (RED): current surface is TF-binding/fold-change oriented; Karr audit expects substrate/enzyme triplet, so GREEN needs model-surface policy decision rather than surgical renames (`opencell/vivarium/karr_transcriptional_regulation.py:269-294`, `docs/phase_e/L2_0_SCHEMA_AUDIT.json:825-829`).
- Metabolism (AMBER): missing enzyme/boundEnzyme ports are large (104 each) and not currently explicit in the M1 schema surface; this is likely a state-model expansion, not a no-risk alias (`opencell/vivarium/karr_metabolism.py:242-283`).

## 5) Cross-link to L2.1 strategy
`docs/phase_e/L2_STATUS.md` is not present in this worktree (requested in prompt), so cross-rung notes are based on available artifacts plus the prompt-provided L2.1 GREEN list (`PROMPT.md:20`, `PROMPT.md:40`). From prompt context, L2.1 RED includes TerminalOrganelleAssembly and TranscriptionalRegulation; both are also L2.0 RED in the current audit JSON (`PROMPT.md:65`, `docs/phase_e/L2_0_SCHEMA_AUDIT.json:758-781`, `docs/phase_e/L2_0_SCHEMA_AUDIT.json:810-837`).

Given L2.0 is a prerequisite for L2.2, L2.0 is currently a binding constraint for any process targeted for distributional-fidelity closure, but it is slack for near-term L2.1-only closure (as the prompt explicitly notes) (`PROMPT.md:11`). Practical sequencing: keep no-risk AMBER->GREEN sweeps moving in parallel with L2.1 replay fixes, but do not block L2.1 closure on deep L2.0 REDs where the state model itself is deferred.

## 6) Open questions
1. Should L2.0 remain strictly top-level port-name overlap, or be upgraded to include nested WID membership checks? (Current probe only checks top-level keys: `scripts/probe_l2_0_schema_audit.py:90-95`.)
2. For L2.0 GREEN eligibility, are empty declarations acceptable when Karr port cardinality is zero (for example ProteinActivation enzymes), or must every declared port be actively read/written?
3. Is the canonical policy to preserve legacy top-level aliases (`unmodifiedRNAs`, `freeRNAs`, etc.) permanently, or only during migration windows?
4. Should processes currently L2.1 GREEN be excluded from L2.0 surface expansion until replay baselines are frozen, to avoid overlap-set expansion regressions?
5. Where is the authoritative cross-rung matrix now that `docs/phase_e/L2_STATUS.md` is missing in this worktree? (`PROMPT.md:20` references it, but file is absent.)
