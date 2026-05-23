# Phase E-final — v1.0 Release Gate Design

**Status**: design ready  
**Prereq**: E.1 + E.2 + E.3 all committed with PASS verdicts  
**Branch**: `agent/pe-final-v1-release`  
**Wall-time**: 30-60 min Codex (CHANGELOG assembly + release notes + tag + GitHub Release + optional README polish)

## 1. Goal

Verify all v1.0 hard gates pass. Assemble user-facing release artifacts (CHANGELOG,
RELEASE_NOTES, README quickstart). Push the `v1.0.0` git tag. Create a GitHub Release
page. Soft gates (blog, PyPI, methods paper) are explicitly deferred — not blocking.

## 2. Hard gates checklist (every one must PASS)

### G1. Code completeness
- 28 of 28 Karr processes present:
  ```
  python -c "from opencell.vivarium.karr_composite import CHASSIS_V6_EXPECTED_PROCESS_KEYS; assert len(CHASSIS_V6_EXPECTED_PROCESS_KEYS) == 28"
  ```
- No `NotImplementedError` in production paths:
  ```
  grep -rn 'raise NotImplementedError' opencell/ --include='*.py' | grep -v test_ | grep -v _stub
  ```
  Expected: zero non-stub matches. Stub modules (`karr_macromolecular_complexation_stub.py` etc.) are allowed to raise; production composite must not import them.

### G2. Test suite green
- ≥900 tests collected
- 0 failures
- 0 unexplained xfails: every `pytest.mark.xfail` must reference a v1.1 todo in `opencell_tasks.db` via a `reason=` matching pattern `"v1.1-todo: <id>"`
- Run: `pytest -q --tb=no | tee /tmp/e_final_suite.txt`
- Check: `grep -E "(failed|FAILED)" /tmp/e_final_suite.txt` returns nothing

### G3. Full-cycle test
- `tests/integration/test_full_cell_cycle_completes.py::test_32400_ticks_pass_or_xfail`
- MUST be PASS OR explicit `pytest.mark.xfail(reason="perf-budget v2; v1.1-todo: perf-32400")`
- Record measured wall-time in `docs/phase_e/E_final_wall_time.txt`

### G4. E.1 gate
- Read `docs/phase_e/E1_match_report.md` summary line
- Assert: 100% opencell-tooling bucket PASS, ≥50% validation-and-organism-scaling PASS

### G5. E.2 gate
- Read `docs/phase_e/E2_scorecard.md` summary line
- Assert: ≥10/28 phenotypes PASS

### G6. E.3 gate
- Read `docs/phase_e/E3_discrepancy_log.md` summary line
- Assert: 0 BLOCK-RELEASE entries

### G7. CI green on main
- `gh run list --branch main --limit 3 --json conclusion -q '.[0].conclusion'` returns `success`
- If not, FAIL the gate; do not tag.

## 3. Release artifact assembly

### A1. CHANGELOG.md (new or appended)

Generated from commit log since last tag (or repo init if no prior tag):
```bash
git log --pretty='%h %s' $(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD)..HEAD \
  | grep -v -E '^[a-f0-9]+ (chore:|docs: typo|test: tweak|wip)' \
  | sort -u > /tmp/changelog_raw.txt
```

Then group into sections by reading commit prefix:
- `feat:` → "Added"
- `fix:` → "Fixed"
- `refactor:` → "Changed"
- `Merge agent/p[abcde]-*` → "Phase N: <branch label>"
- everything else → "Other"

Codex writes the human-readable `CHANGELOG.md` at repo root.

### A2. RELEASE_NOTES_v1.0.md

A new file at repo root. Sections:

- **What is opencell** — 2-paragraph project description (cribbed from README)
- **What's in v1.0** — bullet list:
  - 28 Karr 2012 processes ported to vivarium-core
  - Full cell-cycle simulation (32400 ticks, 9h biological time)
  - Phenotype validation: N/28 KPs PASS (from E.2 summary line)
  - Trajectory match: opencell-tooling 100% / validation N% (from E.1)
- **Known limitations (deferred to v1.1)** — pulled from `opencell_tasks.db WHERE milestone='v1.1'`
- **How to install** — `pip install -e .` instructions
- **How to run a simulation** — 10-line quickstart with build_karr_chassis_v6
- **Acknowledgments** — Karr et al 2012, vivarium-core team, contributors

### A3. README.md update

