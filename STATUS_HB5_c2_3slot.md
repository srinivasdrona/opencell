# STATUS_HB5_c2_3slot

## INTENT
Summary: derive `dependencies` honestly from authoritative machine-readable sources, update only dependency blocks, add a reproducible verifier, and either land a green invariant or report the honest blocker.

Contract: fix `check_dependency_symmetry` by making every retained inter-process dependency evidence-backed from row same-tick inputs, with no fabricated WIDs and no special-case add/remove logic. Done means the dependency graph in `data/schemas/per_process_wiring/*.yaml` matches a single derivation rule, not merely that the checker happens to pass.

Expected observable: `bin\oc-py scripts/l1b_verify_wiring.py --format plain` should report `check_dependency_symmetry: 0` and `no_dependency_cycles: PASS`; `bin\oc-pytest tests/integration/test_l1b_verify_wiring.py -q` should pass; `bin\oc-py scripts/l1b_method_completeness.py` should remain at `gap: 0`.

Inversion: the most embarrassing false-green would be hardcoding or selectively justifying edges, especially by citing WIDs that are not actually present in a row YAML, by using TOML `state_groups` only when they help adds, or by deleting a real derived edge just to keep the cycle check green.

PM sanity-check: I treated `dependencies` as an inter-process relation only and therefore excluded self-edges even when a process consumes a WID whose producer type maps back to itself; if self-dependencies were intended to be represented in this field, this derivation is too conservative.

## Uniform Derivation Rule
`X depends on Y` iff row `X` has at least one same-tick input WID in `consume_stoichiometry[*].wid` or `allocator.requests[*].wid` whose producer maps to distinct process `Y` under the authoritative producer map:

- `Metabolism.json substrates[*].wid` -> `Metabolism`
- `*_MONOMER` -> `Translation`
- `RIBOSOME*` -> `RibosomeAssembly`
- `*_DIMER` or `*MER` -> `MacromolecularComplexation`
- `MGrrn*` or `rRNA` -> `RNAProcessing`
- anything else -> producer `UNKNOWN` and no dependency edge is asserted

State-group TOMLs were read but excluded from the derivation because they do not distinguish read vs write, and Slot-2 rule 3 forbids using that ambiguity selectively.

## Honest Result
- Added committed derivation/verifier: `scripts/verify_dep_evidence.py`
- Rewrote dependency blocks to match the derived graph exactly
- Derived dependency graph size: 28 dependency edges
- Graph check size is 29 total edges because the verifier graph also includes the existing `tRNAAminoacylation -> Translation` ordering edge

Additional full-graph corrections beyond the 43 asymmetric pairs:
- `Translation.produces_inputs_for` was realigned from the post-translation maturation chain to the evidence-backed consumers `MacromolecularComplexation`, `ProteinActivation`, `RibosomeAssembly`, and `TerminalOrganelleAssembly`.
- Unsupported symmetric producer edges were removed from `ProteinProcessingI`, `ProteinTranslocation`, `RNAModification`, `RNAProcessing`, `Transcription`, `tRNAAminoacylation`, and `ProteinFolding`.
- `MacromolecularComplexation.produces_inputs_for` changed from `ProteinDecay` to `ProteinActivation`.
- `Metabolism.produces_inputs_for` added `DNADamage` and removed `MacromolecularComplexation`.

## Asymmetry Evidence Table
Each command is rerunnable. The table records the first output line; the full command output lists the specific supporting or scanned WIDs.

