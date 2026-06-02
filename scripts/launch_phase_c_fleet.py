#!/usr/bin/env python3
"""Launch N parallel Codex sessions for Phase C/D/E turns.

Each session: design + implement + test + commit, standalone in its own worktree.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(r"E:\opencell")
WT_ROOT = Path(r"E:\opencell-worktrees")

PREAMBLE = r"""[MANDATORY PREAMBLE — READ FULLY BEFORE ANY ACTION]

You are a Codex implementation agent in a dedicated git worktree at the CWD.
The orchestrator (Copilot CLI, separate session) created this worktree on
branch agent/<task>. Your job is autonomous: DESIGN -> IMPLEMENT -> TEST ->
COMMIT -> write STATUS.md -> exit.

== 0. FIRST ACTION (do this BEFORE reading anything) ==
Overwrite STATUS.md with a fresh header:
    ## <task-slug> — started <UTC timestamp>
    (no inherited content from any prior session)

== 1. READ FIRST (in this order) ==
- SESSION_CONTEXT.md (6 hard rules — Karr fidelity, WSL venv, accumulate-only,
  KarrAllocationStep, commit-or-STATUS, no regressions)
- .github/copilot-instructions.md (Primary-Source Discipline)
- opencell/vivarium/karr_replication_initiation.py (Phase C T1 pattern — your closest reference)
- opencell/vivarium/karr_allocation_step.py (substrate request/allocate protocol)
- opencell/vivarium/karr_protein_decay_light.py (minimal scope process example)
- opencell/vivarium/karr_composite.py — search for build_karr_chassis_v4 (wiring pattern)
- docs/design/phase_c_overview.md (Phase C scope, new stores, CellCycleCoordinator)
- docs/design/pc_turn1_replication_initiation.md (your design-doc template)
- The Karr extract(s) listed in your TASK-SPECIFIC SCOPE below.

== 2. TOOL FALLBACKS ==
WSL may lack rg, fd, jq, gh. Fall back to: grep -rn, find, python -m json.tool,
curl + git. A missing tool is NEVER a reason to abort — switch tools.

== 3. PYTHON IS WSL-VENV ONLY ==
ALL Python and pytest invocations MUST go through the project's WSL venv:
    wsl -e bash -lc "/mnt/e/opencell/.venv-wsl/bin/python ..."
    wsl -e bash -lc "cd /mnt/e/opencell && /mnt/e/opencell/.venv-wsl/bin/pytest ..."
Do NOT use Windows `py -3.12` or `python.exe` — it will silently fail with
phantom ModuleNotFoundError on the project's own package. This rule cost the
team 30 min yesterday; do not repeat.

== 4. PROGRESS DISCIPLINE ==
- After your first action, append a one-line heartbeat to .progress.md every
  ~5 files touched or ~10 min wall-clock.
- If you get stuck: write to STATUS.md WHAT specifically blocked you, with the
  exact error message and the command that produced it. Then exit non-zero.
- NEVER exit silently. A partial STATUS is always better than no STATUS.

== 5. WORKFLOW (design-first) ==
1. Write docs/design/<task-slug>.md BEFORE writing any code.
   Use docs/design/pc_turn1_replication_initiation.md as the template.
   Include: Karr primary source ref, scope (light/full + deferred list),
   state ports (new stores added), substrate consumption, test plan,
   open questions.
2. Implement opencell/vivarium/karr_<process>.py following the design.
   Read karr_replication_initiation.py for the file shape. ~300-600 LOC
   is normal. Use KarrAllocationStep if you consume shared substrates.
   Every per-tick writer uses `_updater: "accumulate"`.
3. Write tests in tests/vivarium/test_karr_<process>.py — at minimum:
   (a) process instantiates with chassis_v4 defaults
   (b) one-tick run produces expected state delta sign
   (c) substrate-allocation contract honored (if applicable)
   (d) 100-tick steady-state behavior matches Karr trace within tolerance
   (e) no NaN / negative-count regressions
