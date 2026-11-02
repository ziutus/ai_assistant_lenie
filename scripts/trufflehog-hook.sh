#!/usr/bin/env bash
# TruffleHog pre-commit / pre-push hook that works in git worktrees.
#
# The upstream entry `trufflehog git file://. --since-commit HEAD` has two problems here:
#   1. In a linked worktree `.git` is a FILE, so go-git fails with "repository does not exist"
#      (exit 1, no finding) - every commit from a worktree was blocked.
#   2. On pre-commit it scans commits in HEAD..HEAD, i.e. nothing: the staged change is never read.
#
# This wrapper:
#   - pre-commit: exports the STAGED content (the index, not the working copy) of added/changed/
#     renamed files to a temp dir and scans that with `trufflehog filesystem`;
#   - pre-push (pre-commit sets PRE_COMMIT_FROM_REF / PRE_COMMIT_TO_REF): scans the pushed commit
#     range with `trufflehog git` pointed at the main checkout (a real repository from any worktree);
#   - always passes --no-update (the self-updater cannot replace a running trufflehog.exe on Windows
#     and used to make the hook exit 1 without any finding).
#
# TRUFFLEHOG_RESULTS overrides the result filter (default "verified", like the old hook); use
# "verified,unverified,unknown" to see how the hook reacts to an unverified canary.

set -euo pipefail

RESULTS="${TRUFFLEHOG_RESULTS:-verified}"

# pre-commit exports PRE_COMMIT=1; TruffleHog then "overrides default flags for hook context" and scans
# HEAD..HEAD of the repository it is pointed at (0 chunks) whatever range we pass. Hide it.
unset PRE_COMMIT

if ! command -v trufflehog >/dev/null 2>&1; then
    echo "trufflehog not found on PATH (install it; see docs/security/dev-hooks-setup.md)" >&2
    exit 1
fi

to_native_path() {
    if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}

FROM_REF="${PRE_COMMIT_FROM_REF:-}"
TO_REF="${PRE_COMMIT_TO_REF:-}"

if [[ -n "$TO_REF" ]]; then
    # pre-push: a new branch has no remote sha (empty or all zeros) - scan from the merge-base with main
    if [[ -z "$FROM_REF" || "$FROM_REF" =~ ^0+$ ]]; then
        FROM_REF="$(git merge-base origin/main "$TO_REF" 2>/dev/null || true)"
    fi
    if [[ -z "$FROM_REF" ]]; then
        echo "trufflehog-hook: no base commit to scan from, scanning nothing" >&2
        exit 0
    fi
    # Point the git source at the MAIN checkout (parent of the common git dir): it is a real repository
    # seen from any worktree. `file://.` fails in a worktree and `file://<.git dir>` reads 0 chunks.
    COMMON_DIR="$(git rev-parse --path-format=absolute --git-common-dir)"
    MAIN_CHECKOUT="$(to_native_path "$(dirname "$COMMON_DIR")")"
    exec trufflehog --no-update git "file://$MAIN_CHECKOUT" \
        --since-commit "$FROM_REF" --branch "$TO_REF" \
        --results="$RESULTS" --fail --trust-local-git-config
fi

# pre-commit: scan the staged content
STAGED_LIST="$(mktemp)"
EXPORT_DIR="$(mktemp -d)"
trap 'rm -rf "$EXPORT_DIR" "$STAGED_LIST"' EXIT

git diff --cached --name-only --diff-filter=ACMR -z > "$STAGED_LIST"
if [[ ! -s "$STAGED_LIST" ]]; then
    exit 0
fi

git checkout-index --prefix="$EXPORT_DIR/" -z --stdin < "$STAGED_LIST"

# no `exec`: the EXIT trap must still remove the export directory
trufflehog --no-update filesystem "$(to_native_path "$EXPORT_DIR")" \
    --results="$RESULTS" --fail
