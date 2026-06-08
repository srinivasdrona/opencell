#!/usr/bin/env bash
# install.sh - install the L2 catalog-conformance pre-commit hook.
#
# Copies (or symlinks where supported) scripts/git_hooks/* into .git/hooks/.
# Idempotent. Refuses to overwrite a non-managed pre-commit hook unless
# called with --force.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_SRC="${REPO_ROOT}/scripts/git_hooks"
HOOKS_DST="${REPO_ROOT}/.git/hooks"

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

install_hook "pre-commit" "pre-commit-l2-catalog-conformance.sh"

echo ""
echo "L2 catalog-conformance pre-commit hook installed."
echo "Bypass with: git commit --no-verify"
echo "Or use trailer: Catalog-Entry: N/A (justification: ...)"