4. Run targeted tests, then full suite:
       wsl -e bash -lc "cd /mnt/e/opencell && .venv-wsl/bin/pytest tests/vivarium/test_karr_<process>.py -v"
       wsl -e bash -lc "cd /mnt/e/opencell && .venv-wsl/bin/pytest -x -q"
   The full suite MUST end with 0 failures and no new xfails. If something
   pre-existing fails on main, document it in STATUS.md but do NOT alter
   unrelated code to "fix" it.
5. ONE commit per turn (squash if needed), message:
       <task-slug>: <one-line scope summary>
   Do NOT push. The orchestrator will merge to main after review.

== 6. FINAL STATUS.md ==
At end, append a final block:
    ## RESULT
    - status: SUCCESS | PARTIAL | BLOCKED
    - design: docs/design/<task-slug>.md (LOC, sections)
    - implementation: opencell/vivarium/karr_<process>.py (LOC)
    - tests: <n> new, <n> total in module, full-suite <PASS/FAIL>
    - commit: <sha> <message>
    - blockers: <list or "none">
    - deferred to v2: <list>

== 7. KARR-LIGHT IS OK ==
For long/complex Phase C processes (Replication, DNADamage, Cytokinesis), it
is OK to ship a Karr-LIGHT v1 that:
- matches per-tick RATES from the trace (data/m1_sources/karr_native/per_process_traces/<Process>_100ticks.mat)
- uses bulk counters instead of per-nucleotide / per-base detail
- documents deferred mechanism explicitly as "v2 scope" in module docstring.
The chassis still has to close mass balance — light scope ≠ fictional biology.

== TASK-SPECIFIC SCOPE ==
"""

TASKS = {
    "pc-t2-replication": {
        "title": "Replication (Karr-LIGHT v1)",
        "primary": "docs/karr_extracts/process/03_Replication.md",
        "trace": "data/m1_sources/karr_native/per_process_traces/Replication_100ticks.mat",
        "scope": """
Implement opencell/vivarium/karr_replication.py — fork advancement after pc-t1
initiation has flipped chromosome.replication_state to "initiating".

Karr-LIGHT v1 scope:
- Read chromosome.replication_state from pc-t1. When state == "initiating"
  (one tick after initiation fires), transition state to "elongating" and
  begin fork tracking.
- Track per-fork progress as a bulk counter (chromosome.fork_position_bp,
  starting at oriC, advancing toward terC). 2 forks (bidirectional).
- Per-tick advancement rate: derive from Replication_100ticks.mat polymerization
  rate (~100 bp/s per fork is typical; verify from trace before coding).
