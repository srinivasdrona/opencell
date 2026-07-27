#!/usr/bin/env bash
# install.sh - install the repo-managed `commit-msg` hook(s).
#
# Copies (or symlinks where supported) scripts/git_hooks/* into .git/hooks/.
# Idempotent. Refuses to overwrite a non-managed commit-msg hook unless
# called with --force.
#
# Both checks below run at the `commit-msg` phase, not `pre-commit`: each
# depends on the commit message body (the L2 catalog check on a
# `Catalog-Entry:` trailer, the LLM-log check on a `co-authored-by: copilot`
# trailer), and Git only writes the message to disk once `commit-msg` runs.
# Staged files remain fully inspectable via `git diff --cached` at that
# phase because the commit object hasn't been created yet, so neither check
# loses visibility into what's being committed.
#
# Git only supports *one* script per hook name, so this installer composes
# both checks into a single generated `commit-msg` shim that runs each in
# order and stops (fails closed) on the first non-zero exit. This keeps the
# two enforcement policies independently source-controlled and testable
# (scripts/git_hooks/commit-msg-l2-catalog-conformance.sh,
# scripts/hooks/check_llm_log_on_commit.py) while sharing the one hook slot
# Git gives us.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
# Hooks live in the *common* git dir, which is shared by all worktrees of a
# repo. `${REPO_ROOT}/.git` is wrong here when run from a linked worktree:
# there, `.git` is a file (a gitdir pointer), not the directory that holds
# `hooks/`. `git rev-parse --git-common-dir` resolves correctly in both the
# main checkout and any linked worktree.
HOOKS_DST="$(git rev-parse --git-common-dir)/hooks"

MANAGED_MARKER="OPENCELL-MANAGED-HOOK"
LEGACY_MARKER="L2-CATALOG-CONFORMANCE-HOOK-MANAGED"

FORCE=0
if [ "${1:-}" = "--force" ]; then
    FORCE=1
fi

