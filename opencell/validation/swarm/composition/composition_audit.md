# Swarm Class A.5 Composition / Fixture-Contract Audit

## Top-line counts
- **L0 runtime identity findings:** 2/28 processes mismatch audited class vs v6 runtime class: `Transcription`, `Translation` (both promoted to v3 runtime classes). Evidence: `composition_l0.json` mismatch rows and v6 promotion code. (opencell/validation/swarm/composition/composition_l0.json:219,224,237,242; opencell/vivarium/karr_composite.py:1279,1287,1885,1886,1888,1890)
- **L1 store-classification findings:** 1 process / 1 store reclassified (`Metabolism.metabolic_reaction` => telemetry). (opencell/validation/swarm/composition/composition_l1.json:302,319,333,336)
- **L2 allocator-topology findings:** 5 processes with substrate traffic outside allocator mediation (`Metabolism`, `Transcription`, `Translation`, `MacromolecularComplexation`, `ProteinDecay`) plus 2 key-identity mismatches against allocator defaults (`MacromolecularComplexation`, `ProteinDecay`). (opencell/validation/swarm/composition/composition_l2.json:99,105,106,111,118,135,141,142,291,298,315,322)
- **L7 fixture-provenance findings:** 28/28 fixtures are single-snapshot with no replay I/O channels (`fixture_n_ticks=1`, `fixture_has_io_channels=false`, `replay_capable=false`). (opencell/validation/swarm/composition/composition_l7.json:3,6,7,8,300,303,304,305)

## L0 hot list (audited-class != runtime-class)
- **Transcription:** Class A audited `KarrTranscriptionProcess` (`karr_transcription.py`), but v6 runs `KarrTranscriptionV3Process` remapped to key `karr_transcription`. (opencell/validation/swarm/composition/composition_l0.json:219,224; opencell/vivarium/karr_composite.py:1279,1885,1888,1890)
- **Translation:** Class A audited `KarrTranslationProcess` (`karr_translation.py`), but v6 runs `KarrTranslationV3Process` remapped to key `karr_translation`. (opencell/validation/swarm/composition/composition_l0.json:237,242; opencell/vivarium/karr_composite.py:1287,1886,1888,1890)

Implication: reducer findings that cite v1 TX/TL biology behavior should be treated as **runtime-identity-scoped** until revalidated on v3 classes.

## L1 hot list (misclassified stores)
- **Metabolism `metabolic_reaction`** is telemetry-by-design in composed topology (writer-only in current decision graph), so reducer “read-port-unpowered” framing is over-broad for this store. (opencell/validation/swarm/composition/composition_l1.json:319,333,336; E:/opencell-worktrees/swarm-class-a-Metabolism/opencell/validation/swarm/class_a/Metabolism/findings.json:73,79; E:/opencell-worktrees/swarm-reducer/opencell/validation/swarm/swarm_report.md:68,69,72)

## L2 hot list (enrollment + key identity)
- **Enrollment gaps with substrate traffic confirmed:**
  - `Metabolism` (direct substrate deltas, not enrolled). (opencell/validation/swarm/composition/composition_l2.json:111,112,118,120; opencell/vivarium/karr_metabolism.py:420,490; E:/opencell-worktrees/swarm-reducer/opencell/validation/swarm/bugs_to_fix.md:61,65)
  - `Transcription` (v3 direct substrate deltas, not enrolled). (opencell/validation/swarm/composition/composition_l2.json:291,292,298,300; opencell/vivarium/karr_transcription_v3.py:46,179,185; E:/opencell-worktrees/swarm-reducer/opencell/validation/swarm/bugs_to_fix.md:125,129)
  - `Translation` (v3 direct substrate deltas, not enrolled). (opencell/validation/swarm/composition/composition_l2.json:315,316,322,324; opencell/vivarium/karr_translation_v3.py:39,140,142; E:/opencell-worktrees/swarm-reducer/opencell/validation/swarm/bugs_to_fix.md:133,137)
- **Enrolled but bypassing declared allocator path:**
  - `MacromolecularComplexation` enrolled; request calculator emits hard-zero demand while process consumes shared substrates directly. (opencell/validation/swarm/composition/composition_l2.json:99,105,106,108; opencell/vivarium/karr_request_calculators.py:30,63; opencell/vivarium/karr_macromolecular_complexation.py:203,236; E:/opencell-worktrees/swarm-reducer/opencell/validation/swarm/bugs_to_fix.md:53,57)
  - `ProteinDecay` enrolled; default-key drift (`protein_decay_light` vs `karr_protein_decay_light`) and direct substrate writes in process path. (opencell/validation/swarm/composition/composition_l2.json:135,137,141,142,144; opencell/vivarium/karr_allocation_step.py:68; opencell/vivarium/karr_protein_decay_light.py:54,172,193,248; E:/opencell-worktrees/swarm-reducer/opencell/validation/swarm/bugs_to_fix.md:69,73,149,153)