- Bulk substrate demand per tick: dNTPs (dATP, dCTP, dGTP, dTTP) proportional
  to bp advanced; ATP for helicase. Use KarrAllocationStep — request 4*advance_bp
  dNTPs split per base composition (Karr's chromosome bp counts from KB).
- When BOTH forks reach terC: set chromosome.replication_state = "complete".
  Emit completion event for downstream (cytokinesis trigger).
- DEFER to v2 (document in docstring): SSB binding cycle, Okazaki fragment
  per-strand mechanics, ligase per-fragment events, leading/lagging strand
  asymmetry. These do NOT affect mass balance if the bulk dNTP/ATP demand
  matches Karr's trace.

Tests (tests/vivarium/test_karr_replication.py):
1. Process instantiates
2. With chromosome.replication_state = "idle" -> no fork advance, no substrate request
3. With state = "initiating" -> transitions to "elongating", forks begin at 0
4. After N ticks of elongation, fork_position_bp advanced by ~N*rate, dNTPs decreased
5. When forks reach terC -> state = "complete" emitted exactly once
6. Substrate allocation: if requested > available, advance proportionally (Karr fair-share)
7. 1000-tick partial elongation run — fork positions monotonic, no NaN, mass closes
""",
    },
    "pc-t3-supercoiling": {
        "title": "DNASupercoiling",
        "primary": "docs/karr_extracts/process/04_DNASupercoiling.md",
        "trace": "data/m1_sources/karr_native/per_process_traces/DNASupercoiling_100ticks.mat",
        "scope": """
Implement opencell/vivarium/karr_dna_supercoiling.py — supercoiling state
machine driven by topoII (gyrase) introducing negative supercoils and topoIV
relaxing them.

Scope:
- New state: chromosome.supercoil_density (float, target ~-0.06 = Karr's value)
- Per-tick: stochastic gyrase action (ATP-dependent, introduces -1 link per
  event) and topoIV relaxation (introduces +1 link per event). Rates from
  trace.
- Couple to chromosome.replication_state: replication consumes negative
  supercoils ahead of fork (so during elongating, demand for gyrase rises).
- ATP consumption via KarrAllocationStep.

5+ tests including 100-tick steady-state supercoil density within 10% of Karr trace.
""",
    },
    "pc-t4-condensation": {
        "title": "ChromosomeCondensation",
        "primary": "docs/karr_extracts/process/05_ChromosomeCondensation.md",
        "trace": "data/m1_sources/karr_native/per_process_traces/ChromosomeCondensation_100ticks.mat",
        "scope": """
Implement opencell/vivarium/karr_chromosome_condensation.py — SMC complex
binding to chromosome, ATP-driven loop extrusion / condensation.

Scope:
- New state: chromosome.smc_bound_count (int), chromosome.condensation_level (float 0..1)
- SMC binds at rate from trace; condensation_level relaxes toward target driven
  by smc_bound_count + ATP availability.
- Karr-light: track aggregate condensation, not per-loop topology.
- Couple loosely to replication (condensation can pause during fork passage).

5+ tests; 100-tick condensation_level matches Karr trace within 10%.
""",
    },
    "pc-t5-segregation": {
        "title": "ChromosomeSegregation",
        "primary": "docs/karr_extracts/process/06_ChromosomeSegregation.md",
        "trace": "data/m1_sources/karr_native/per_process_traces/ChromosomeSegregation_100ticks.mat",
        "scope": """
Implement opencell/vivarium/karr_chromosome_segregation.py — once replication
is complete, daughter chromosomes separate to opposite cell poles.

Depends on (READ-ONLY): chromosome.replication_state == "complete" (from pc-t2).
If pc-t2 not merged yet on main, scaffold a mock: assume the state can also be
set externally by a CellCycleCoordinator. Your tests can drive the state
directly.

Scope:
- New state: chromosome.segregation_progress (float 0..1), chromosome.daughter_pole_positions
- Per-tick advance from trace rate; ATP-dependent.
- When progress == 1.0: emit "segregation_complete" — gates cytokinesis (pc-t9).

5+ tests; rate matches trace within 10%.
""",
    },
    "pc-t6-damage": {
        "title": "DNADamage",
        "primary": "docs/karr_extracts/process/07_DNADamage.md",
        "trace": "data/m1_sources/karr_native/per_process_traces/DNADamage_100ticks.mat",
        "scope": """
Implement opencell/vivarium/karr_dna_damage.py — stochastic damage site
creation (UV-like, oxidative, alkylation, depurination).

Scope:
- New state: chromosome.damage_sites (list of {position, kind, age_ticks})
- Per-tick: poisson-distributed new damage events at rates from trace per kind.
- No repair here (that's pc-t7). damage_sites accumulate.
- Couple: damage at fork = replication stall flag (advisory, replication can read).

5+ tests; 100-tick total damage count within 20% of trace.
""",
    },
    "pc-t7-repair": {
        "title": "DNARepair",
        "primary": "docs/karr_extracts/process/08_DNARepair.md",
        "trace": "data/m1_sources/karr_native/per_process_traces/DNARepair_100ticks.mat",
        "scope": """
Implement opencell/vivarium/karr_dna_repair.py — repair damage_sites emitted
by pc-t6.

Depends on chromosome.damage_sites (from pc-t6). If pc-t6 not merged yet,
scaffold a mock store; tests pre-populate damage sites directly.

Scope:
- Per-tick: each kind of damage has its repair pathway (NER, BER, HR, NHEJ-like).
- ATP/dNTP consumption via KarrAllocationStep proportional to repairs.
- Remove from damage_sites when repaired; track repair_count delta.
- Karr-light: aggregate per-pathway rates from trace, not per-site mechanics.

5+ tests.
""",
    },
    "pc-t8-ftsz": {
        "title": "FtsZPolymerization",
        "primary": "docs/karr_extracts/process/09_FtsZPolymerization.md",
        "trace": "data/m1_sources/karr_native/per_process_traces/FtsZPolymerization_100ticks.mat",
        "scope": """
Implement opencell/vivarium/karr_ftsz_polymerization.py — FtsZ-GTP monomers
polymerize into Z-ring at midcell.

Scope:
- New state: cell.ftsz_ring_count (int, target ~Karr steady-state from trace),
  cell.ftsz_ring_complete (bool, flips when count >= threshold).
- GTP consumption via KarrAllocationStep.
- Couple: ring assembly is required for cytokinesis (pc-t9 reads ftsz_ring_complete).

5+ tests; ring count matches trace SS within 10%.
""",
    },
    "pc-t9-cytokinesis": {
        "title": "Cytokinesis",
        "primary": "docs/karr_extracts/process/10_Cytokinesis.md",
        "trace": "data/m1_sources/karr_native/per_process_traces/Cytokinesis_100ticks.mat",
        "scope": """
Implement opencell/vivarium/karr_cytokinesis.py — Z-ring constriction +
membrane invagination → cell division event.

Depends on cell.ftsz_ring_complete (pc-t8) AND chromosome.segregation_progress == 1.0 (pc-t5).
If either dep not merged, mock the gating state in tests.

Scope:
- New state: cell.division_progress (float 0..1), cell.division_complete (bool)
- Per-tick advance only if both gates true; rate from trace; GTP consumption.
- When progress = 1.0: emit "division_complete" — Phase D / Phase E will consume.
- Karr-light: bulk ring constriction, not per-monomer GTPase cycling.

5+ tests including: dependency gating, completion event, 100-tick rate match.
""",
    },
    "pc-t10-terminal-organelle": {
        "title": "TerminalOrganelleAssembly",
        "primary": "docs/karr_extracts/process/11_TerminalOrganelleAssembly.md",
        "trace": "data/m1_sources/karr_native/per_process_traces/TerminalOrganelleAssembly_100ticks.mat",
        "scope": """
Implement opencell/vivarium/karr_terminal_organelle_assembly.py — M. genitalium
specific polar adhesion organelle (P1, P30, HMW1/2/3 + cytoskeletal components).

Scope:
- New state: cell.terminal_organelle_count (int, target 1 or 2 in division),
  cell.terminal_organelle_components_assembled (dict per protein).
- Component-by-component assembly per Karr's defined order. Each step is
  protein-availability-gated (reads from protein.activity from pb-t11).
- Karr-light: bulk per-component counters from trace, not per-residue docking.

5+ tests; 100-tick assembly progression matches trace.
""",
    },
    "pd-t1-host-interaction": {
        "title": "HostInteraction",
        "primary": "docs/karr_extracts/process/28_HostInteraction.md",
        "trace": "data/m1_sources/karr_native/per_process_traces/HostInteraction_100ticks.mat",
        "scope": """
Implement opencell/vivarium/karr_host_interaction.py — adhesion of M. genitalium
to host epithelial surface, mediated by terminal organelle proteins.

Independent of Phase C state — can run as a standalone Phase D process. Reads
cell.terminal_organelle_count (if pc-t10 merged; otherwise mock).

Scope:
- New state: cell.host_adhesion_strength (float), cell.host_attached (bool)
- Per-tick: stochastic binding/unbinding events from trace rates.
- ATP consumption via KarrAllocationStep (small).
- Karr-light: aggregate adhesion strength, not per-receptor docking events.

5+ tests.
""",
    },
    "pe-1-trajectory-scaffold": {
        "title": "Phase E.1 — Karr trajectory comparison scaffold",
        "primary": "data/m1_sources/karr_native/cell_cycle_trajectory.mat",
        "trace": "(this IS the trajectory — the gold standard)",
        "scope": """
NOT a vivarium process — this is the Phase E.1 validation scaffold.

Goal: load Karr's full cell_cycle_trajectory.mat (100 MB, gitignored, at
data/m1_sources/karr_native/cell_cycle_trajectory.mat) and build the
comparison framework that will eventually run chassis_v6 (28 processes)
against Karr's reference trajectory.

Deliverables:
1. opencell/validation/karr_trajectory.py — loader for cell_cycle_trajectory.mat.
   Inspect the file structure first (scipy.io.loadmat). Extract per-time-point
   snapshots of: cell mass, replication state, fork position, mRNA totals,
   protein totals, ATP/GTP pools, dNTP pools, division event timestamp.
2. opencell/validation/trajectory_compare.py — diff function:
   compare_trajectories(opencell_trajectory, karr_trajectory) ->
       per-observable L_inf abs+rel error + phenotype-scalar diff (Karr's 28).
   Reuse opencell/diff/multi_level.py where it fits.
3. scripts/phase_e1_dry_run.py — drives a 1000-tick chassis_v4 run, extracts
   the SAME observables, runs trajectory_compare against Karr's first 1000
   ticks, prints a markdown table of {observable, opencell_value, karr_value,
   rel_err, status}. Status PASS if rel_err < threshold from
   data/semantics/A6_semantics_contract.md.
4. tests/validation/test_trajectory_scaffold.py — minimal: loader works,
   shape sanity checks, compare returns a dict with expected keys.

DO NOT yet run chassis_v6 (it doesn't exist). DO produce a markdown report
docs/phase_e/E1_scaffold.md showing the 1000-tick chassis_v4-vs-Karr-first-1000
preview comparison. This IS expected to be very far off (chassis_v4 has 17/28
processes); the point is to land the comparison framework.
""",
    },
}


def compose_prompt(task: str, spec: dict) -> str:
    return (
        PREAMBLE
        + f"\nTask: {task}\nTitle: {spec['title']}\n"
        + f"Primary source: {spec['primary']}\nKarr trace: {spec['trace']}\n"
        + spec["scope"]
        + f"\n\nBegin now. First action: overwrite STATUS.md with the started-header.\n"
    )


def launch(task: str, prompt: str) -> int:
    wt = WT_ROOT / task
    prompt_path = wt / "PROMPT.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    # Clear any inherited STATUS.md
    status = wt / "STATUS.md"
    if status.exists():
        status.unlink()
    log_out = wt / ".codex_stdout.log"
    log_err = wt / ".codex_stderr.log"
    fout = open(log_out, "w", encoding="utf-8")
    ferr = open(log_err, "w", encoding="utf-8")
    # Fully detached
    codex_cmd = r"C:\Users\sdrona\AppData\Roaming\npm\codex.cmd"
    proc = subprocess.Popen(
        [
            codex_cmd, "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "-C", str(wt),
            "-o", str(status),
            prompt,
        ],
        stdout=fout, stderr=ferr,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            if sys.platform == "win32" else 0,
        close_fds=True,
    )
    (wt / ".codex_pid").write_text(str(proc.pid), encoding="ascii")
    return proc.pid


if __name__ == "__main__":
    only = set(sys.argv[1:])
    launched = []
    for task, spec in TASKS.items():
        if only and task not in only:
            continue
        prompt = compose_prompt(task, spec)
        pid = launch(task, prompt)
        launched.append((task, pid))
        print(f"LAUNCHED {task} (pid={pid})  prompt_len={len(prompt)}")
    print(f"\nTotal: {len(launched)} sessions running.")