| Edge | Final | Command | Observed first line |
| --- | --- | --- | --- |
| `ChromosomeSegregation <- ChromosomeCondensation` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair ChromosomeSegregation ChromosomeCondensation` | `NO_EDGE ChromosomeSegregation <- ChromosomeCondensation: no same-tick input WID maps to ChromosomeCondensation in data/schemas/per_process_wiring/ChromosomeSegregation.yaml` |
| `ChromosomeSegregation <- DNASupercoiling` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair ChromosomeSegregation DNASupercoiling` | `NO_EDGE ChromosomeSegregation <- DNASupercoiling: no same-tick input WID maps to DNASupercoiling in data/schemas/per_process_wiring/ChromosomeSegregation.yaml` |
| `ChromosomeSegregation <- Replication` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair ChromosomeSegregation Replication` | `NO_EDGE ChromosomeSegregation <- Replication: no same-tick input WID maps to Replication in data/schemas/per_process_wiring/ChromosomeSegregation.yaml` |
| `DNADamage <- Metabolism` | KEEP | `bin\oc-py scripts/verify_dep_evidence.py --pair DNADamage Metabolism` | `EDGE DNADamage <- Metabolism: 3 supporting same-tick input(s) in data/schemas/per_process_wiring/DNADamage.yaml` |
| `FtsZPolymerization <- ProteinFolding` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair FtsZPolymerization ProteinFolding` | `NO_EDGE FtsZPolymerization <- ProteinFolding: no same-tick input WID maps to ProteinFolding in data/schemas/per_process_wiring/FtsZPolymerization.yaml` |
| `FtsZPolymerization <- ProteinProcessingI` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair FtsZPolymerization ProteinProcessingI` | `NO_EDGE FtsZPolymerization <- ProteinProcessingI: no same-tick input WID maps to ProteinProcessingI in data/schemas/per_process_wiring/FtsZPolymerization.yaml` |
| `FtsZPolymerization <- ProteinProcessingII` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair FtsZPolymerization ProteinProcessingII` | `NO_EDGE FtsZPolymerization <- ProteinProcessingII: no same-tick input WID maps to ProteinProcessingII in data/schemas/per_process_wiring/FtsZPolymerization.yaml` |
| `FtsZPolymerization <- Translation` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair FtsZPolymerization Translation` | `NO_EDGE FtsZPolymerization <- Translation: no same-tick input WID maps to Translation in data/schemas/per_process_wiring/FtsZPolymerization.yaml` |
| `HostInteraction <- ProteinProcessingI` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair HostInteraction ProteinProcessingI` | `NO_EDGE HostInteraction <- ProteinProcessingI: no same-tick input WID maps to ProteinProcessingI in data/schemas/per_process_wiring/HostInteraction.yaml` |
| `HostInteraction <- ProteinProcessingII` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair HostInteraction ProteinProcessingII` | `NO_EDGE HostInteraction <- ProteinProcessingII: no same-tick input WID maps to ProteinProcessingII in data/schemas/per_process_wiring/HostInteraction.yaml` |
| `HostInteraction <- ProteinTranslocation` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair HostInteraction ProteinTranslocation` | `NO_EDGE HostInteraction <- ProteinTranslocation: no same-tick input WID maps to ProteinTranslocation in data/schemas/per_process_wiring/HostInteraction.yaml` |
| `HostInteraction <- TerminalOrganelleAssembly` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair HostInteraction TerminalOrganelleAssembly` | `NO_EDGE HostInteraction <- TerminalOrganelleAssembly: no same-tick input WID maps to TerminalOrganelleAssembly in data/schemas/per_process_wiring/HostInteraction.yaml` |
| `HostInteraction <- Translation` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair HostInteraction Translation` | `NO_EDGE HostInteraction <- Translation: no same-tick input WID maps to Translation in data/schemas/per_process_wiring/HostInteraction.yaml` |
| `MacromolecularComplexation <- RNAModification` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair MacromolecularComplexation RNAModification` | `NO_EDGE MacromolecularComplexation <- RNAModification: no same-tick input WID maps to RNAModification in data/schemas/per_process_wiring/MacromolecularComplexation.yaml` |
| `MacromolecularComplexation <- RNAProcessing` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair MacromolecularComplexation RNAProcessing` | `NO_EDGE MacromolecularComplexation <- RNAProcessing: no same-tick input WID maps to RNAProcessing in data/schemas/per_process_wiring/MacromolecularComplexation.yaml` |
| `MacromolecularComplexation <- Transcription` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair MacromolecularComplexation Transcription` | `NO_EDGE MacromolecularComplexation <- Transcription: no same-tick input WID maps to Transcription in data/schemas/per_process_wiring/MacromolecularComplexation.yaml` |
| `MacromolecularComplexation <- Translation` | KEEP | `bin\oc-py scripts/verify_dep_evidence.py --pair MacromolecularComplexation Translation` | `EDGE MacromolecularComplexation <- Translation: 8 supporting same-tick input(s) in data/schemas/per_process_wiring/MacromolecularComplexation.yaml` |
| `MacromolecularComplexation <- tRNAAminoacylation` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair MacromolecularComplexation tRNAAminoacylation` | `NO_EDGE MacromolecularComplexation <- tRNAAminoacylation: no same-tick input WID maps to tRNAAminoacylation in data/schemas/per_process_wiring/MacromolecularComplexation.yaml` |
| `ProteinActivation <- HostInteraction` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair ProteinActivation HostInteraction` | `NO_EDGE ProteinActivation <- HostInteraction: no same-tick input WID maps to HostInteraction in data/schemas/per_process_wiring/ProteinActivation.yaml` |
| `ProteinActivation <- Metabolism` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair ProteinActivation Metabolism` | `NO_EDGE ProteinActivation <- Metabolism: no same-tick input WID maps to Metabolism in data/schemas/per_process_wiring/ProteinActivation.yaml` |
| `ProteinActivation <- ProteinProcessingII` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair ProteinActivation ProteinProcessingII` | `NO_EDGE ProteinActivation <- ProteinProcessingII: no same-tick input WID maps to ProteinProcessingII in data/schemas/per_process_wiring/ProteinActivation.yaml` |
| `ProteinActivation <- Translation` | KEEP | `bin\oc-py scripts/verify_dep_evidence.py --pair ProteinActivation Translation` | `EDGE ProteinActivation <- Translation: 2 supporting same-tick input(s) in data/schemas/per_process_wiring/ProteinActivation.yaml` |
| `ProteinDecay <- ProteinFolding` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair ProteinDecay ProteinFolding` | `NO_EDGE ProteinDecay <- ProteinFolding: no same-tick input WID maps to ProteinFolding in data/schemas/per_process_wiring/ProteinDecay.yaml` |
| `ProteinDecay <- ProteinProcessingI` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair ProteinDecay ProteinProcessingI` | `NO_EDGE ProteinDecay <- ProteinProcessingI: no same-tick input WID maps to ProteinProcessingI in data/schemas/per_process_wiring/ProteinDecay.yaml` |
| `ProteinDecay <- ProteinProcessingII` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair ProteinDecay ProteinProcessingII` | `NO_EDGE ProteinDecay <- ProteinProcessingII: no same-tick input WID maps to ProteinProcessingII in data/schemas/per_process_wiring/ProteinDecay.yaml` |
| `ProteinDecay <- Translation` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair ProteinDecay Translation` | `NO_EDGE ProteinDecay <- Translation: no same-tick input WID maps to Translation in data/schemas/per_process_wiring/ProteinDecay.yaml` |
| `ProteinFolding <- MacromolecularComplexation` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair ProteinFolding MacromolecularComplexation` | `NO_EDGE ProteinFolding <- MacromolecularComplexation: no same-tick input WID maps to MacromolecularComplexation in data/schemas/per_process_wiring/ProteinFolding.yaml` |
| `ProteinFolding <- RibosomeAssembly` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair ProteinFolding RibosomeAssembly` | `NO_EDGE ProteinFolding <- RibosomeAssembly: no same-tick input WID maps to RibosomeAssembly in data/schemas/per_process_wiring/ProteinFolding.yaml` |
| `ProteinModification <- ProteinProcessingII` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair ProteinModification ProteinProcessingII` | `NO_EDGE ProteinModification <- ProteinProcessingII: no same-tick input WID maps to ProteinProcessingII in data/schemas/per_process_wiring/ProteinModification.yaml` |
| `RNADecay <- RNAModification` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair RNADecay RNAModification` | `NO_EDGE RNADecay <- RNAModification: no same-tick input WID maps to RNAModification in data/schemas/per_process_wiring/RNADecay.yaml` |
| `RNADecay <- RNAProcessing` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair RNADecay RNAProcessing` | `NO_EDGE RNADecay <- RNAProcessing: no same-tick input WID maps to RNAProcessing in data/schemas/per_process_wiring/RNADecay.yaml` |
| `RNADecay <- Transcription` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair RNADecay Transcription` | `NO_EDGE RNADecay <- Transcription: no same-tick input WID maps to Transcription in data/schemas/per_process_wiring/RNADecay.yaml` |
| `RNADecay <- tRNAAminoacylation` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair RNADecay tRNAAminoacylation` | `NO_EDGE RNADecay <- tRNAAminoacylation: no same-tick input WID maps to tRNAAminoacylation in data/schemas/per_process_wiring/RNADecay.yaml` |
| `RNAModification <- RNAProcessing` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair RNAModification RNAProcessing` | `NO_EDGE RNAModification <- RNAProcessing: no same-tick input WID maps to RNAProcessing in data/schemas/per_process_wiring/RNAModification.yaml` |
| `RibosomeAssembly <- ProteinProcessingI` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair RibosomeAssembly ProteinProcessingI` | `NO_EDGE RibosomeAssembly <- ProteinProcessingI: no same-tick input WID maps to ProteinProcessingI in data/schemas/per_process_wiring/RibosomeAssembly.yaml` |
| `RibosomeAssembly <- ProteinProcessingII` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair RibosomeAssembly ProteinProcessingII` | `NO_EDGE RibosomeAssembly <- ProteinProcessingII: no same-tick input WID maps to ProteinProcessingII in data/schemas/per_process_wiring/RibosomeAssembly.yaml` |
| `RibosomeAssembly <- Transcription` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair RibosomeAssembly Transcription` | `NO_EDGE RibosomeAssembly <- Transcription: no same-tick input WID maps to Transcription in data/schemas/per_process_wiring/RibosomeAssembly.yaml` |
| `RibosomeAssembly <- Translation` | KEEP | `bin\oc-py scripts/verify_dep_evidence.py --pair RibosomeAssembly Translation` | `EDGE RibosomeAssembly <- Translation: 52 supporting same-tick input(s) in data/schemas/per_process_wiring/RibosomeAssembly.yaml` |
| `TerminalOrganelleAssembly <- Translation` | KEEP | `bin\oc-py scripts/verify_dep_evidence.py --pair TerminalOrganelleAssembly Translation` | `EDGE TerminalOrganelleAssembly <- Translation: 8 supporting same-tick input(s) in data/schemas/per_process_wiring/TerminalOrganelleAssembly.yaml` |
| `TranscriptionalRegulation <- MacromolecularComplexation` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair TranscriptionalRegulation MacromolecularComplexation` | `NO_EDGE TranscriptionalRegulation <- MacromolecularComplexation: no same-tick input WID maps to MacromolecularComplexation in data/schemas/per_process_wiring/TranscriptionalRegulation.yaml` |
| `TranscriptionalRegulation <- Translation` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair TranscriptionalRegulation Translation` | `NO_EDGE TranscriptionalRegulation <- Translation: no same-tick input WID maps to Translation in data/schemas/per_process_wiring/TranscriptionalRegulation.yaml` |
| `Translation <- RNAModification` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair Translation RNAModification` | `NO_EDGE Translation <- RNAModification: no same-tick input WID maps to RNAModification in data/schemas/per_process_wiring/Translation.yaml` |
| `tRNAAminoacylation <- Translation` | REMOVE | `bin\oc-py scripts/verify_dep_evidence.py --pair tRNAAminoacylation Translation` | `NO_EDGE tRNAAminoacylation <- Translation: no same-tick input WID maps to Translation in data/schemas/per_process_wiring/tRNAAminoacylation.yaml` |

## VERIFICATION
Beat-3 expected outcome: `check_dependency_symmetry: 0`, `no_dependency_cycles: PASS`, integration test green, and method completeness remains `gap: 0`.

Actual measured values:

Command:
```text
bin\oc-py scripts/l1b_verify_wiring.py --format plain
```
Output:
```text
graph checks:
- no_dependency_cycles: PASS
  - validated acyclic dependency/order graph (28 nodes, 29 edges)
