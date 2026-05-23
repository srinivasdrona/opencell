# Phase E.2 — 28-Phenotype Scorecard Design

**Status**: design ready (this doc)  
**Prereq**: E.1 PASS + chassis_v6 on main  
**Branch**: `agent/pe-2-phenotype-scorecard`  
**Wall-time**: 60-90 min Codex (registry impl + 28 extractors + Karr-value sourcing + tests)

## 1. Goal

For a single full-cycle (32400-tick) chassis_v6 run, extract the 28 quantitative
phenotypes (KP01–KP28) defined in `pd_final_chassis_v6.md`, compare against Karr
2012 paper + supplements, and emit a scorecard with per-KP PASS/FAIL/BLOCKED status.

## 2. Module layout

```
opencell/validation/
  phenotype_registry.py      # PhenotypeDef dataclass + PHENOTYPES dict
  phenotype_extractors.py    # 28 extractor functions: (trajectory, run_meta) -> float | NaN
  karr_reference_values.py   # KP01..KP28 Karr published values + citations
  phenotype_scorecard.py     # score(trajectory) -> ScorecardRow[]
docs/phase_e/
  E2_scorecard.md            # output artifact, written by scorecard.py
tests/validation/
  test_e2_phenotype_scorecard.py
data/phase_e/
  v6_trajectory_32400s.pkl  # canonical E.1 fixture (schema_version=1)
```

## 3. PhenotypeDef dataclass

```python
from dataclasses import dataclass
from typing import Callable, Literal

Bucket = Literal["opencell-tooling", "validation-and-organism-scaling",
                 "karr-known-incomplete", "biology-beyond-Karr"]

@dataclass(frozen=True)
class PhenotypeDef:
    id: str                                 # "KP07"
    label: str                              # "mRNA short-horizon stability"
    bucket: Bucket
    extractor: Callable[[Trajectory], float | None]  # None = BLOCKED
    karr_value: float | None                # from karr_reference_values; None if not yet sourced
    karr_citation: str                      # e.g. "Karr 2012 Cell 150(2) Fig 3b" or "Sup Table S6 row 14"
    rel_tol: float                          # bucket default; overridable per-KP
    notes: str = ""                         # explain BLOCKED / xfail reasons
```

`Trajectory` is the dict returned by Vivarium's `experiment.emitter.get_timeseries()`
(nested mapping; tip-level values are arrays indexed by emit-stride).

## 4. Bucket-default tolerances

| Bucket | rel_tol default | PASS criterion |
|---|---|---|
| opencell-tooling | 0.001 (0.1%) | abs(opencell - karr) / abs(karr) ≤ rel_tol |
| validation-and-organism-scaling | 0.30 (30%) | same formula |
| karr-known-incomplete | 1.5 (ratio 0.4×–2.5×) | 0.4 ≤ opencell/karr ≤ 2.5 |
| biology-beyond-Karr | qualitative | extractor returns bool; PASS = True |

Special: if `extractor` returns `None`, status = **BLOCKED** (counts neither as
PASS nor FAIL; documented as known v1 limitation; does not gate release).

## 5. 28 phenotypes — extractor & bucket assignment

Below is the canonical PHENOTYPES table. Each `extractor` is one or two lines of
Python; Codex implements them by reading the trajectory dict per the path in
`pd_final_chassis_v6.md` lines 144-173. `karr_value` left as `None` (with citation
hint) where Codex must source from the paper during implementation.

