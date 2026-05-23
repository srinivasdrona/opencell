# Known intentional test skips

Last reviewed: 2026-05-23

After deletion of the chassis_v5/v6 skeleton stubs (committed 2026-05-23), the
remaining 11 skipped tests are **all intentional** and gated on an external data
artifact. Do not attempt to "fix" them by reactivating; the gate is correct.

## Thattai 2001 paper cache (11 skips)

These tests exercise curation/extraction pipelines against the full text of
Thattai & van Oudenaarden 2001 ("Intrinsic noise in gene regulatory networks",
PNAS 98(15):8614-8619). They require the cached paper at:

```
.paper_cache/thattai2001_full.txt
```

That file is gitignored (copyrighted content; not redistributable). The skips
are emitted by `pytest.skip(...)` guards at module load time when the file is
absent, which is the normal state in a fresh clone.

### Affected tests

| File | Lines | Count |
|---|---|---:|
| `tests/unit/test_curation.py` | 638, 649, 665 | 3 |
| `tests/unit/test_extraction.py` | 143, 157, 172, 177, 190, 202, 222, 250 | 8 |
| **Total** | | **11** |

### Why we do NOT re-cache

- These tests passed historically (verified across commits `a265de1`, `cf6a1ad`,
  and current main during the skip-drift audit of 2026-05-23). The gate works.
- The curation/extraction code paths they cover are stable; reactivating them
  in CI would require either bundling copyrighted text (no) or a network fetch
  step (slow, fragile, out-of-scope for v1.0).
- Per skip-drift audit (`STATUS.md` on branch `agent/skip-drift-audit`,
  2026-05-23): zero rename-caused drift, zero genuine regressions hidden behind
  these skips.

If you ever need to run these locally, drop the paper text at the path above
and rerun pytest; no other setup is required.

## Expected pytest baseline (post-skeleton-deletion)

```
885 passed, 11 skipped, 4 xfailed
```

If skip count drifts from 11 (in either direction), investigate before merging.