per-check failures:
- check_dependency_symmetry: 0
```

Command:
```text
bin\oc-pytest tests/integration/test_l1b_verify_wiring.py -q
```
Output:
```text
...................                                                      [100%]
19 passed in 101.48s (0:01:41)
```

Command:
```text
bin\oc-py scripts/l1b_method_completeness.py
```
Output:
```text
L1b METHOD-COMPLETENESS: PASS (115/115 runtime methods resolved)
gap:         0  <-- real porting gaps
```

Beat-4 failure mode 1: "I cited a WID as being in a row's consume/request when grep shows count 0."

Command:
```text
rg -n "ATP|GLU|LIPOYLAMP" data/schemas/per_process_wiring/ProteinActivation.yaml
```
Output:
```text
<no matches; rg exit 1>
```

Command:
```text
bin\oc-py scripts/verify_dep_evidence.py --pair ProteinActivation Metabolism
```
Output:
```text
NO_EDGE ProteinActivation <- Metabolism: no same-tick input WID maps to Metabolism in data/schemas/per_process_wiring/ProteinActivation.yaml
  - scanned: consume_stoichiometry[0]:MG_101_MONOMER->Translation, consume_stoichiometry[1]:MG_127_MONOMER->Translation, consume_stoichiometry[2]:MG_205_DIMER->MacromolecularComplexation, consume_stoichiometry[3]:MG_409_DIMER->MacromolecularComplexation
