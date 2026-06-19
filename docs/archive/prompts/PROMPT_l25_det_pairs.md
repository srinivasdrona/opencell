# Task: Wire 2 deterministic-deterministic L2.5 pair tests (bit-identity oracle)

Read `./SESSION_CONTEXT.md` for project rules.

## ⚠️ Python interpreter — MANDATORY
Use `bin\oc-pytest.cmd` and `bin\oc-py.cmd`. Do NOT run python directly.

## STATUS file
Write `docs/phase_f/STATUS_l25_deterministic_pairs.md` as you go.
Final message: "done, see STATUS".

## Commit cadence
Commit each pair as a separate beat with prefix `l25-det-pair:`.

## Goal

Wire the 2 deterministic↔deterministic L2.5 pair tests. These are the
"strictest" pairs (per L2_5_ACCEPTANCE_RUBRIC.md) — both sides require
bit-identity against L2.1 traces under composition with shared substrate
pool. If composition is wired correctly, these SHOULD pass trivially
because there's no RNG to diverge.

## The 2 pairs

### Pair 1: ChromosomeCondensation ↔ ChromosomeSegregation
- **Shared overlap:** 3 substrates [H, H2O, PI]
- **Biology:** both processes consume ATP (separately) and release H+/H2O/Pi
  as byproducts. The shared substrates are the metabolic exhaust pool —
  potential allocator interference if both write the same WID.
- **Risk:** allocator might give both processes the same substrate budget
  twice, causing double-counting. Bit-identity assertion will catch this.

### Pair 2: HostInteraction ↔ TerminalOrganelleAssembly
- **Shared overlap:** 4 enzymes [MG_218_MONOMER, MG_312_MONOMER, MG_317_MONOMER, MG_318_MONOMER]
- **Biology:** both processes use the same adhesion proteins. Shared
  enzymes mean both processes read the same enzyme counts.
- **Risk:** if one process modifies bound vs free enzymes inconsistently,
  the other will see stale counts. Composition order matters.

## Approach

### Step 1: Check existing harness support for bit-identity oracle

Look at:
- `tests/vivarium/l2_2_replay_common_v2.py` — composition harness (currently
  distributional-only)
- `tests/vivarium/l2_replay_common.py` — has `assert_identity_or_tolerance`
  with rtol=0, atol=0 support

The composition harness MUST be extensible to handle per-side oracle types
without breaking existing 211 stochastic-stochastic pair flow. Two options:
- Add `oracle_type` param to `run_integrated_replay_v2` and switch
  per-process assertion
- Subclass / wrap with a `run_bit_identity_composition` helper

Pick whichever is cleaner. Document choice in STATUS.

### Step 2: Create the test files

```
tests/vivarium/test_l25_chromosome_condensation_plus_segregation.py
tests/vivarium/test_l25_host_interaction_plus_terminal_organelle.py
```

Each test:
1. Loads both processes' L2.1 traces (`per_process_traces_v2/<Name>_100ticks.mat`)
2. Runs composition with shared substrate pool, `disable_trace_hints=True`
3. For each tick, asserts both processes' observable channels are
   bit-identical to their L2.1 trace's `states_after[tick]`
4. Fail mode: report which WID diverged on which side, with the diff value
   (similar to CAUSE_1-7 structured failure)

### Step 3: Run them and report what happens

The cheeky expectation is they pass on first try (both sides deterministic,
no RNG). If they fail, the failure is interesting — it exposes a real
composition bug we couldn't catch at L2.1 single-process.

## Required behavior matrix

| Process | L2.1 oracle | Composition behavior | Expected match |
|---|---|---|---|
| ChromosomeCondensation | per_process_traces_v2/ChromosomeCondensation_100ticks.mat | Reads substrates, writes condensation_progress | Bit-identical states_after |
| ChromosomeSegregation | per_process_traces_v2/ChromosomeSegregation_100ticks.mat | Reads substrates, writes segregation_progress | Bit-identical states_after |
| HostInteraction | per_process_traces_v2/HostInteraction_100ticks.mat | Reads/writes shared adhesion enzymes | Bit-identical states_after |
| TerminalOrganelleAssembly | per_process_traces_v2/TerminalOrganelleAssembly_100ticks.mat | Reads/writes shared adhesion enzymes + substrates | Bit-identical states_after |

## Files you may read (read-set)

- `data/m1_sources/karr_native/per_process_traces_v2/ChromosomeCondensation_100ticks.mat`
- `data/m1_sources/karr_native/per_process_traces_v2/ChromosomeSegregation_100ticks.mat`
- `data/m1_sources/karr_native/per_process_traces_v2/HostInteraction_100ticks.mat`
- `data/m1_sources/karr_native/per_process_traces_v2/TerminalOrganelleAssembly_100ticks.mat`
- `opencell/vivarium/karr_chromosome_condensation.py`
- `opencell/vivarium/karr_chromosome_segregation.py`
- `opencell/vivarium/karr_host_interaction.py`
- `opencell/vivarium/karr_terminal_organelle_assembly.py`
- `tests/vivarium/l2_2_replay_common_v2.py`
- `tests/vivarium/l2_replay_common.py`
- `tests/vivarium/test_karr_chromosome_condensation_l2_replay.py` (reference: single-process L2.1 test)
- `tests/vivarium/test_l2_2_translation_plus_rna_processing_v2.py` (reference: pair test scaffold)
- `data/schemas/per_process/{chromosome_condensation,chromosome_segregation,host_interaction,terminal_organelle_assembly}.toml`
- `docs/phase_f/L2_5_PAIR_MATRIX.md`
- `docs/phase_f/L2_5_ACCEPTANCE_RUBRIC.md`
- `data/schemas/l25_pair_list.toml`

## Files you may write (write-set)

- `tests/vivarium/test_l25_chromosome_condensation_plus_segregation.py` (NEW)
- `tests/vivarium/test_l25_host_interaction_plus_terminal_organelle.py` (NEW)
- `tests/vivarium/l2_2_replay_common_v2.py` (MAY MODIFY — add bit-identity support if needed)
- `docs/phase_f/STATUS_l25_deterministic_pairs.md`

DO NOT modify:
- Process implementations (`opencell/vivarium/karr_*.py`)
- Per-process TOMLs
- PROCESS_CATALOG.yaml
- Other test infrastructure (`l2_replay_common.py`, etc.)

## Acceptance criteria

1. Two new test files created
2. `bin\oc-pytest.cmd tests/vivarium/test_l25_chromosome_condensation_plus_segregation.py -v` runs (PASS or FAIL, document either)
3. `bin\oc-pytest.cmd tests/vivarium/test_l25_host_interaction_plus_terminal_organelle.py -v` runs
4. If PASS: 1-line victory note in STATUS
5. If FAIL: structured failure record showing which WID, which tick, which side, oc_val vs karr_val
6. At least 2 commits with `l25-det-pair:` prefix
7. STATUS doc explains harness extension choice + per-pair outcome

## Hard rules

- DO NOT modify the process implementations to make tests pass
- DO NOT lower the bit-identity bar (rtol=0, atol=0 is the bar)
- If existing harness can't handle bit-identity, extend it minimally;
  don't rewrite
- Use `disable_trace_hints=True` (these are deterministic — they shouldn't
  need hints anyway)
- If you exceed 80k tokens, stop and write STATUS with partial results
