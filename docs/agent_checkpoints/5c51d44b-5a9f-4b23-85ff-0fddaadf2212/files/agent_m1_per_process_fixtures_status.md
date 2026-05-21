# M1 — Per-Process MAT Fixture Extraction — Status

**Branch:** `agent/m1-per-process-fixtures`
**Worktree:** `/mnt/e/opencell-worktrees/m1-per-process-fixtures`
**Final commit:** `1a4f92f8382a57107b856cd52d7e18505e432922`
   (single commit — split unnecessary, all changes are one logical unit)

## Headline

44 / 44 fixtures surveyed and committed as Python-native sidecars
(`<Name>.json` + `<Name>.npz`) — but **all 44 are flagged
`extraction_status = "unparsed_mcos_payload"`**.

Every source `.mat` is a MATLAB v5 file holding a single MCOS-serialized
class instance (`edu.stanford.covert.cell.sim.{process,state}.<Name>`).
The actual class field data lives inside the v5 `__function_workspace__`
subsystem blob, in MATLAB's *undocumented* MCOS format. None of the
Python-side MAT readers we have (`scipy.io.loadmat`, `pymatreader`,
`mat4py`) can decode MCOS — pymatreader explicitly warns
*"Complex objects (like classes) are not supported"*. Per the brief's
"no MATLAB call-out" constraint, we did **not** invoke MATLAB.

What is committed (best-effort, ~208 KB total):

* full provenance per fixture (source path, sha256, size, mat-format
  version, MCOS class name, `__function_workspace__` byte count),
* the 6-uint32 MCOS pointer array under
  `arrays["None/__mcos__/arr"]` (sentinel placeholder so future code
  can identify the fixture by class + ptr),
* a `manifest.json` listing all 44 entries,
* `fixture_hashes.json` for byte-exact validation,
* a `README.md` with consumption pattern + unblock recipe.

## Counts

| Kind     | Source dir                                                                                  | Count | Extracted | MCOS-blocked |
| -------- | ------------------------------------------------------------------------------------------- | ----- | --------- | ------------ |
| process  | `data/m1_sources/WholeCell/src_test/+edu/+stanford/+covert/+cell/+sim/+process/fixtures/`   | 28    | 28        | 28           |
| state    | `data/m1_sources/WholeCell/src_test/+edu/+stanford/+covert/+cell/+sim/+state/fixtures/`     | 16    | 16        | 16           |
| **all**  |                                                                                             | **44** | **44**   | **44**       |

No fixture failed scipy load, no v7.3/HDF5 file detected, no per-fixture
hard error. The "blocked" status is uniform and is a property of the
MAT format used (MCOS), not of any specific fixture.

## Total payload size

`du -sh data/karr_fixtures/per_process` → **208 KB** (well under the
50 MB-per-fixture flag threshold).

We deliberately did **not** commit the raw `__function_workspace__`
blobs (~3 GB total across all 44 fixtures) — they can be regenerated
losslessly from the upstream `data/m1_sources/WholeCell` clone (which
is gitignored and re-fetchable via
`git clone https://github.com/CovertLab/WholeCell`).

## Verification

```bash
.venv-wsl/bin/python scripts/validate_per_process_fixtures.py
# → 89 files compared, 0 mismatched, 0 missing, 0 unexpected
# → OK: per-process fixture payload matches committed hashes.
```