```

Command:
```text
rg -n "MG_224" data/schemas/per_process_wiring/FtsZPolymerization.yaml
```
Output:
```text
<no matches; rg exit 1>
```

Command:
```text
bin\oc-py scripts/verify_dep_evidence.py --pair FtsZPolymerization Translation
```
Output:
```text
NO_EDGE FtsZPolymerization <- Translation: no same-tick input WID maps to Translation in data/schemas/per_process_wiring/FtsZPolymerization.yaml
  - scanned: consume_stoichiometry[0]:GTP->Metabolism, consume_stoichiometry[1]:GDP->Metabolism, consume_stoichiometry[2]:H2O->Metabolism, allocator.requests[0]:GTP->Metabolism
```

Beat-4 failure mode 2: "I counted `enzymes`-group membership as a dependency for adds but ignored it for removes."

Command:
```text
rg -n "state_groups|toml|enzymes|monomers|complexs|rnas" scripts/verify_dep_evidence.py
```
Output:
```text
<no matches; rg exit 1>
```

Command:
```text
bin\oc-py scripts/verify_dep_evidence.py --pair ProteinActivation Translation
```
Output:
```text
EDGE ProteinActivation <- Translation: 2 supporting same-tick input(s) in data/schemas/per_process_wiring/ProteinActivation.yaml
  - consume_stoichiometry[0]: wid=MG_101_MONOMER -> producer=Translation (suffix *_MONOMER)
  - consume_stoichiometry[1]: wid=MG_127_MONOMER -> producer=Translation (suffix *_MONOMER)
