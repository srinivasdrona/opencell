# STATUS: Cytokinesis Precondition (wid-length mismatch) Diagnosis

**Status:** verdict reached by 3-slot diagnostic (2026-06-18, ~22:54-23:00 IST)
**Pair:** `ChromosomeCondensation + Cytokinesis` (DS pair, was failing precondition)
**3-slot approach:** DAP + L2.5 precondition investigation template + case directive

Codex completed diagnosis but did not write STATUS file (output went to log only).
This document captures the verdict from the log for the record.

## Verbatim precondition assertion (from harness)

From `tests/vivarium/l2_2_replay_common_v2.py:761`:

```python
"L2.2.v2 precondition failed (wid-length mismatch): "
f"process={name}, observable={observable}, "
f"len(runtime_wids)={len(runtime_wids)}, len(initial_oracle_vector)={int(karr_before.shape[0])}"
```

## Reproduction

```powershell
bin\oc-pytest.cmd tests/vivarium/test_l25_deterministic_stochastic_pairs.py \
    -v -k "ChromosomeCondensation+Cytokinesis" --tb=long
```

Result: `len(runtime_wids)=4, len(initial_oracle_vector)=3`.

Single-process Cytokinesis replay (`test_karr_cytokinesis_l2_replay.py`)
PASSES — so the bug is specifically the harness/runtime WID contract,
not the Cytokinesis biology itself.

## Three-source WID comparison

| Source | Substrate WIDs | Count |
|---|---|---|
| OC runtime (`KarrCytokinesisProcess.__init__`) | `['GTP', 'H', 'H2O', 'PI']` | **4** |
| Trace oracle projection (states_before/substrates, tick 0) | length-3 vector | 3 |
| TOML `state_groups.substrates` (cytokinesis.toml:12) | `["PI", "H2O", "H"]` | 3 |
| Fixture `substrateWholeCellModelIDs` | `['PI', 'H2O', 'H']` | 3 |

## Root cause

`opencell/vivarium/karr_cytokinesis.py:160`:

```python
self._substrate_wids = sorted(set(self.fixture_substrate_wids + [self.gtp_wid]))
```

OC's Cytokinesis port adds `GTP` to its observable substrate WID list at
runtime, even though GTP is NOT in the fixture, NOT in the trace, NOT in
the TOML. This breaks the precondition that runtime WID count must match
trace projection length.

## Verdict

**(a) OC runtime is wrong.** Fixture + TOML + trace are all consistent
at 3 substrates (H, H2O, PI). OC's Cytokinesis fixture loader adds a
spurious GTP that isn't part of Karr's substrate contract for this
process.

## Why this doesn't affect single-process L2.1

Single-process L2.1 tests have looser projection logic — they tolerate
extra runtime WIDs by zero-padding or masking. L2.5 requires exact match
because the composition harness builds a master WID list across pairs
and exact length is required for vector alignment.

## Fix path

Modify `opencell/vivarium/karr_cytokinesis.py:160` to NOT add `gtp_wid`
to `_substrate_wids`:

```python
# OLD:
self._substrate_wids = sorted(set(self.fixture_substrate_wids + [self.gtp_wid]))

# NEW:
self._substrate_wids = sorted(set(self.fixture_substrate_wids))
```

Keep `self.gtp_wid` available for request/allocation plumbing (Cytokinesis
DOES request GTP from the allocator — that path uses `gtp_wid` separately
and does NOT need it in `_substrate_wids`).

**Verification after fix:**
1. `bin\oc-pytest.cmd tests/vivarium/test_karr_cytokinesis_l2_replay.py -v`
   — must still PASS (single-process regression check)
2. `bin\oc-pytest.cmd tests/vivarium/test_l25_deterministic_stochastic_pairs.py -v -k "Cytokinesis"`
   — should clear the 2 precondition failures (Cond+Cyt and Seg+Cyt)

## Generalization

Other PRECONDITION failures: only 1 process affected (Cytokinesis, 2 pair
failures). Localized fix, no broader pattern. Other processes may have
analogous "extra WID at init" issues — worth a quick audit but not
blocking.

## Provenance

- 3-slot prompt: `PROMPT_cytokinesis_precondition.md` (deleted after run)
- Codex PID: 36340, elapsed 5.5 min, ~10k tokens
- Verdict extracted from `.codex_cytokinesis_precondition.log` (codex did
  not commit STATUS due to no-modify hard rule limiting STATUS write path)