- **Predictions refuted by code:**
  - `DNASupercoiling` H2O partial-vector claim is **not** present in current Python runtime path: request/grant keys are ATP-only and emitted substrate deltas are ATP/ADP/PI only. (opencell/validation/swarm/composition/composition_l2.json:63,70,72; opencell/vivarium/karr_dna_supercoiling.py:190,192,195,197,465,469,470,471; E:/opencell-worktrees/swarm-reducer/opencell/validation/swarm/bugs_to_fix.md:45,49)
- **Recategorized (non-traffic enrollment gap):**
  - `DNADamage` is not enrolled, but current Python process exposes chromosome-only ports (no runtime substrate traffic path). (opencell/validation/swarm/composition/composition_l2.json:39,40,46,48; opencell/vivarium/karr_dna_damage.py:123,151; E:/opencell-worktrees/swarm-reducer/opencell/validation/swarm/bugs_to_fix.md:29,33)

## L7 hot list (single-snapshot fixtures blocking replay)
Single-snapshot/non-replay-capable fixtures: ChromosomeCondensation, ChromosomeSegregation, Cytokinesis, DNADamage, DNARepair, DNASupercoiling, FtsZPolymerization, HostInteraction, MacromolecularComplexation, Metabolism, ProteinActivation, ProteinDecay, ProteinFolding, ProteinModification, ProteinProcessingI, ProteinProcessingII, ProteinTranslocation, RNADecay, RNAModification, RNAProcessing, Replication, ReplicationInitiation, RibosomeAssembly, TerminalOrganelleAssembly, Transcription, TranscriptionalRegulation, Translation, tRNAAminoacylation. (opencell/validation/swarm/composition/composition_l7.json:3,14,25,36,47,58,69,80,91,102,113,124,135,146,157,168,179,190,201,212,223,234,245,256,267,278,289,300)

Additional L7 provenance notes:
- **DNARepair** remains a positive `mismatch_absent` case with fixture-backed evidence despite “no findings”. (opencell/validation/swarm/composition/composition_l7.json:47,53,54,55; E:/opencell-worktrees/swarm-class-a-DNARepair/opencell/validation/swarm/class_a/DNARepair/findings.json:103,107,109)
- **Translation** has confirmed t0 mismatch and replay-channel absence. (opencell/validation/swarm/composition/composition_l7.json:289,292,293,295,297; E:/opencell-worktrees/swarm-class-a-Translation/opencell/validation/swarm/class_a/Translation/findings.json:73,77,79,103,107,109)
- **Metabolism** t0 mismatch is scoped to standalone M1 harness; canonical v5/v6 initializer is fixture-aligned. (opencell/validation/swarm/composition/composition_l7.json:102,108,110; E:/opencell-worktrees/swarm-class-a-Metabolism/opencell/validation/swarm/class_a/Metabolism/findings.json:88,92,94; opencell/vivarium/karr_metabolism.py:538; opencell/vivarium/karr_composite.py:1442,1703)

## Implications for reducer `bugs_to_fix.md`
- **Recategorize, not discard:** #16 Transcription and #17 Translation allocator findings stay valid as allocator-topology defects, but biology comparisons in those Class A packets were audited against non-runtime wrappers. (E:/opencell-worktrees/swarm-reducer/opencell/validation/swarm/bugs_to_fix.md:125,133; opencell/validation/swarm/composition/composition_l0.json:219,224,237,242)
- **Recategorize:** #6 DNASupercoiling “missing H2O allocation” is not evidenced in current Python request/update path; treat as MATLAB-parity hypothesis pending separate completeness audit. (E:/opencell-worktrees/swarm-reducer/opencell/validation/swarm/bugs_to_fix.md:45,49; opencell/vivarium/karr_dna_supercoiling.py:190,197,465,471)
- **Recategorize:** #4 DNADamage is currently an enrollment/model-parity seam, not a demonstrated runtime shared-substrate bypass in Python. (E:/opencell-worktrees/swarm-reducer/opencell/validation/swarm/bugs_to_fix.md:29,33; opencell/vivarium/karr_dna_damage.py:123,151)
- **Keep as high-confidence:** #7 MacromolecularComplexation, #9 ProteinDecay direct-consumption path, and #19 ProteinDecay key mismatch are composition-contract defects corroborated by this audit. (E:/opencell-worktrees/swarm-reducer/opencell/validation/swarm/bugs_to_fix.md:53,57,69,73,149,153; opencell/validation/swarm/composition/composition_l2.json:99,105,106,135,141,142)

## Open questions / unresolved
- The launcher-authored `scripts/swarm/class_a_targets.json` referenced by template is not present in this worktree; this audit reconstructed targets from substituted Class-A prompts. Confirm whether the canonical manifest should be committed for reproducibility. (scripts/swarm/CLASS_A_TEMPLATE.md:3)
- Should allocator default aliases (`d2_real`, `protein_decay_light`) be normalized to canonical v6 process keys to eliminate default-path identity drift? (opencell/vivarium/karr_allocation_step.py:67,68; opencell/validation/swarm/composition/composition_l2.json:101,137)
- Fixture pipeline remains replay-blocking fleet-wide; do we treat fixture channel extraction (`inputs`/`outputs`) as a Track-A precondition? (opencell/validation/replay.py:232,233; opencell/validation/swarm/composition/composition_l7.json:3,300)
