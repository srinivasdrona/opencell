#!/usr/bin/env bash
# install.sh - install the L2 catalog-conformance commit-msg hook.
#
# Copies (or symlinks where supported) scripts/git_hooks/* into .git/hooks/.
# Idempotent. Refuses to overwrite a non-managed commit-msg hook unless
# called with --force.
#
# The check runs at the `commit-msg` phase (not `pre-commit`): Git only
# writes the commit message to disk once `commit-msg` runs, so this is the
# earliest phase at which both the staged files (still uncommitted) and the
# actual commit message are simultaneously available.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_SRC="${REPO_ROOT}/scripts/git_hooks"
# Hooks live in the *common* git dir, which is shared by all worktrees of a
# repo. `${REPO_ROOT}/.git` is wrong here when run from a linked worktree:
# there, `.git` is a file (a gitdir pointer), not the directory that holds
# `hooks/`. `git rev-parse --git-common-dir` resolves correctly in both the
# main checkout and any linked worktree.
HOOKS_DST="$(git rev-parse --git-common-dir)/hooks"

FORCE=0
if [ "${1:-}" = "--force" ]; then
    FORCE=1
fi

install_hook () {
    local hook_name="$1"
    local source_basename="$2"
    local src="${HOOKS_SRC}/${source_basename}"
    local dst="${HOOKS_DST}/${hook_name}"

    if [ ! -f "$src" ]; then
        echo "install: ERROR source not found: $src" >&2
        return 1
    fi

    if [ -f "$dst" ]; then
        if grep -q "L2-CATALOG-CONFORMANCE-HOOK-MANAGED" "$dst" 2>/dev/null; then
            :
        elif [ "$FORCE" -eq 0 ]; then
            echo "install: refusing to overwrite existing non-managed ${hook_name}; use --force to override" >&2
            return 1
        fi
    fi

    cat > "$dst" <<EOF
#!/usr/bin/env bash
# L2-CATALOG-CONFORMANCE-HOOK-MANAGED
# Installed from scripts/git_hooks/${source_basename}
# To uninstall, delete this file. To update, re-run scripts/git_hooks/install.sh.
REPO_ROOT="\$(git rev-parse --show-toplevel)"
exec "\${REPO_ROOT}/scripts/git_hooks/${source_basename}" "\$@"
EOF
    chmod +x "$dst"
    echo "install: ${hook_name} -> ${src}"
}

install_hook "commit-msg" "commit-msg-l2-catalog-conformance.sh"

# Migration cleanup: earlier versions of this installer wired the check up
# as `pre-commit`, exec'ing a script that has since been renamed/moved to
# `commit-msg`. Remove a stale managed pre-commit shim so it doesn't fail
# every commit by exec'ing a path that no longer exists.
LEGACY_PRE_COMMIT="${HOOKS_DST}/pre-commit"
if [ -f "$LEGACY_PRE_COMMIT" ] && grep -q "L2-CATALOG-CONFORMANCE-HOOK-MANAGED" "$LEGACY_PRE_COMMIT" 2>/dev/null; then
    rm -f "$LEGACY_PRE_COMMIT"
    echo "install: removed stale managed pre-commit shim (superseded by commit-msg)"
fi

echo ""
echo "L2 catalog-conformance commit-msg hook installed."
echo "Bypass with: git commit --no-verify"
echo "Or use trailer: Catalog-Entry: N/A (justification: ...)"