| ID | Label | Bucket | Extractor sketch | Karr value source |
|---|---|---|---|---|
| KP01 | Growth rate (g/s) | opencell-tooling | `mean(traj["metabolic_reaction"]["growth_per_s"][stable_window])` | Karr 2012 Fig 3a; ≈ 0.060 |
| KP02 | Doubling time (s) | validation-and-organism-scaling | `traj["events"]["division"]["timestamp_s"][0]` | Karr 2012 Fig 3a; ≈ 32400 (9h target) |
| KP03 | Flux-oracle agreement | opencell-tooling | mean abs rel-err of fluxs vs internal oracle (qualitative scalar) | derive from m1_oracle fixture |
| KP04 | Glucose uptake (PTS) | validation-and-organism-scaling | `mean(traj["metabolic_reaction"]["fluxs"]["TX_GLCPTS"])` | Karr Sup Tbl S6 |
| KP05 | Total mRNA abundance | validation-and-organism-scaling | `sum(traj["rna"]["counts"][-1])` | Karr Sup Tbl S3; ≈ 250-300 |
| KP06 | Total protein abundance | validation-and-organism-scaling | `sum(traj["protein"]["counts"][-1])` | Karr Sup Tbl S3; ≈ 1e7 |
| KP07 | mRNA short-horizon stability | opencell-tooling | std(sum_counts) / mean(sum_counts) over 100s window | qualitative; tol = 0.30 |
| KP08 | Protein short-horizon stability | opencell-tooling | same metric on protein counts | qualitative; tol = 0.10 |
| KP09 | Amino-acid pool stability | opencell-tooling | std/mean of aa pools over 100s | tol = 0.10 |
| KP10 | Cell dry mass (g) at division | validation-and-organism-scaling | `traj["cell_geometry"]["dry_mass_g"][division_idx]` | Karr Fig 3b; ≈ 1.3e-13 |
| KP11 | Replication initiation timing (s) | karr-known-incomplete | first tick where `replication_state == "replicating"` | Karr Fig 3c; ≈ 4500 |
| KP12 | Replication duration (s) | karr-known-incomplete | end_tick - start_tick of replication state | Karr Fig 3c; ≈ 6000 |
| KP13 | Cytokinesis duration (s) | karr-known-incomplete | end_tick - start_tick of cytokinesis state | Karr Fig 3c; ≈ 2000 |
| KP14 | dNTP vs replication coupling | opencell-tooling | corr(dntp_total, fork_progress) over replication window | qualitative > 0.5 |
| KP15 | DNA-binding occupancy dynamics | biology-beyond-Karr | qualitative: occupancy curves emit non-empty? | bool |
| KP16 | DNA content doubling | opencell-tooling | dna_mass[division] / dna_mass[t=0] | exactly 2.0 ± 0.1 |
| KP17 | DNA mass fraction | validation-and-organism-scaling | dna_mass / total_mass at mid-cycle | Karr Sup Tbl S4; ≈ 0.03 |
| KP18 | RNA mass fraction | validation-and-organism-scaling | rna_mass / total_mass at mid-cycle | Karr Sup Tbl S4; ≈ 0.18 |
| KP19 | Protein mass fraction | validation-and-organism-scaling | protein_mass / total_mass at mid-cycle | Karr Sup Tbl S4; ≈ 0.55 |
| KP20 | Metabolite concentration profile | karr-known-incomplete | mean abs log-ratio across 30 key metabolites vs Karr Sup Tbl S5 | tol = 1.0 in log-space |
| KP21 | ATP/GTP production-use balance | opencell-tooling | (production - use) / production over cycle | tol = 0.05 |
| KP22 | Energy discrepancy phenotype | karr-known-incomplete | aggregate energy_ledger flux balance | qualitative |
| KP23 | Burst-like protein synthesis stats | biology-beyond-Karr | fano factor of protein synthesis events | bool: extractor returns True if computable |
| KP24 | mRNA/protein distribution shape | biology-beyond-Karr | KS-statistic vs Karr-published distribution | qualitative |
| KP25 | Gene essentiality accuracy | biology-beyond-Karr | **BLOCKED in v1** — needs multi-run KO sweep | extractor returns None |
| KP26 | Single-gene disruption phenotype class | biology-beyond-Karr | **BLOCKED in v1** — same | None |
| KP27 | Host adhesion competence | biology-beyond-Karr | `traj["host"]["is_bacterium_adherent"][-1]` | bool |
| KP28 | Host immune activation cascade | biology-beyond-Karr | `all([is_tlr_activated, is_nfkb_activated, is_inflammatory_response_activated])` | bool |

## 6. Karr value sourcing strategy

`karr_reference_values.py` is a module-level dict with one constant per KP. Each
entry has `(value, citation, sourced_by, sourced_at)`. Codex turn populates it
by:
1. Searching `data/karr_paper/karr_2012_supplementary_tables/` if present (matlab `.mat` or `.csv`)
2. Else: leave `value=None` and `citation="TODO: from paper table SX"`, mark KP as BLOCKED with a logged v1.1 todo
3. NO scraping from the paper PDF (we don't have it locally and won't fetch external URLs)

**Targeting**: at least 12 KPs should have real `karr_value` sourced from `m1_oracle` fixtures or existing `data/` files. The remaining 16 can be BLOCKED in v1 and still meet the ≥10/28 PASS gate.

## 7. Fixture: cached chassis_v6 32400-tick trajectory

