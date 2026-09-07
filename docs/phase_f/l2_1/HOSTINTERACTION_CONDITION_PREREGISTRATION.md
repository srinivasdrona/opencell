# HostInteraction Discriminating Condition Preregistration

**Date:** 2026-09-05
**Status:** PREREGISTERED — predictions below were written BEFORE the MATLAB
extraction in this section was run. See `HOSTINTERACTION_ACTIVE_WINDOW_DECISION.md`
§11 for the after-the-fact results comparison (never edited retroactively;
any correction is appended as a new dated note, never a silent edit to the
predictions below).

## Why this exists

Opus review (2026-09-05) correctly rejected the fitted-seed-0-only evidence
layer as degenerate: a trace where every one of the 6 host booleans is
constant-True for the entire window cannot, by itself, distinguish a
literal, source-faithful boolean cascade from a hardcoded `return
all-True` stub. Both would look identical against that one trace. This
document preregisters a set of genuine, source-legal, INPUT-SIDE
enzyme-knockout conditions (never touching Karr's own output booleans)
that discriminate every cascade stage, derived directly from
`HostInteraction.m`'s own formula (see
`HOSTINTERACTION_ACTIVE_WINDOW_DECISION.md` §2):

```
isBacteriumAdherent = all(terminalOrganelle) && all(adhesin)
isTLRActivated(1)   = isBacteriumAdherent && any(tlr12Ligand)
isTLRActivated(2)   = isBacteriumAdherent && (any(tlr12Ligand) || any(tlr26Ligand))
isTLRActivated(6)   = isBacteriumAdherent && any(tlr26Ligand)
isNFkBActivated     = (TLR2 && TLR1) || (TLR2 && TLR6)
isInflammatoryResponseActivated = isNFkBActivated || (isBacteriumAdherent && any(antigen))
```

Index sets (from `data/karr_fixtures/per_process/HostInteraction_flat.mat`,
1-indexed, WIDs resolved):

- `terminalOrganelle` = {MG_191, MG_192, MG_217, MG_218, MG_312, MG_317, MG_318, MG_386}
- `adhesin` = {MG_191, MG_192, MG_217, MG_318} (subset of terminalOrganelle)
- `tlr12Ligand` = {MG_149, MG_412, MG_410_411_412_PENTAMER}
- `tlr26Ligand` = {MG_309}
- `antigen` = {MG_075, MG_149, MG_309, MG_412, MG_410_411_412_PENTAMER}
- `MG_218` is in `terminalOrganelle` ONLY (not adhesin/tlr12Ligand/tlr26Ligand/antigen) — the clean single-WID adherence knockout target.
- `MG_075` is in `antigen` ONLY (not terminalOrganelle/adhesin/tlr12Ligand/tlr26Ligand) — the clean antigen-only-path probe.

All conditions extracted from the SAME genuine fitted seed-0 Simulation
(same `karr_bootstrap()`, same allocator-correct scheduler,
`scripts/matlab/extract_per_process_traces_v2.m`), overriding only the
listed enzyme WIDs to `0` via the new `extraction_opts.per_process_enzyme_overrides.HostInteraction`
surface (process-local `this.enzymes` override, applied fresh every tick;
never touches Karr's own `host` booleans, never touches any other
process's state). `n_ticks=5`, `tick_offset=0`, `window_contract='fixed'`,
`capture_signal_container=true` (same signal_kind/signal_property/
signal_field as the positive-control window). Every condition is a
**null or partial control** except `POSITIVE` (no override, already
extracted and accepted as `EXISTING_WINDOW_PASS` evidence).

## Preregistered conditions and predictions

| Condition ID | Enzyme override (all others at fitted baseline) | Predicted `host_attached` | Predicted `host_tlr1_activated` | Predicted `host_tlr2_activated` | Predicted `host_tlr6_activated` | Predicted `host_nfkb_activated` | Predicted `host_inflammatory_response_activated` | Purpose |
|---|---|---|---|---|---|---|---|---|
| `POSITIVE` | (none) | True | True | True | True | True | True | Positive control (already extracted; see main decision doc). |
| `NEG_ADHERENCE` | `MG_218_MONOMER=0` | **False** | False | False | False | False | False | Null control: single clean terminalOrganelle knockout must shut off the ENTIRE cascade, not just adherence. |
| `PARTIAL_ADHERENT_NO_SIGNAL` | `MG_075=0, MG_149=0, MG_309=0, MG_412=0, MG_410_411_412_PENTAMER=0` | True | False | False | False | False | False | Adherence alone is not sufficient for anything downstream — proves the AND-gating on ligand/antigen presence, not a partial-credit/threshold model. |
| `TLR12_PATH` | `MG_309=0` | True | **True** | True | **False** | **True** (via TLR1 disjunct) | True | Isolates the TLR1-only activation path for NF-kB; TLR6 must independently be False. |
| `TLR26_PATH` | `MG_149=0, MG_412=0, MG_410_411_412_PENTAMER=0` | True | **False** | True | **True** | **True** (via TLR6 disjunct) | True | Isolates the TLR6-only activation path for NF-kB; TLR1 must independently be False. Together with `TLR12_PATH`, proves NF-kB genuinely requires the TLR2 conjunct combined with EITHER TLR1 OR TLR6 (not a fabricated `TLR1 or TLR6` formula that silently drops the TLR2 term — TLR2 is structurally redundant with `any(tlr12) or any(tlr26)` per the source, so this is the strongest test the actual formula admits). |
| `ANTIGEN_ONLY` | `MG_149=0, MG_309=0, MG_412=0, MG_410_411_412_PENTAMER=0` | True | False | False | False | **False** | **True** (via antigen disjunct alone) | Isolates the antigen-only inflammatory-response path, independent of NF-kB — proves inflammatory response is a genuine OR, not merely a copy of NF-kB. |

## Acceptance rule (preregistered, fail-closed)

- The literal port (`opencell/vivarium/karr_host_interaction.py`) MUST
  reproduce every cell above bit-exact, for every condition, against the
  genuinely extracted MATLAB trace (not against this table — the table is
  the prediction to be checked, not the oracle).
- A trivial "constant-True" stub (`next_update` returning `host_attached`
  etc. always `True` regardless of `protein.counts`) MUST fail
  `NEG_ADHERENCE`, `PARTIAL_ADHERENT_NO_SIGNAL`, `TLR12_PATH` (on
  `host_tlr6_activated`), `TLR26_PATH` (on `host_tlr1_activated`), and
  `ANTIGEN_ONLY` (on `host_nfkb_activated`) — i.e. at least one field in
  every negative/partial condition must diverge from the stub's constant
  `True`.
- If any extracted MATLAB result disagrees with a prediction above, the
  prediction is WRONG (my source reading was wrong), not the trace — the
  fix is to correct the process/prediction and re-derive, documented as a
  dated correction, never a silent edit.
