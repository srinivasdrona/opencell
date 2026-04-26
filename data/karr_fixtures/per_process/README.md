# `data/karr_fixtures/per_process/` — Karr WholeCell Per-Process Oracles

## What this is

Per-process and per-state MAT fixtures shipped with Karr et al.'s
*WholeCell* MATLAB suite, lifted into Python-native form for use as
oracles by the M2–M7 unit tests.

Sources (gitignored upstream clone — re-fetch with
`git clone https://github.com/CovertLab/WholeCell data/m1_sources/WholeCell`):

* 28 process fixtures —
  `data/m1_sources/WholeCell/src_test/+edu/+stanford/+covert/+cell/+sim/+process/fixtures/*.mat`
* 16 state fixtures —
  `data/m1_sources/WholeCell/src_test/+edu/+stanford/+covert/+cell/+sim/+state/fixtures/*.mat`

## ⚠️ Status: **MCOS payload is unparsed**

Every one of the 44 source `.mat` files is a MATLAB v5 file holding a
single MCOS-serialized class instance (e.g.
`edu.stanford.covert.cell.sim.process.Transcription`).  The actual
class field data lives inside the MAT v5 `__function_workspace__`
subsystem blob in MATLAB's undocumented MCOS format.

`scipy.io.loadmat`, `pymatreader`, and `mat4py` *all* refuse to decode
MCOS objects — they surface only the opaque pointer
`(s0='fixture', s1='MCOS', s2=<class>, arr=<6×uint32 pointer>)`.
Decoding requires either:

* a running MATLAB (explicitly forbidden post-MATLAB-eviction), **or**
* a custom Python MCOS subsystem decoder (not currently bundled).

We therefore commit a **best-effort** payload here:

| File                          | Contents                                                                        |
| ----------------------------- | ------------------------------------------------------------------------------- |
| `<Name>.json`                 | Provenance (source path, sha256, size), MCOS class name, `function_workspace_bytes`, `extraction_status`, sorted scalar map. |
| `<Name>.npz`                  | The 6-uint32 MCOS pointer array under key `None/__mcos__/arr` (sentinel for empty otherwise). |
| `manifest.json`               | All 44 entries combined, sorted by (kind, name).                                |
| `fixture_hashes.json`         | sha256 of every `.npz`/`.json` in this dir for `validate_per_process_fixtures.py`. |

The committed payload is ~200 KB total — it does **not** include the
~3 GB worth of raw `__function_workspace__` bytes.  Those can be
regenerated from the upstream `data/m1_sources/WholeCell` clone at any
time via the extraction script.

## Files

```
manifest.json                  # 44 entries (28 process + 16 state)
fixture_hashes.json            # validation manifest
<ProcessName>.json             # one per process fixture, e.g. Transcription.json
<ProcessName>.npz
<StateName>.json               # one per state fixture, e.g. CellMass.json
<StateName>.npz
README.md                      # this file
```

## Consuming a fixture (downstream test pattern)

```python
import json, numpy as np, pathlib

D = pathlib.Path("data/karr_fixtures/per_process")
meta = json.loads((D / "Transcription.json").read_text())
arrs = np.load(D / "Transcription.npz")

assert meta["manifest"]["mcos_class"].endswith(".Transcription")
status = meta["manifest"]["extraction_status"]
if status == "unparsed_mcos_payload":
    raise unittest.SkipTest(
        f"Transcription oracle blocked: {status} "
        f"(needs MCOS decoder; see data/karr_fixtures/per_process/README.md)"
    )
# When a future MCOS decoder lands, the npz will carry real per-field
# arrays under stable paths and the test can compare against them:
expected = arrs["before/state/rnaPolymerase/positionStrands"]
```

## Regenerating

```bash
# Extract every fixture (idempotent, deterministic):
.venv-wsl/bin/python scripts/extract_per_process_fixtures.py --all

# Or one-off:
.venv-wsl/bin/python scripts/extract_per_process_fixtures.py --name Transcription

# Verify byte-stable output against committed hashes:
.venv-wsl/bin/python scripts/validate_per_process_fixtures.py

# Re-seed hashes after intentional changes to the extractor:
.venv-wsl/bin/python scripts/validate_per_process_fixtures.py --seed
```

## Per-fixture one-liners

All 44 fixtures share the same shape: a single MCOS-serialized
WholeCell class instance representing a snapshot of that
process/state in the Karr unit-test harness.  The MATLAB class name
is the authoritative description; see `manifest.json` →
`fixtures[*].mcos_class`.