Running 32400 ticks takes ~10-18 min. Tests can't tolerate that on every call.
Strategy:
- Provide helper `load_v6_trajectory_fixture()` in E.2 implementation.
- Loader path is fixed to `data/phase_e/v6_trajectory_32400s.pkl`.
- Loader validates E.1 schema contract before returning:
  - `chassis == "v6"`
  - `schema_version == 1`
  - top-level keys include `snapshots`, `wall_time_s`, `ticks_completed`, `division_detected`
  - each snapshot has `{tick, time_s, state}` with 9 scaffold observables under `state`
- If the fixture is missing, E.2 may trigger `scripts/phase_e1_real_match.py` once and then cache.

## 8. Scorecard output format

`docs/phase_e/E2_scorecard.md`:

```markdown
# Phase E.2 — 28-Phenotype Scorecard

**Run**: chassis_v6 @ commit <sha>  
**Wall-time**: <s>s  
**Pass count**: NN/28 (target ≥10)  
**Bucket summary**: opencell-tooling N/8 · validation N/9 · karr-incomplete N/5 · beyond-Karr N/6  
**Blocked**: M (KP25, KP26, ...) — see notes column

## Per-KP detail

| KP | Label | Bucket | Opencell | Karr | rel_err | Status | Disposition |
|---|---|---|---|---|---|---|---|
| KP01 | Growth rate | opencell-tooling | 0.0598 | 0.0600 | 0.33% | ❌ FAIL | strict tol exceeded |
| ... |
```

A one-line header is also emitted to stdout for blog/release-notes consumption:
`E2_PASS=12/28 OC=5/8 VAL=4/9 INC=2/5 BEY=1/6 BLOCKED=4`

## 9. Test plan

```python
# tests/validation/test_e2_phenotype_scorecard.py

def test_e2_all_kps_registered():
    """All 28 IDs KP01..KP28 present in PHENOTYPES."""
    assert sorted(PHENOTYPES.keys()) == [f"KP{i:02d}" for i in range(1, 29)]
    for kp in PHENOTYPES.values():
        assert kp.bucket in get_args(Bucket)
        assert kp.extractor is not None

def test_e2_extractors_run(chassis_v6_trajectory):
    """Each extractor returns a float or None — no exceptions."""
    for kp_id, kp in PHENOTYPES.items():
        result = kp.extractor(chassis_v6_trajectory)
        assert result is None or isinstance(result, (int, float, bool, np.floating))

def test_e2_scorecard_pass_count(chassis_v6_trajectory):
    """At least 10 of 28 PASS within bucket tolerance."""
    scorecard = score(chassis_v6_trajectory)
    pass_count = sum(1 for row in scorecard if row.status == "PASS")
    assert pass_count >= 10, f"Only {pass_count}/28 PASS"

def test_e2_no_unhandled_blocked(chassis_v6_trajectory):
    """Every BLOCKED has a documented v1.1 todo."""
    scorecard = score(chassis_v6_trajectory)
    blocked = [row for row in scorecard if row.status == "BLOCKED"]
    for row in blocked:
        assert row.disposition_todo_id is not None, \
            f"{row.kp_id} blocked without todo"

def test_e2_report_emitted():
    """docs/phase_e/E2_scorecard.md exists with all 28 rows."""
    path = Path("docs/phase_e/E2_scorecard.md")
    assert path.exists()
    content = path.read_text()
    for i in range(1, 29):
        assert f"KP{i:02d}" in content
```

Mark slow tests with `pytest.mark.slow`; default suite excludes them unless `--run-slow`.

## 10. Acceptance criteria (gating E-final)

- ≥10 of 28 KPs PASS within bucket tolerance
- Every KP has explicit status (PASS / FAIL / BLOCKED)
- Every BLOCKED has a v1.1 todo logged
- `E2_scorecard.md` committed to repo

## 11. Out of scope (deferred to v1.1+)

- Multi-run KO sweeps (KP25, KP26) — defer
- Real distribution-shape comparison via downloaded Karr SI distributions (KP24) — deferred
- Live PDF/paper scraping for unsourced Karr values — deferred
- Performance optimization of the 32400-tick fixture build — deferred

## 12. Codex turn brief

Branch: `agent/pe-2-phenotype-scorecard`  
Token budget: 100k (extractor implementations + Karr value sourcing + 5 tests + scorecard renderer)  
Commit checkpoints:
1. `phenotype_registry.py` skeleton + PhenotypeDef + bucket tols → commit
2. `karr_reference_values.py` populated for ≥12 KPs → commit
3. All 28 extractors implemented → commit
4. Scorecard renderer + report writer → commit
5. Tests passing + fixture caching working → commit
6. `E2_scorecard.md` generated and committed → final commit
