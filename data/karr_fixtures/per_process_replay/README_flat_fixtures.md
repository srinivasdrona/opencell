# Flat Snapshot Replay Fixtures (`*_from_flat.npz`)

## Oracle kinds side-by-side

| Oracle kind | Source | Shape | Intended check |
| --- | --- | --- | --- |
| `trajectory_state_pairs` | `*_from_trajectory.npz` | tick-series `(n_pairs, 1, N)` | Integrated `(state_t -> state_t+1)` consistency over cell-cycle trajectory snapshots |
| `snapshot_state` | `*_from_flat.npz` | single snapshot vectors + dict payloads | Initial-state sanity and process-specific derived metrics from one extracted process snapshot |

`Replication` and `ReplicationInitiation` trajectory fixtures are useful for metabolite-projected deltas, but chromosome-internal state is not captured there; use `*_from_flat.npz` as the primary oracle for chromosome-focused checks.

## Processes covered in Track B Option B

| Process | Trajectory fixture | Flat fixture | Primary oracle |
| --- | --- | --- | --- |
| `Replication` | `Replication_from_trajectory.npz` | `Replication_from_flat.npz` | Flat snapshot (`snapshot_state`) |
| `ReplicationInitiation` | `ReplicationInitiation_from_trajectory.npz` | `ReplicationInitiation_from_flat.npz` | Flat snapshot (`snapshot_state`) |
| `ChromosomeCondensation` | n/a in trajectory builder | `ChromosomeCondensation_from_flat.npz` | Flat snapshot (`snapshot_state`) |
| `DnaSupercoiling` | n/a in trajectory builder | `DnaSupercoiling_from_flat.npz` | Flat snapshot (`snapshot_state`) |

## Build command

```powershell
py -3.12 scripts/build_replay_fixtures_from_flat.py --all-chromosome
```

Or per process:

```powershell
py -3.12 scripts/build_replay_fixtures_from_flat.py --process Replication
```

## Schema

Each `<Process>_from_flat.npz` contains:

- `initial__substrates`
- `initial__enzymes`
- `initial__boundEnzymes`
- `initial__chromosome` (dict serialized as object array)
- `params` (dict serialized as object array)
- `metadata` with:
  - `source = "flat"`
  - `oracle_kind = "snapshot_state"`
  - `process_name`
  - `extraction_timestamp`
  - `flat_path`
  - `fields_captured`

## Chromosome unpack strategy note

In these MATLAB v7 fixtures, `fixture.chromosome` is exposed by `scipy.io.loadmat` as a MATLAB handle reference string. The extractor stores that handle and also captures process-local chromosome-coupled fields in `initial__chromosome["process_local_fields"]` so pure-Python validation can still inspect chromosome-relevant snapshot context without MATLAB runtime dependencies.