| Process                       | MATLAB class                                                            |
| ----------------------------- | ----------------------------------------------------------------------- |
| ChromosomeCondensation        | edu.stanford.covert.cell.sim.process.ChromosomeCondensation             |
| ChromosomeSegregation         | edu.stanford.covert.cell.sim.process.ChromosomeSegregation              |
| Cytokinesis                   | edu.stanford.covert.cell.sim.process.Cytokinesis                        |
| DNADamage                     | edu.stanford.covert.cell.sim.process.DNADamage                          |
| DNARepair                     | edu.stanford.covert.cell.sim.process.DNARepair                          |
| DNASupercoiling               | edu.stanford.covert.cell.sim.process.DNASupercoiling                    |
| FtsZPolymerization            | edu.stanford.covert.cell.sim.process.FtsZPolymerization                 |
| HostInteraction               | edu.stanford.covert.cell.sim.process.HostInteraction                    |
| MacromolecularComplexation    | edu.stanford.covert.cell.sim.process.MacromolecularComplexation         |
| Metabolism                    | edu.stanford.covert.cell.sim.process.Metabolism                         |
| ProteinActivation             | edu.stanford.covert.cell.sim.process.ProteinActivation                  |
| ProteinDecay                  | edu.stanford.covert.cell.sim.process.ProteinDecay                       |
| ProteinFolding                | edu.stanford.covert.cell.sim.process.ProteinFolding                     |
| ProteinModification           | edu.stanford.covert.cell.sim.process.ProteinModification                |
| ProteinProcessingI            | edu.stanford.covert.cell.sim.process.ProteinProcessingI                 |
| ProteinProcessingII           | edu.stanford.covert.cell.sim.process.ProteinProcessingII                |
| ProteinTranslocation          | edu.stanford.covert.cell.sim.process.ProteinTranslocation               |
| RNADecay                      | edu.stanford.covert.cell.sim.process.RNADecay                           |
| RNAModification               | edu.stanford.covert.cell.sim.process.RNAModification                    |
| RNAProcessing                 | edu.stanford.covert.cell.sim.process.RNAProcessing                      |
| Replication                   | edu.stanford.covert.cell.sim.process.Replication                        |
| ReplicationInitiation         | edu.stanford.covert.cell.sim.process.ReplicationInitiation              |
| RibosomeAssembly              | edu.stanford.covert.cell.sim.process.RibosomeAssembly                   |
| TerminalOrganelleAssembly     | edu.stanford.covert.cell.sim.process.TerminalOrganelleAssembly          |
| Transcription                 | edu.stanford.covert.cell.sim.process.Transcription                      |
| TranscriptionalRegulation     | edu.stanford.covert.cell.sim.process.TranscriptionalRegulation          |
| Translation                   | edu.stanford.covert.cell.sim.process.Translation                        |
| tRNAAminoacylation            | edu.stanford.covert.cell.sim.process.tRNAAminoacylation                 |

| State                         | MATLAB class                                                            |
| ----------------------------- | ----------------------------------------------------------------------- |
| CellGeometry                  | edu.stanford.covert.cell.sim.state.CellGeometry                         |
| CellMass                      | edu.stanford.covert.cell.sim.state.CellMass                             |
| Chromosome                    | edu.stanford.covert.cell.sim.state.Chromosome                           |
| FtsZRing                      | edu.stanford.covert.cell.sim.state.FtsZRing                             |
| Host                          | edu.stanford.covert.cell.sim.state.Host                                 |
| MetabolicReaction             | edu.stanford.covert.cell.sim.state.MetabolicReaction                    |
| Metabolite                    | edu.stanford.covert.cell.sim.state.Metabolite                           |
| Polypeptide                   | edu.stanford.covert.cell.sim.state.Polypeptide                          |
| ProteinComplex                | edu.stanford.covert.cell.sim.state.ProteinComplex                       |
| ProteinMonomer                | edu.stanford.covert.cell.sim.state.ProteinMonomer                       |
| RNAPolymerase                 | edu.stanford.covert.cell.sim.state.RNAPolymerase                        |
| Ribosome                      | edu.stanford.covert.cell.sim.state.Ribosome                             |
| Rna                           | edu.stanford.covert.cell.sim.state.Rna                                  |
| Stimulus                      | edu.stanford.covert.cell.sim.state.Stimulus                             |
| Time                          | edu.stanford.covert.cell.sim.state.Time                                 |
| Transcript                    | edu.stanford.covert.cell.sim.state.Transcript                           |

## Unblocking real field-level extraction

To turn these into usable per-field oracles:

1. Add a Python MCOS subsystem decoder (the format is reverse-engineered
   in several community projects; not currently in our venv).
2. Wire it into `extract_per_process_fixtures.py` inside the
   `is_mcos` branch so `arrays`/`scalars` get populated from the parsed
   `before`/`after`/etc. struct.
3. Re-run `validate_per_process_fixtures.py --seed` to refresh hashes.

Until then, M2–M7 tests should treat any fixture whose
`extraction_status == "unparsed_mcos_payload"` as **skipped, not
failing** — the source `.mat` and its sha256 are preserved so the
oracle is recoverable later.