`git status` after the commit shows only the two scaffolding symlinks
in this worktree (`.venv-wsl` → main repo's venv, `data/m1_sources/WholeCell`
→ main repo's clone) as untracked; nothing else outside the spec is
modified.

## Sample loader snippet

```python
import json, numpy as np, pathlib, unittest

D = pathlib.Path("data/karr_fixtures/per_process")
meta = json.loads((D / "Transcription.json").read_text())
arrs = np.load(D / "Transcription.npz")

assert meta["manifest"]["mcos_class"].endswith(".Transcription")
if meta["manifest"]["extraction_status"] == "unparsed_mcos_payload":
    raise unittest.SkipTest(
        f"{meta['manifest']['name']} oracle blocked: MCOS subsystem "
        f"undecoded ({meta['manifest']['function_workspace_bytes']} "
        f"bytes); see data/karr_fixtures/per_process/README.md"
    )
# Once an MCOS decoder lands, .npz will hold real per-field arrays:
expected = arrs["before/state/rnaPolymerase/positionStrands"]
```

Spot-check (run on commit `1a4f92f`):

```
Transcription   arrays=['None/__mcos__/arr'] status=unparsed_mcos_payload
                class=edu.stanford.covert.cell.sim.process.Transcription
                fws_bytes=68716184
Metabolism      arrays=['None/__mcos__/arr'] status=unparsed_mcos_payload
                class=edu.stanford.covert.cell.sim.process.Metabolism
                fws_bytes=92497664
CellMass        arrays=['None/__mcos__/arr'] status=unparsed_mcos_payload
                class=edu.stanford.covert.cell.sim.state.CellMass
                fws_bytes=68720272
Time            fws_bytes=4376    Host  fws_bytes=3720    (small ones)
```

## Deviations from the brief (and why)

1. **`.npz` files contain only the MCOS pointer**, not the
   pre/post state arrays the brief expected. Reason: scipy/pymatreader
   refuse to decode the MCOS subsystem — these aren't plain MATLAB
   structs, they're serialized class instances. The brief's "DO NOT
   assume" survey directive correctly anticipated structure surprises;
   this is what we found. Each fixture is still emitted (idempotent,
   deterministic) so the wiring is already in place for the day a
   Python MCOS decoder is bundled.

2. **No raw `__function_workspace__` blob is committed.** The brief
   says "don't worry about size unless an individual fixture exceeds
   ~50 MB". 28 of 44 fixtures *individually* exceed 65 MB at the
   `__function_workspace__` byte count (Metabolism is 92 MB), and
   the aggregate would be ~3 GB. Since the data is unparsed and the
   source `.mat` is already accessible via the gitignored upstream
   clone, committing the blob would multiply repo size for zero
   downstream value. The script + sha256 manifest let any future
   MCOS-decoder run reproduce the full payload.

3. **Validator tempdir under `data/.tmp/`** (gitignored, added in
   this commit), not the system `/tmp`. Reason: the agent sandbox
   forbids writes to `/tmp`.

4. **Validator excludes `README.md`** from `fixture_hashes.json`
   coverage. Reason: README is human-maintained, not regenerated by
   the extractor; including it would cause the re-extract-and-diff
   check to fail spuriously.

5. **One commit, not several.** The brief permitted "multiple commits
   if logical". Given the entire payload is uniformly blocked at the
   same root cause, separate commits for "extract process / extract
   state / validation / manifest" would be artificial — they all
   ship the same single-liner of behaviour.

## Recommended next step

**Not ready to merge to main as a true M2–M7 oracle source.**
The committed payload's *manifest* is mergeable as-is (it tells M2–M7
"these fixtures exist, here's their provenance, skip until decoded"),
but the actual oracle data is **not** present.

To actually unblock M2–M7 unit tests against these per-process
fixtures we need one of:

* (preferred, Python-only) Add a Python MCOS subsystem decoder
  (community implementations exist; it would be a new dependency
  flagged for `pip install` rather than ad-hoc included). Then re-run
  `scripts/extract_per_process_fixtures.py --all` and
  `scripts/validate_per_process_fixtures.py --seed`. The script's
  `is_mcos` branch + `_flatten_struct` helper are already wired to
  populate `arrays`/`scalars` once a decoder hands us a real Python
  struct instead of a `MatlabOpaque`.
* (fallback) Re-export the fixtures from MATLAB as plain v5 structs
  (e.g. `save('Transcription.mat', '-struct', struct(o))`). This
  contradicts the post-MATLAB-eviction direction and would require
  sign-off; flagging only as a contingency, not a recommendation.

Until either path lands, M2–M7 tests should treat
`extraction_status == "unparsed_mcos_payload"` as a `SkipTest`, not
a failure (sample snippet above shows the pattern).

## Files committed (commit `1a4f92f`)

```
.gitignore                                                 (M, +1 line: data/.tmp/)
scripts/extract_per_process_fixtures.py                    (new, 234 lines)
scripts/validate_per_process_fixtures.py                   (new, 102 lines)
data/karr_fixtures/per_process/README.md                   (new)
data/karr_fixtures/per_process/manifest.json               (new, 44 entries)
data/karr_fixtures/per_process/fixture_hashes.json         (new, 89 hashes)
data/karr_fixtures/per_process/<Name>.json   x44           (new)
data/karr_fixtures/per_process/<Name>.npz    x44           (new)
```

94 files changed, 2628 insertions.