```

Command:
```text
bin\oc-py scripts/verify_dep_evidence.py --pair Translation RNAModification
```
Output:
```text
NO_EDGE Translation <- RNAModification: no same-tick input WID maps to RNAModification in data/schemas/per_process_wiring/Translation.yaml
  - scanned: consume_stoichiometry[0]:GTP->Metabolism, consume_stoichiometry[1]:H2O->Metabolism, consume_stoichiometry[2]:ALA->Metabolism, consume_stoichiometry[3]:MET->Metabolism, consume_stoichiometry[4]:LYS->Metabolism, allocator.requests[0]:ALA->Metabolism, allocator.requests[1]:MET->Metabolism, allocator.requests[2]:LYS->Metabolism, allocator.requests[3]:GLY->Metabolism, allocator.requests[4]:VAL->Metabolism
```

Beat-4 failure mode 3: "I forced `no_dependency_cycles: PASS` by deleting a real edge instead of reporting the cycle the honest graph implies."

Command:
```text
bin\oc-py scripts/verify_dep_evidence.py --mode diff
```
Output:
```text
current dependency blocks match the derived graph
```

Command:
```text
$lines = bin\oc-py scripts/l1b_verify_wiring.py --format plain; $lines | Select-String 'no_dependency_cycles|check_dependency_symmetry'
```
Output:
```text
- no_dependency_cycles: PASS
- check_dependency_symmetry: 0
```

Verdict: matched.
