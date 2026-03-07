#!/usr/bin/env bash
# Scan git history for secrets between local branch and remote
# Uses both TruffleHog and gitleaks to catch different secret patterns
#
# Usage:
#   ./scripts/scan-history-secrets.sh              # scan unpushed commits vs origin/main
#   ./scripts/scan-history-secrets.sh origin/main   # scan since specific ref
#   ./scripts/scan-history-secrets.sh --full         # scan entire repository history

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

MODE="since-commit"
BASE_REF=""

if [[ "${1:-}" == "--full" ]]; then
    MODE="full"
elif [[ -n "${1:-}" ]]; then
    BASE_REF="$1"
else
    # Auto-detect: find the merge base with origin/main
    git fetch origin main --quiet 2>/dev/null || true
    BASE_REF="$(git merge-base HEAD origin/main 2>/dev/null || echo "")"
    if [[ -z "$BASE_REF" ]]; then
        echo -e "${YELLOW}WARNING: Could not find merge base with origin/main. Scanning last 10 commits.${NC}"
        BASE_REF="HEAD~10"
    fi
fi

COMMITS_TO_SCAN=""
if [[ "$MODE" != "full" ]]; then
    COMMITS_TO_SCAN="$(git log --oneline "$BASE_REF..HEAD" 2>/dev/null || echo "")"
    COMMIT_COUNT="$(echo "$COMMITS_TO_SCAN" | grep -c . || echo 0)"
    echo "=== Secret History Scanner ==="
    echo "Base ref: $BASE_REF"
    echo "Commits to scan: $COMMIT_COUNT"
    echo ""
    if [[ "$COMMIT_COUNT" -eq 0 ]]; then
        echo -e "${GREEN}No unpushed commits to scan.${NC}"
        exit 0
    fi
    echo "$COMMITS_TO_SCAN"
    echo ""
fi

FOUND_SECRETS=0

# --- TruffleHog ---
echo "--- TruffleHog ---"
if command -v trufflehog &>/dev/null; then
    TRUFFLEHOG_ARGS=(git "file://." --no-update --json)
    if [[ "$MODE" == "full" ]]; then
        echo "Scanning entire repository history..."
    else
        TRUFFLEHOG_ARGS+=(--since-commit "$BASE_REF")
    fi

    TRUFFLEHOG_OUTPUT="$(trufflehog "${TRUFFLEHOG_ARGS[@]}" 2>/dev/null || true)"
    if [[ -n "$TRUFFLEHOG_OUTPUT" ]]; then
        echo -e "${RED}SECRETS FOUND by TruffleHog:${NC}"
        echo "$TRUFFLEHOG_OUTPUT" | python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
        print(f\"  Type: {d.get('DetectorName', 'unknown')}\")
        print(f\"  File: {d.get('SourceMetadata', {}).get('Data', {}).get('Git', {}).get('file', 'unknown')}\")
        print(f\"  Commit: {d.get('SourceMetadata', {}).get('Data', {}).get('Git', {}).get('commit', 'unknown')[:12]}\")
        print(f\"  Verified: {d.get('Verified', False)}\")
        print()
    except json.JSONDecodeError:
        print(f'  {line}')
" 2>/dev/null || echo "$TRUFFLEHOG_OUTPUT"
        FOUND_SECRETS=1
    else
        echo -e "${GREEN}No secrets found.${NC}"
    fi
else
    echo -e "${YELLOW}trufflehog not installed, skipping.${NC}"
fi

echo ""

# --- gitleaks ---
echo "--- gitleaks ---"
if command -v gitleaks &>/dev/null; then
    GITLEAKS_ARGS=(detect --source . --no-banner -c "$REPO_ROOT/.gitleaks.toml")
    if [[ "$MODE" == "full" ]]; then
        echo "Scanning entire repository history..."
    else
        GITLEAKS_ARGS+=(--log-opts="$BASE_REF..HEAD")
    fi

    if ! gitleaks "${GITLEAKS_ARGS[@]}" 2>/dev/null; then
        echo -e "${RED}SECRETS FOUND by gitleaks!${NC}"
        FOUND_SECRETS=1
    else
        echo -e "${GREEN}No secrets found.${NC}"
    fi
else
    echo -e "${YELLOW}gitleaks not installed, skipping.${NC}"
fi

echo ""
echo "=== Summary ==="
if [[ "$FOUND_SECRETS" -eq 1 ]]; then
    echo -e "${RED}SECRETS DETECTED! Review findings above and remove before pushing.${NC}"
    exit 1
else
    echo -e "${GREEN}All clear — no secrets found in git history.${NC}"
    exit 0
fi
