# STATUS: DNARepair Chromosome Sparse Port

## Scope
Re-ported `opencell/vivarium/karr_dna_repair.py` to consume/write chromosome damage state via sparse triples (`ChromosomeStore`/`SparseTriplet`) for:
- `damagedBases`
- `strandBreaks`
- `gapSites`
- `abasicSites`
- `damagedSugarPhosphates`

## Karr / State Anchors Read (line-cited)
- `DNARepair.m` damage-state contract explicitly names these chromosome fields (`gapSites`, `abasicSites`, `damagedSugarPhosphates`, `damagedBases`, `strandBreaks`) as process-owned damage state (`E:\opencell\data\m1_sources\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+process\DNARepair.m:225-230`).
- `DNARepair.m` stochastic sequencing uses `rand` and `randperm` for subfunction order (`...\DNARepair.m:895-919`), and per-pathway site selection uses random ordering/binding (`...\DNARepair.m:935-967`, `1159-1163`, `1391-1397`).
- `DNARepair.m` chromosome writeback semantics mutate these sparse damage arrays in place during repair (`...\DNARepair.m:972-973`, `1009-1020`, `1047-1049`, `1074-1076`, `1214-1218`, `1444-1447`, `1480`).
- `Chromosome.m` declares these damage fields as sparse strand/position state (`E:\opencell\data\m1_sources\WholeCell\src\+edu\+stanford\+covert\+cell\+sim\+state\Chromosome.m:206-212`), initializes them as `CircularSparseMat` (`...\Chromosome.m:454-460`), and derives DSB from paired strand breaks (`...\Chromosome.m:3924-3925`).
- OpenCell sparse primitives used for port:
  - `sparse_triplet_schema` leaf structure (`opencell/state/chromosome_store.py:130-159`)
  - canonical sparse decode/shape handling (`opencell/state/chromosome_store.py:194-217`)
  - store mapping load/set (`opencell/state/chromosome_store.py:296-355`)
- Working reference pattern followed from DNASupercoiling:
  - chromosome sparse schema wiring (`opencell/vivarium/karr_dna_supercoiling.py:291-295`)
  - store resolve from chromosome state (`opencell/vivarium/karr_dna_supercoiling.py:580-588`)

## Code Changes
### 1) DNARepair sparse chromosome schema + read/write
- Added sparse-triplet chromosome schema entries for the five damage fields (`opencell/vivarium/karr_dna_repair.py:261-279`).
- Added chromosome shape config (`chromosome_length_bp`) and store-compatible shape setup (`opencell/vivarium/karr_dna_repair.py:137-152`).
- Replaced damage input sourcing to prefer sparse chromosome fields, with legacy event fallback retained (`opencell/vivarium/karr_dna_repair.py:320`, `391-399`).
- Implemented sparse field decoding into canonical repair sites, including DSB inference from paired strand breaks (`opencell/vivarium/karr_dna_repair.py:401-477`).
- Implemented sparse writeback that removes repaired coordinates from touched fields and emits updated sparse triplets (`opencell/vivarium/karr_dna_repair.py:479-543`).
- Preserved stochastic sampling path (`poisson`, `choice`) and substrate allocation behavior in existing methods (`opencell/vivarium/karr_dna_repair.py:688-697`, `582-598`, `330-337`).

### 2) DNARepair tests updated for sparse behavior
- Added sparse-triplet test helpers and sparse chromosome base state construction (`tests/vivarium/test_karr_dna_repair.py:36-125`).
- Updated update-apply helper to respect chromosome sparse-triplet set writes (`tests/vivarium/test_karr_dna_repair.py:133-137`).
- Added tests that explicitly verify sparse-field reads and sparse-field writeback (`tests/vivarium/test_karr_dna_repair.py:219-263`).
- Kept legacy mixed-type pathway-routing test via explicit event-only path (`tests/vivarium/test_karr_dna_repair.py:317-339`).

## Verification
Ran required command:
- `bin/oc-pytest tests/vivarium/test_karr_dna_repair.py tests/vivarium/test_karr_dna_repair_l2_replay.py -x -v`

Result:
- `10 passed, 2 warnings` (warnings are pre-existing Vivarium schema-updater warnings in chassis-seeded test path).

## Acceptance Checklist
1. [x] DNARepair reads chromosome damage fields as sparse triples
2. [x] DNARepair writes repair events back as sparse-triple deltas/writeback
3. [x] Stochastic behavior preserved (`randperm`/`rand`-style ordering and stochastic draws retained)
4. [x] Tests pass with required command
5. [x] Committed on this branch (`2894bcc`)

## Files Changed
- `opencell/vivarium/karr_dna_repair.py`
- `tests/vivarium/test_karr_dna_repair.py`
- `STATUS.md` (session progress log append entries)
- `STATUS_dna_repair.md` (this report)
