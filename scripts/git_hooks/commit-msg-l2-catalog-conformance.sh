#!/usr/bin/env bash
# commit-msg-l2-catalog-conformance.sh
#
# Enforces the COMPOSITION_MANDATE v2 spec-authority rule at the commit boundary
# for any change to L2.2 Design-A runner / helpers / catalog / oracle-loader code.
#
# Refuses to commit unless the commit message body contains a `Catalog-Entry:`
# trailer with a fenced YAML block quoting the relevant PROCESS_CATALOG.yaml
# entry verbatim.
#
# Rationale: 2026-06-07/08 saw 5 fanout merges drift from the catalog because
# no codex PROMPT (or operator-authored helper code) quoted the catalog. The
# spec authority rule is documented in docs/prompts/COMPOSITION_MANDATE_v2.md
# but document-level rules drift. This hook makes the rule executable at the
# only chokepoint that matters: commit landing.
#
# Runs as a `commit-msg` hook, not `pre-commit`. Git only writes the commit
# message to disk (and passes its path as $1) once the `commit-msg` phase
# begins; at `pre-commit` time no message exists yet, so a message-content
# check installed as `pre-commit` cannot see the current commit's message
# (see history: it previously read a stale/absent COMMIT_EDITMSG, which
# always failed on a repo's or worktree's very first commit). Staged files
# are still fully accessible via `git diff --cached` at `commit-msg` time
# because the commit object has not been created yet, so the trigger-file
# detection below is unaffected by the phase move.
#
# Bypass (use sparingly, leaves a forensic trail in git log):
#   git commit --no-verify   (skips ALL hooks)
#   - OR -
#   include line "Catalog-Entry: N/A (justification: <reason>)" in the commit
#     message body. Recognized for non-process-specific changes (e.g. infra
#     refactors that don't touch any single process's spec).
#
# Installed by: scripts/git_hooks/install.sh

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"

# Git invokes commit-msg hooks with the path to the message file as $1. Fall
# back to `git rev-parse --git-path COMMIT_EDITMSG` (worktree-correct, unlike
# a hardcoded "${REPO_ROOT}/.git/COMMIT_EDITMSG") for manual/test invocation.
COMMIT_MSG_FILE="${1:-$(git rev-parse --git-path COMMIT_EDITMSG)}"

WATCHED_PATTERNS=(
    "tests/vivarium/l2_2_design_a_runner\.py"
    "tests/vivarium/_l2_2_design_a_runner_helpers\.py"
    "tests/vivarium/_l2_2_design_a_projections\.py"
    "tests/vivarium/test_l2_2_design_a.*\.py"
    "docs/phase_f/l2_2_design_a/PROCESS_CATALOG\.yaml"
)

STAGED_FILES="$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null || true)"

if [ -z "$STAGED_FILES" ]; then
    exit 0
fi

TRIGGERED=0
for pattern in "${WATCHED_PATTERNS[@]}"; do
    if echo "$STAGED_FILES" | grep -E -q "^${pattern}$"; then
        TRIGGERED=1
        break
    fi
done

if [ "$TRIGGERED" -eq 0 ]; then
    exit 0
fi

if [ ! -f "$COMMIT_MSG_FILE" ]; then
    echo "commit-msg-l2: ERROR no commit message file at $COMMIT_MSG_FILE" >&2
    exit 1
fi

MSG_BODY="$(cat "$COMMIT_MSG_FILE")"

if echo "$MSG_BODY" | grep -E -q "^Catalog-Entry: N/A \(justification:"; then
    echo "commit-msg-l2: PASS (Catalog-Entry: N/A justification present)" >&2
    exit 0
fi

if echo "$MSG_BODY" | grep -E -q "^Catalog-Entry:"; then
    if echo "$MSG_BODY" | awk '
        /^Catalog-Entry:/ { found_trailer=1; next }
        found_trailer && /^[[:space:]]*```yaml/ { in_block=1; next }
        in_block && /^[[:space:]]*```/ { saw_close=1; exit }
        in_block { lines++ }
        END { exit (saw_close && lines > 0 ? 0 : 1) }
    '; then
        echo "commit-msg-l2: PASS (Catalog-Entry trailer with yaml block)" >&2
        exit 0
    else
        echo "commit-msg-l2: ERROR Catalog-Entry trailer present but no fenced yaml block follows it." >&2
        echo "  Format required:" >&2
        echo "    Catalog-Entry:" >&2
        echo "    \`\`\`yaml" >&2
        echo "      - name: <Process>" >&2
        echo "        ..." >&2
        echo "    \`\`\`" >&2
        exit 1
    fi
fi

echo "" >&2
echo "==================================================================" >&2
echo "commit-msg-l2: BLOCKED" >&2
echo "==================================================================" >&2
echo "" >&2
echo "Your commit touches L2.2 Design-A code:" >&2
for f in $STAGED_FILES; do
    for pattern in "${WATCHED_PATTERNS[@]}"; do
        if echo "$f" | grep -E -q "^${pattern}$"; then
            echo "  - $f" >&2
            break
        fi
    done
done
echo "" >&2
echo "COMPOSITION_MANDATE v2 spec-authority rule requires the commit message" >&2
echo "to quote the relevant PROCESS_CATALOG.yaml entry verbatim." >&2
echo "" >&2
echo "Add either of:" >&2
echo "" >&2
echo "  Catalog-Entry:" >&2
echo "  \`\`\`yaml" >&2
echo "    - name: <Process>" >&2
echo "      bucket: ..." >&2
echo "      primary_channel: ..." >&2
echo "      M_ticks: ..." >&2
echo "      karr_artifact: ..." >&2
echo "  \`\`\`" >&2
echo "" >&2
echo "  OR (for non-process-specific infra changes):" >&2
echo "" >&2
echo "  Catalog-Entry: N/A (justification: <one-sentence reason>)" >&2
echo "" >&2
echo "Catalog file: docs/phase_f/l2_2_design_a/PROCESS_CATALOG.yaml" >&2
echo "Mandate spec: docs/prompts/COMPOSITION_MANDATE_v2.md" >&2
echo "" >&2
echo "Bypass (logged in git via --no-verify):" >&2
echo "  git commit --no-verify -m \"...\"" >&2
echo "" >&2
echo "==================================================================" >&2
exit 1