Append (don't overwrite) a "v1.0 quickstart" section near the top. Include:
- One-paragraph claim summary
- 5-line install + run code snippet
- Link to RELEASE_NOTES_v1.0.md for details

If README already has a quickstart, replace it; otherwise insert after the project description.

### A4. Git tag and GitHub Release

```bash
git tag -a v1.0.0 -m "opencell v1.0.0 — Mycoplasma genitalium whole-cell model on vivarium-core"
git push origin v1.0.0
gh release create v1.0.0 \
  --title "opencell v1.0.0" \
  --notes-file RELEASE_NOTES_v1.0.md \
  --latest
```

If `gh release create` fails (auth, repo not configured for releases), STOP and
write to STATUS.md with explicit error. Do NOT proceed without a successful
release.

## 4. Soft gates (recommended; non-blocking)

These DO NOT prevent v1.0 ship. Codex may complete them if time permits; else
they become post-release todos.

| Soft gate | Action | If skipped |
|---|---|---|
| Blog/narrative post | Draft `docs/blog/v1_0_announcement.md` | leave as v1.1 todo |
| PyPI publish | Build wheel, `twine upload` | leave as v1.1 todo (separate effort) |
| L4 methods paper | Outline only at `docs/papers/l4_methods_outline.md` | leave as `l4-methods-paper` todo |
| `llm-interaction-log` extraction | Extract to standalone PyPI package | leave as v1.1 todo |

Codex should attempt the blog draft (it's already half-written across checkpoints) but explicitly skip PyPI and methods paper unless operator requests in the turn prompt.

## 5. Order of operations

```
1. Verify G1-G7 (no actions; pure read; STOP on any FAIL)
2. Assemble CHANGELOG.md
3. Draft RELEASE_NOTES_v1.0.md
4. Polish README.md (quickstart section)
5. Commit all three: "Prepare v1.0.0 release"
6. Tag v1.0.0 + push tag
7. gh release create
8. Optional: blog draft (timeboxed at 20 min)
9. Write docs/phase_e/E_final_summary.md with all gate results + release URL
10. Final commit: "v1.0.0 released"
```

If step 6-7 fail (network, gh auth, etc.), revert step 5 commit and write
detailed STATUS for human follow-up.

## 6. Test plan

```python
# tests/release/test_e_final_gates.py — invoked by Codex during gate verification

def test_g1_28_processes():
    from opencell.vivarium.karr_composite import CHASSIS_V6_EXPECTED_PROCESS_KEYS
    assert len(CHASSIS_V6_EXPECTED_PROCESS_KEYS) == 28

def test_g1_no_not_implemented_in_production():
    import subprocess
    out = subprocess.check_output(
        ["grep", "-rn", "raise NotImplementedError",
         "opencell/", "--include=*.py"]
    ).decode().splitlines()
    out = [l for l in out if "_stub" not in l and "test_" not in l]
    assert len(out) == 0, f"Production NotImplementedError(s): {out}"

def test_g2_full_suite_green():
    """Self-referential; runs via tox or subprocess in CI only."""
    # ... pytest --tb=no, parse exit code

def test_g4_g5_g6_artifacts_committed():
    for p in ["docs/phase_e/E1_match_report.md",
              "docs/phase_e/E2_scorecard.md",
              "docs/phase_e/E3_discrepancy_log.md"]:
        assert Path(p).exists(), f"Missing required artifact: {p}"

def test_g6_no_block_release():
    log = Path("docs/phase_e/E3_discrepancy_log.md").read_text()
    assert "BLOCK-RELEASE" not in log or "BLOCK=0" in log
```

`tests/release/` is opt-in (gated by `pytest -m release`); not in default suite.

## 7. Failure handling

If ANY hard gate fails:
1. Codex writes `docs/phase_e/E_final_HOLD.md` with the failing gate detail
2. NO tag is pushed, NO release is created
3. Each failure becomes a new follow-up Codex turn (one per gate failed)
4. Operator decides whether to fix-and-retry or escalate

## 8. Out of scope (NOT for this turn)

- Performance optimization
- PyPI publish (separate effort; v1.1+)
- llm-interaction-log extraction (separate effort)
- Methods paper drafting (only outline if doing soft gate at all)

## 9. Codex turn brief

Branch: `agent/pe-final-v1-release`  
Token budget: 60k (assembly + release ops; tests already pass-or-fail by this point)  
Commit checkpoints:
1. Gate verification report (G1-G7) → commit `docs/phase_e/E_final_gate_check.md`
2. CHANGELOG + RELEASE_NOTES + README polish → commit `Prepare v1.0.0 release`
3. (after `gh release create` succeeds) → final commit `v1.0.0 released — see GitHub Release page`

If any gate fails, only commit (1) and write `E_final_HOLD.md`; do NOT push tag.
