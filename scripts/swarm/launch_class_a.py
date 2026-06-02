#!/usr/bin/env python3
"""Class A swarm launcher.

Instantiates per-process PROMPT files from CLASS_A_TEMPLATE.md, creates worktrees
off main HEAD, and optionally fires Codex agents in parallel.

Phased usage:
    # Pilot phase (2 processes)
    python scripts/swarm/launch_class_a.py --only Translation,RnaDecay --fire

    # Scale phase (next 8)
    python scripts/swarm/launch_class_a.py --batch 2 --size 8 --fire

    # Remaining 18
    python scripts/swarm/launch_class_a.py --batch 3 --size 18 --fire

    # Dry-run: prep worktrees + prompts, no codex launch
    python scripts/swarm/launch_class_a.py --only Translation,RnaDecay

The launcher is idempotent on worktree creation (skip if exists) and PROMPT
file write (overwrite). Codex launch is the side-effecting step gated by --fire.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(r"E:\opencell")
WORKTREE_ROOT = Path(r"E:\opencell-worktrees")
TEMPLATE = REPO / "scripts" / "swarm" / "CLASS_A_TEMPLATE.md"
TARGETS = REPO / "scripts" / "swarm" / "class_a_targets.json"
MAIN_SHA = "852da97"

CODEX = r"C:\Users\sdrona\AppData\Roaming\npm\codex.cmd"
CODEX_FLAGS = "--dangerously-bypass-approvals-and-sandbox --skip-git-repo-check"


def get_azure_key() -> str:
    """Read AZURE_OPENAI_API_KEY from process env, falling back to User scope."""
    import os
    key = os.environ.get("AZURE_OPENAI_API_KEY")
    if key:
        return key
    out = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command",
         "[System.Environment]::GetEnvironmentVariable('AZURE_OPENAI_API_KEY','User')"],
        capture_output=True, text=True, check=True,
    )
    key = out.stdout.strip()
    if not key:
        raise SystemExit("ERROR: AZURE_OPENAI_API_KEY not in process env or User-scope.")
    return key


def load_targets() -> list[dict]:
    return json.loads(TARGETS.read_text(encoding="utf-8"))["processes"]


def render_prompt(target: dict, template: str) -> str:
    return (
        template
        .replace("{{PROCESS_NAME}}", target["name"])
        .replace("{{PROCESS_PY_PATH}}", target["py"])
        .replace("{{KARR_EXTRACT}}", target["extract"])
        .replace("{{MATLAB_NAME}}", target["matlab_name"])
        .replace("{{FIXTURE_MAT}}", target["fixture_mat"])
    )


def worktree_path(name: str) -> Path:
    return WORKTREE_ROOT / f"swarm-class-a-{name}"


def branch_name(name: str) -> str:
    return f"swarm/class-a/{name}"


def ensure_worktree(target: dict, dry_run: bool) -> Path:
    wt = worktree_path(target["name"])
    br = branch_name(target["name"])
    if wt.exists():
        print(f"  [skip] worktree exists: {wt}")
        return wt
    cmd = ["git", "-C", str(REPO), "worktree", "add", "-b", br, str(wt), MAIN_SHA]
    print(f"  [run] {' '.join(cmd)}")
    if not dry_run:
        subprocess.run(cmd, check=True)
    return wt


def write_prompt(target: dict, wt: Path, template: str, dry_run: bool) -> Path:
    prompt = render_prompt(target, template)
    prompt_path = wt / f"PROMPT_class_a_{target['name']}.md"
    print(f"  [write] {prompt_path}")
    if not dry_run:
        prompt_path.write_text(prompt, encoding="utf-8")
    return prompt_path


def fire_codex(target: dict, wt: Path, prompt_path: Path, dry_run: bool, azure_key: str) -> int | None:
    """Launch codex detached. Returns PID or None on dry-run."""
    name = target["name"]
    stdout_log = wt / ".codex_stdout.log"
    stderr_log = wt / ".codex_stderr.log"
    pid_file = wt / ".codex_pid"

    inner = (
        f'set AZURE_OPENAI_API_KEY={azure_key}&& '
        f'cd /d "{wt}" && '
        f'type "{prompt_path}" | "{CODEX}" exec {CODEX_FLAGS} '
        f'> "{stdout_log}" 2> "{stderr_log}"'
    )
    ps_cmd = [
        "powershell.exe", "-NoProfile", "-Command",
        f'$p = Start-Process cmd.exe -ArgumentList "/c", \'{inner}\' '
        f'-WindowStyle Hidden -PassThru; $p.Id | Out-File -FilePath "{pid_file}" -Encoding ascii'
    ]
    print(f"  [fire] {name} -> {wt}")
    if dry_run:
        return None
    subprocess.run(ps_cmd, check=True)
    pid = int(pid_file.read_text().strip())
    print(f"  [pid]  {name} = {pid}")
    return pid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="Comma-separated process names (e.g. Translation,RnaDecay)")
    ap.add_argument("--batch", type=int, help="Batch number 1..N (1-indexed, with --size)")
    ap.add_argument("--size", type=int, help="Batch size")
    ap.add_argument("--fire", action="store_true", help="Actually launch codex (default: prep only)")
    ap.add_argument("--dry-run", action="store_true", help="Print plan, write nothing")
    args = ap.parse_args()

    targets = load_targets()
    template = TEMPLATE.read_text(encoding="utf-8")

    if args.only:
        wanted = [n.strip() for n in args.only.split(",")]
        selected = [t for t in targets if t["name"] in wanted]
        missing = set(wanted) - {t["name"] for t in selected}
        if missing:
            print(f"ERROR: unknown process names: {sorted(missing)}", file=sys.stderr)
            return 2
    elif args.batch is not None and args.size is not None:
        start = (args.batch - 1) * args.size
        selected = targets[start:start + args.size]
    else:
        print("ERROR: must specify --only or --batch + --size", file=sys.stderr)
        return 2

    print(f"\nSelected {len(selected)} processes:")
    for t in selected:
        print(f"  - {t['name']} ({t['py']})")

    if not args.fire:
        print("\nMode: PREP ONLY (worktrees + prompts; codex not launched).")
        print("Re-run with --fire to launch.\n")

    print("\n--- Worktrees + Prompts ---")
    prompts: list[tuple[dict, Path, Path]] = []
    for t in selected:
        print(f"\n[{t['name']}]")
        wt = ensure_worktree(t, args.dry_run)
        pp = write_prompt(t, wt, template, args.dry_run)
        prompts.append((t, wt, pp))

    if args.fire:
        azure_key = get_azure_key()
        print("\n--- Codex Launch ---")
        for t, wt, pp in prompts:
            print(f"\n[{t['name']}]")
            fire_codex(t, wt, pp, args.dry_run, azure_key)

        print("\nFleet launched. Track via:")
        for t, wt, _ in prompts:
            print(f"  Get-Content '{wt}\\.codex_stdout.log' -Tail 30")

    return 0


if __name__ == "__main__":
    sys.exit(main())
