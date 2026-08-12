# OpenCell 🧬

**Open-source whole-cell simulation framework, built on
[Vivarium-core](https://vivarium-core.readthedocs.io/). Pure Python
(NumPy/SciPy), CPU-native. *Mycoplasma genitalium* reference, with
explicit L-ladder validation, anti-laundering detection, and intervention
API. Designed for ML method validation, causal discovery benchmarking,
and reproducible Bio-AI research.**

> *"A hallucinating agent and a biology noob walked into a cell..."*

## What is this?

OpenCell is a modern, modular, reproducible port of the
[Karr 2012 *M. genitalium* whole-cell model](https://www.cell.com/cell/fulltext/S0092-8674(12)00776-3)
from MATLAB to Python, built on the Vivarium-core simulation framework.

**Design goals:**

1. **Validated against Karr's MATLAB** — the goal is per-process evidence
   against the original MATLAB oracle traces: same-seed replay at L2.1 for
   all 28 processes, and distributional fidelity at L2.2 for the 22
   processes with a stochastic surface worth a distributional gate. This
   is the target, not the current state — see [Status](#status--checkpoint-2026-08-03).
2. **Composable** — 28 biological processes + allocator, each a separate
   `Process` class with declared ports. Drop in a DNN surrogate, an ODE
   model, or a different algorithm without touching neighbors.
3. **Reproducible** — every result ties to a `reference_data_manifest`
   capturing MATLAB commit, fixture date, RNG seed, dependency lockfile,
   and hardware fingerprint.
4. **Tested for oracle leakage** — runtime `PRIMARY_CHANNEL_ORACLE_LAUNDERING`
   detector catches benchmarks that secretly read from the ground-truth
   trace instead of computing independently.

## Status — checkpoint 2026-08-03

Rung *definitions* live in
[`docs/phase_f/L_LADDER_CANONICAL.md`](docs/phase_f/L_LADDER_CANONICAL.md)
(the only normative source; deliberately status-free). Current *state* lives
in [`docs/phase_f/CHECKPOINT_2026-08-03.md`](docs/phase_f/CHECKPOINT_2026-08-03.md).
This section summarises that checkpoint and defers to it on every detail.

### Read the denominator first

OpenCell ports **28 Karr processes. 28 is the denominator** for every claim
about coverage, completeness or progress. Two smaller numbers appear
constantly in the evidence tree and are **validation-profile scopes, never
process totals**:

- **22** — processes flagged `in_scope_L2_2`, i.e. those with a stochastic
  surface worth a *distributional* gate at all. The rest are
  deterministic-bucket and out of L2.2 scope by design, not by omission.
- **18** — of those 22, the rows routed to the Design-A per-tick harness.
  The other 4 route to the event-class harness.

"18/28 green" is a category error: it grades a per-tick-harness row count
against the whole roster. The correct forms are "n of 18 Design-A per-tick
rows", "n of 22 L2.2 in-scope processes", or "n of 28 processes at rung X".

### Ladder snapshot

| Rung | What it proves | Checkpoint status |
|---|---|---|
| L1a | the process fires and mutates state | 28/28 aliveness baseline |
| L1b | the wiring record matches the code | 28/28 method/wiring conformance |
| L2.0 | declared channels are the oracle's channels | 28/28 static schema |
| L2.0a | the allocator hands each process the right inputs | 403/403 cases |
| L2.1 | same-seed replay reproduces one Karr trace | **22 GENUINE / 5 MISSING_ACTIVE_EXTRACTION / 1 FAIL** (active-window-aware) |
| L2.2 | the *distribution* is right across seeds | **16 PASS / 3 FAIL / 3 MISSING_EVIDENCE of 22 in scope — aggregate `NON_GREEN`** |
| L2.4 | the free-running chassis conserves mass | PASS, 100 ticks × 4 seeds |
| L2.5 | processes compose through the shared pool | **no currently certified pair set** — not started under the honest rebuild |
| L3 | processes compose through direct hand-off | not started |
| L4 / L5 | cluster vs Karr submodel / whole-cell phenotype | not started |

L2.2 authority is the mechanically re-derived
[`docs/phase_f/l2_2_design_a/evidence_index.json`](docs/phase_f/l2_2_design_a/evidence_index.json)
— re-derive it before quoting these counts after any source or evaluator
change. Stored verdict strings, tracker tables and status docs are never
authority.

Only **L2.1 and above** put a Karr oracle at process outputs. L1a, L1b, L2.0,
L2.0a and L2.4 are *structural* gates: they can prove the port is internally
incoherent, never that it is biologically right. L2.1's non-GENUINE rows are
not all implementation failures — stochastic, event, windowed and
condition-gated processes require their applicable fidelity profile;
`ChromosomeCondensation` is the one literal L2.1 FAIL.

### What is explicitly *not* green

No event, windowed, stress or condition-gated diagnostic currently certifies
anything. Per the checkpoint:

- **RibosomeAssembly** and **Cytokinesis** — event adapters are *structural
  and unregistered*. RibosomeAssembly's structural smoke is `NOT_APPLICABLE`
  and the real gate refuses at 1/50 seeds; Cytokinesis Canary D reached tick
  25,361 before exposing the `mnrnd` shim defect and its retry is paused.
- **FtsZPolymerization** — reframed as an honest windowed diagnostic. The one
  available seed is non-vacuous and invariant-clean but terminates
  `INSUFFICIENT_ENSEMBLE`; it cannot PASS at N=1.
- **ProteinProcessingII** — natural row remains `H12_OBSERVED_REGIME`
  (non-green). The `transferase_capacity_scarce` canary is explicitly
  non-gating and unblocks nothing.
- **MacromolecularComplexation** — the `CONDITION_GATED_CANDIDATE` is
  hardened but non-operative; lifecycle reachability is `UNRESOLVED` and the
  candidate changes no verdict.
- **DNADamage** — a synthetic, explicitly non-biological mechanism-stress
  profile is preregistered but *unexecuted*; no live registry or catalog
  change exists.
- **Replication** — the literal topology restart branch is not integrated and
  N=50 is denied; bypass diagnostics are causality probes, not acceptance.
- **DNASupercoiling** — the canonical row is `FAIL /
  PRIMARY_INSUFFICIENT_SAMPLES`; the powered N=100 diagnostic is supplemental
  and non-gating.

Candidate, preregistered and supplemental artifacts are non-gating by
construction. Nothing above L2.2 resumes until these have terminal, reviewed
dispositions and the lower-gate evidence is regenerated on the final tree.

## Architecture

- **Engine**: [Vivarium-core](https://github.com/vivarium-collective/vivarium-core)
  (modular simulation framework with declared ports, atomic delta merges,
  multi-timescale support via per-process timesteps)
- **Language**: Python 3.12, NumPy, SciPy (no JAX, no GPU dependencies)
- **State**: schema-driven via per-process TOMLs (`data/schemas/per_process/*.toml`)
- **Processes**: 28 biological + 1 allocator, each a separate
  `vivarium.core.Process` subclass with declared `ports_schema` and
  `next_update(timestep, states) → delta_dict`
- **Validation**: the L-ladder (L1a → L5), with per-process evidence against
  MATLAB oracle traces from L2.1 upward and a runtime anti-laundering
  detector; definitions in `docs/phase_f/L_LADDER_CANONICAL.md`

## Quick Start

```powershell
# Clone
git clone https://github.com/srinivasdrona/opencell.git
cd opencell

# WSL venv setup (required — pure Windows Python lacks vivarium-core deps)
wsl bash -lc "cd /mnt/e/opencell && python3.12 -m venv .venv-wsl && \
              source .venv-wsl/bin/activate && pip install -e '.[dev]'"

# Run tests (via WSL wrapper)
bin\oc-pytest tests/
```

## Repository structure

```
opencell/
├── opencell/                  # Main package
│   ├── vivarium/              # 28 Karr process implementations (karr_*.py)
│   ├── state/                 # Chromosome sparse-triple store
│   ├── m3/                    # M3 v3 mechanism-based modules
│   ├── analysis/              # Phenotype analysis
│   └── m_gen_constants.py     # Biology-specific constants (centralized)
├── tests/                     # L1-L5 validation tests
│   └── vivarium/              # Per-process L2.1 replay + L2.5 composition
├── data/
│   ├── karr_fixtures/         # MATLAB-derived runtime fixtures (*_flat.mat)
│   ├── m1_sources/            # Karr 2012 MATLAB source + extracted traces
│   └── schemas/per_process/   # Per-process TOML schemas (state_groups, observables)
├── docs/
│   ├── phase_f/               # L2.x validation specs + status
│   ├── specs/                 # Architectural specs (INTERVENTION_API, POST_L5_ROADMAP, etc.)
│   ├── karr_extracts/         # MATLAB docstring extracts
│   └── blog/                  # Dev log series
├── scripts/                   # Extraction + derivation tooling
└── decisions/                 # Architecture Decision Records
```

## Use cases

### Today (pre-L5)

This codebase is most useful right now if you want to:

- Study how a 28-process composable simulator is wired with Vivarium
- Use the L-ladder validation methodology in your own simulation projects
- Use the anti-laundering detector pattern for ML benchmark integrity
- Watch a real port-from-MATLAB project navigate trade-offs honestly

### Post-L5 roadmap

See `docs/specs/POST_L5_ROADMAP.md` for the full plan:

- Reproducible WCM tool (the primary deliverable)
- Bio-AI Hello World benchmark
- OpenAI Gym environment for cellular RL
- Causal discovery benchmark
- Synthetic data factory for surrogate model validation
- Educational / tutorial materials
- Mutagenesis study design

The roadmap explicitly rejects: drug discovery, direct human disease
modeling, GPU-accelerated screens, JAX-based differentiable bio. See
the roadmap doc for why and what to point users to instead.

## Documentation

Start here:

- **Ladder definitions (normative)**: [`docs/phase_f/L_LADDER_CANONICAL.md`](docs/phase_f/L_LADDER_CANONICAL.md)
  — what each rung means, applicability, terminal states, ordering rules
- **Current dated state**: [`docs/phase_f/CHECKPOINT_2026-08-03.md`](docs/phase_f/CHECKPOINT_2026-08-03.md)
- **L2.2 mechanical verdicts**: [`docs/phase_f/l2_2_design_a/evidence_index.json`](docs/phase_f/l2_2_design_a/evidence_index.json)
- **L2.event routing/adapter status**: [`docs/phase_f/l2_event/event_registry.yaml`](docs/phase_f/l2_event/event_registry.yaml),
  [`docs/phase_f/l2_event/evidence_index.json`](docs/phase_f/l2_event/evidence_index.json)
- **Latest dev-log post**: [Days 64-74 — the dictionary we deleted, the canary that died at tick 25,361](docs/blog/2026-08-03-days-64-74-the-dictionary-we-deleted-the-canary-that-died-at-tick-25361-and-the-bottleneck-that-turned-out-to-be-me.md)
  (full series in [`docs/blog/`](docs/blog/))

Also:

- **Operational state and open work**: [`plan.md`](plan.md)
- **Post-L5 roadmap**: [`docs/specs/POST_L5_ROADMAP.md`](docs/specs/POST_L5_ROADMAP.md)
- **Architectural specs**: [`docs/specs/INTERVENTION_API.md`](docs/specs/INTERVENTION_API.md),
  `DATA_EMIT_SCHEMA.yaml`, `REFERENCE_DATA_MANIFEST.yaml`, `POST_L5_REFACTOR_PLAN.md`

Older per-process trackers under `docs/phase_e/` and `docs/phase_f/` (including
the 29-row status table, the L2.2 gate tracker and the L2.5 pair tracker /
matrix) are **historical inputs, not current authority**, until a dated
checkpoint explicitly reconciles them. Do not quote counts from them.

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Citation

A formal citation will be available after the biology validation paper
ships (post-L5). Until then, if you reference this work, please link to
the repo and commit:

```bibtex
@software{opencell2026,
  title = {OpenCell: Open-Source Whole-Cell Simulation},
  author = {Drona, Srinivas},
  year = {2026},
  url = {https://github.com/srinivasdrona/opencell}
}
```

## Acknowledgments

This work is a faithful port of the Karr 2012 *M. genitalium*
whole-cell model:

> Karr JR, Sanghvi JC, Macklin DN, Gutschow MV, Jacobs JM, Bolival B Jr,
> Assad-Garcia N, Glass JI, Covert MW. "A whole-cell computational
> model predicts phenotype from genotype." *Cell* 150(2):389-401 (2012).
> DOI: [10.1016/j.cell.2012.05.044](https://doi.org/10.1016/j.cell.2012.05.044)

Built on [Vivarium-core](https://github.com/vivarium-collective/vivarium-core)
by the Vivarium Collective.