# install_composed_hook HOOK_NAME RUNNER RELPATH [RUNNER RELPATH ...]
#
# Each (RUNNER, RELPATH) pair is one step of the composed shim, run in
# order via the given interpreter (explicit, rather than relying on the
# source script's own exec bit / shebang, which git does not reliably
# preserve across checkouts). RELPATH is resolved relative to REPO_ROOT at
# hook-run time, so it works unmodified from any worktree. RUNNER may be
# the special value `AUTO_PYTHON` to defer interpreter selection to the
# generated shim itself, resolved fresh on every hook invocation rather
# than baked in at install time: this repo's hooks directory is the *same*
# file on disk whether a commit is made from a Windows shell or from WSL
# (see docs/copilot-instructions.md's dual Windows/WSL workflow), and each
# side may only have a working interpreter under a different name (e.g. a
# Windows machine where `python3` is a non-functional Microsoft Store
# app-execution-alias stub but `python` works; a WSL image with only
# `python3`, no bare `python`). Baking one name in at install time would
# make the shared shim work on whichever side installed it and silently
# fail on the other.
install_composed_hook () {
    local hook_name="$1"
    shift
    local -a steps=("$@")
    local dst="${HOOKS_DST}/${hook_name}"
    local i

    if [ $(( ${#steps[@]} % 2 )) -ne 0 ]; then
        echo "install: ERROR install_composed_hook needs (runner, relpath) pairs" >&2
        return 1
    fi

    for (( i = 1; i < ${#steps[@]}; i += 2 )); do
        local relpath="${steps[$i]}"
        if [ ! -f "${REPO_ROOT}/${relpath}" ]; then
            echo "install: ERROR source not found: ${REPO_ROOT}/${relpath}" >&2
            return 1
        fi
    done

    if [ -f "$dst" ]; then
        if grep -qE "${MANAGED_MARKER}|${LEGACY_MARKER}" "$dst" 2>/dev/null; then
            :
        elif [ "$FORCE" -eq 0 ]; then
            echo "install: refusing to overwrite existing non-managed ${hook_name}; use --force to override" >&2
            return 1
        fi
    fi

    {
        echo "#!/usr/bin/env bash"
        echo "# ${MANAGED_MARKER}: ${hook_name}"
        echo "# Composed of, in order (first non-zero exit blocks the commit):"
        for (( i = 1; i < ${#steps[@]}; i += 2 )); do
            echo "#   - ${steps[$i]}"
        done
        echo "# To uninstall, delete this file. To update, re-run scripts/git_hooks/install.sh."
        echo "set -euo pipefail"
        echo 'REPO_ROOT="$(git rev-parse --show-toplevel)"'
        for (( i = 0; i < ${#steps[@]}; i += 2 )); do
            local runner="${steps[$i]}"
            local relpath="${steps[$((i + 1))]}"
            if [ "$runner" = "AUTO_PYTHON" ]; then
                # Resolve a working Python interpreter fresh on every run
                # (not baked in at install time -- see rationale above).
                # Verifying with a trivial `-c` invocation, not just
                # `command -v`, catches the Windows app-execution-alias
                # stub case, where the binary exists on PATH but always
                # exits non-zero without running anything.
                echo '_python_bin=""'
                echo 'for _candidate in python3 python; do'
                echo '    if command -v "$_candidate" >/dev/null 2>&1 && "$_candidate" -c "import sys" >/dev/null 2>&1; then'
                echo '        _python_bin="$_candidate"'
                echo "        break"
                echo "    fi"
                echo "done"
                echo 'if [ -z "$_python_bin" ]; then'
                echo '    echo "commit-msg: ERROR no working python interpreter found on PATH (tried: python3, python)" >&2'
                echo "    exit 1"
                echo "fi"
                echo "\"\$_python_bin\" \"\${REPO_ROOT}/${relpath}\" \"\$@\""
            else
                echo "${runner} \"\${REPO_ROOT}/${relpath}\" \"\$@\""
            fi
        done
    } > "$dst"
    chmod +x "$dst"
    echo "install: ${hook_name} -> ${steps[*]}"
}

install_composed_hook "commit-msg" \
    bash "scripts/git_hooks/commit-msg-l2-catalog-conformance.sh" \
    AUTO_PYTHON "scripts/hooks/check_llm_log_on_commit.py"

# Migration cleanup: earlier versions of this installer (and, before that,
# docs/archive/diagnostics/BOOTSTRAP.md's manual instructions) wired one or
# both checks up as `pre-commit`, where the commit message these checks
# depend on either doesn't exist yet (first commit) or is stale (later
# commits). Remove any stale managed pre-commit shim so it doesn't keep
# failing (or, worse, silently passing) by exec'ing a script that no longer
# runs at that phase.
LEGACY_PRE_COMMIT="${HOOKS_DST}/pre-commit"
if [ -f "$LEGACY_PRE_COMMIT" ]; then
    if grep -qE "${MANAGED_MARKER}|${LEGACY_MARKER}" "$LEGACY_PRE_COMMIT" 2>/dev/null; then
        rm -f "$LEGACY_PRE_COMMIT"
        echo "install: removed stale managed pre-commit shim (superseded by commit-msg)"
    elif [ -L "$LEGACY_PRE_COMMIT" ] && \
         [[ "$(readlink "$LEGACY_PRE_COMMIT")" == *check_llm_log_on_commit.py ]]; then
        # The BOOTSTRAP.md-documented manual symlink
        # (`ln -sf ../../scripts/hooks/check_llm_log_on_commit.py .git/hooks/pre-commit`).
        rm -f "$LEGACY_PRE_COMMIT"
        echo "install: removed legacy pre-commit symlink to check_llm_log_on_commit.py (superseded by commit-msg)"
    fi
fi

echo ""
echo "Commit-msg hook installed (L2 catalog conformance + Copilot LLM-log check)."
echo "Bypass with: git commit --no-verify"
echo "Or use trailer: Catalog-Entry: N/A (justification: ...)"
