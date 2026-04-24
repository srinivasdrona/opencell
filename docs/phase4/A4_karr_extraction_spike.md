# A4 — Karr 2012 `.mat` extraction spike (v0.1)

**Status:** done.
**Spike script:** `scripts/karr_mat_spike.py`
**Fixture:** `data/karr_fixtures/MetabolicReaction.mat`
(7,598 bytes, sha256 `817585b3…317342d`).
**Source:** `CovertLab/WholeCell` master branch,
`src_test/+edu/+stanford/+covert/+cell/+sim/+state/fixtures/MetabolicReaction.mat`.
**A3 artefact:** `artifacts/karr_a4_provenance.jsonl` (1 event).

## What we set out to do

Open one Karr 2012 `.mat` file, extract one parameter into the A3 provenance
store with full source-ref + transformation lineage, and assess whether the
extracted value is *interpretable* — not just retrievable.

## What we found

### Mechanics: pass.

`scipy.io.loadmat(squeeze_me=False, struct_as_record=True)` loads the file
without error. The top-level key is the empty string (rendered as `'None'` in
the walker output) — i.e. the file holds a single anonymous MATLAB struct
with four fields: `s0`, `s1`, `s2`, `arr`.

The first numeric leaf the walker reaches is:

```
path:    "None.arr[0]"
shape:   (6, 1)
dtype:   uint32
values:  [3707764736, 2, 1, …]
```

That value is recorded in the A3 store as event id `5aeb0828fe8bf000` with
`unit = "UNKNOWN_unit_not_recoverable_from_mat_alone"`, full source URL +
SHA256, and a transformation lineage that names the raw key path.

### Semantics: fail (and that is the headline finding).

1. **Field names are opaque.** `s0`, `s1`, `s2`, `arr` carry zero biological
   meaning. There is no inline metadata, no unit annotation, no species/
   reaction name vector. The `.mat` is purely a state snapshot for a MATLAB
   class instance; the field-to-meaning mapping lives in the corresponding
   `.m` source file
   (`src/+edu/+stanford/+covert/+cell/+sim/+state/MetabolicReaction.m`),
   which we did not fetch.
2. **The "first parameter" is not a parameter at all.** `3707764736` is on
   the order of `2^32 − 0x2C00_0000`. uint32 values of that magnitude in a
   MATLAB struct field named `arr` are overwhelmingly likely to be a
   MATLAB object handle or class-version tag, not a kinetic constant or
   stoichiometric entry. Naive extraction yields nonsense.
3. **The cell array hides cardinality.** `arr` is shape `(1,)` of `dtype=object`
   — a MATLAB cell array. Each cell holds a separate uint32 vector of
   length 6. Without the class definition we cannot tell whether each cell
   corresponds to a reaction, a compartment, a stoichiometry row, or a
   bookkeeping field of the simulator state object itself.

### What the spike implies for M-phase Karr porting

* **Going via `.mat` fixtures alone is not viable.** Even with bulletproof
  ingestion, we get bytes without meaning. Anyone porting Karr from `.mat`
  must read the matching `.m` source for every state class to recover the
  field-to-biology mapping.
* **Therefore the M-phase ingestion path is `.m` source first, `.mat` second.**
  The `.m` defines the columns; the `.mat` populates them. Reversing that
  order produces a parameter store full of what the A3 store cheerfully
  records but no human can interpret.
* **Bounded-tuning policy needs an upstream "bounded-meaning" check.** A
  parameter without a recoverable unit and biological scope must not enter
  any kinetic model — even if it loads cleanly. The A3 store records this
  honestly via the `UNKNOWN_*` unit string and a loud `notes` field, but
  the lint that *blocks* such records from being consumed by a model
  belongs in v0.2.
* **The rough end-state need not be 525-gene parity.** Several Karr state
  classes (`MetabolicReaction`, `Mass`, `Geometry`, `Time`) are small
  enough to interpret manually with the `.m` source; others
  (`ProteinComplex`, `Transcript`, `RNAPolymerase`) are vast and probably
  need the WholeCell test framework standing up, not just `scipy.io`.

### Cross-reference to A6 (semantics contract)

A6 §5.1 already calls out "phenotype outputs require both numeric value and
its unit; bare numbers are diff-incomparable". A4 confirms the same rule
applies upstream of phenotype, all the way to ingestion. The A6 next
revision should add an §0 ingestion-semantics rule:

> No value enters the live parameter store without a recoverable unit AND
> a recoverable biological scope. `.mat` snapshots without paired `.m` source
> fail this rule even when they parse.

## Verdict

* **Go / no-go on Karr port via `.mat`-only:** **no go**. Continue only if
  paired with `.m` source ingestion (treat `.m` as ground truth for
  field-to-biology mapping; `.mat` as numeric population).
* **A3 store behaviour under intentionally-opaque input:** correct. It
  records what was extracted, exposes the unit gap loudly, and does not
  silently invent meaning.
* **Bytes-extracted from one fixture:** 6 uint32 values from
  `None.arr[0]` plus walk dump.
* **Biologically-usable parameters extracted:** **0**. This is the honest
  answer and the correct result for v0.1 of the spike.

## Future work (M-phase scope)

1. Clone the WholeCell repo (sparse `--filter=blob:none --depth 1` for
   `src/+edu/+stanford/+covert/+cell/+sim/+state/*.m`).
2. For each `.m` state class, read the `setup()` and `allocateMemory()`
   methods to recover `s0/s1/s2/arr` field semantics.
3. Re-run the A4 spike against `Mass.mat`, `Geometry.mat`, `Time.mat`
   first (the simplest classes) with `.m`-derived field maps.
4. Generalise the spike into `tools/karr_extract.py` with per-class field
   maps as YAML; spike → tool only after at least 3 state classes are
   manually understood end-to-end.
