#!/usr/bin/env bash
set -e

# verify-documentation-metrics.sh
# Compares documented infrastructure counts in docs/infrastructure-metrics.md
# against actual counts from source files.
# Exit 0 if all match, exit 1 if any discrepancy found.
# Must be run from the project root directory.

METRICS_FILE="docs/infrastructure-metrics.md"
SERVER_FILE="backend/server.py"
DEPLOY_INI="infra/aws/cloudformation/deploy.ini"
TEMPLATES_DIR="infra/aws/cloudformation/templates"
API_GW_APP="$TEMPLATES_DIR/api-gw-app.yaml"
API_GW_INFRA="$TEMPLATES_DIR/api-gw-infra.yaml"
URL_ADD="$TEMPLATES_DIR/url-add.yaml"

ERRORS=0
CHECKS=0
PASSED=0

check_file_exists() {
    if [ ! -f "$1" ]; then
        echo "ERROR: Required file not found: $1"
        exit 1
    fi
}

compare() {
    local label="$1"
    local documented="$2"
    local actual="$3"
    CHECKS=$((CHECKS + 1))
    if [ "$documented" -eq "$actual" ]; then
        echo "PASS: $label — documented: $documented, actual: $actual"
        PASSED=$((PASSED + 1))
    else
        echo "FAIL: $label — documented: $documented, actual: $actual"
        ERRORS=$((ERRORS + 1))
    fi
}

# --- Verify required files exist ---
check_file_exists "$METRICS_FILE"
check_file_exists "$SERVER_FILE"
check_file_exists "$DEPLOY_INI"
check_file_exists "$API_GW_APP"
check_file_exists "$API_GW_INFRA"
check_file_exists "$URL_ADD"

if [ ! -d "$TEMPLATES_DIR" ]; then
    echo "ERROR: Required directory not found: $TEMPLATES_DIR"
    exit 1
fi

echo "=== Documentation Metrics Verification ==="
echo ""

# ============================================================
# SECTION 1: Extract documented counts from infrastructure-metrics.md
# ============================================================

# Helper: extract a documented count and validate it was found
extract_documented() {
    local label="$1"
    local value="$2"
    if [ -z "$value" ]; then
        echo "ERROR: Could not parse '$label' from $METRICS_FILE"
        echo "       Check that the metrics file format matches expected patterns."
        exit 1
    fi
    echo "$value"
}

# Flask endpoint count: line like "**Total endpoints: 19**"
DOC_FLASK=$(grep -oP 'Total endpoints: \K[0-9]+' "$METRICS_FILE" || true)
DOC_FLASK=$(extract_documented "Flask endpoint count (Total endpoints: N)" "$DOC_FLASK")

# api-gw-app endpoint count: line like "— 11 endpoint paths:**"
DOC_API_APP=$(grep 'api-gw-app' "$METRICS_FILE" | grep -oP '— \K[0-9]+(?= endpoint paths)' || true)
DOC_API_APP=$(extract_documented "api-gw-app endpoint count" "$DOC_API_APP")

# api-gw-infra endpoint count: line like "— 7 endpoint paths:**"
DOC_API_INFRA=$(grep 'api-gw-infra' "$METRICS_FILE" | grep -oP '— \K[0-9]+(?= endpoint paths)' || true)
DOC_API_INFRA=$(extract_documented "api-gw-infra endpoint count" "$DOC_API_INFRA")

# url-add endpoint count: line like "— 1 endpoint path:**"
DOC_URL_ADD=$(grep 'url-add' "$METRICS_FILE" | grep -oP '— \K[0-9]+(?= endpoint path)' || true)
DOC_URL_ADD=$(extract_documented "url-add endpoint count" "$DOC_URL_ADD")

# Lambda total: line like "**Total: 12 Lambda functions in AWS**"
DOC_LAMBDA_TOTAL=$(grep -oP 'Total: \K[0-9]+(?= Lambda functions)' "$METRICS_FILE" || true)
DOC_LAMBDA_TOTAL=$(extract_documented "Lambda total count" "$DOC_LAMBDA_TOTAL")

# CF-managed Lambda count: line like "**CF-managed via deploy.ini (10 functions):**"
DOC_LAMBDA_CF=$(grep -oP 'CF-managed via deploy.ini \(\K[0-9]+(?= functions)' "$METRICS_FILE" || true)
DOC_LAMBDA_CF=$(extract_documented "CF-managed Lambda count" "$DOC_LAMBDA_CF")

# deploy.ini template count: line like "**Templates in deploy.ini [dev]: 26**"
DOC_DEPLOY_TEMPLATES=$(grep -oP 'Templates in deploy.ini \[dev\]: \K[0-9]+' "$METRICS_FILE" || true)
DOC_DEPLOY_TEMPLATES=$(extract_documented "deploy.ini template count" "$DOC_DEPLOY_TEMPLATES")

# Total template file count: line like "**Total .yaml files in templates/: 33**"
DOC_TOTAL_TEMPLATES=$(grep -oP 'Total .yaml files in templates/: \K[0-9]+' "$METRICS_FILE" || true)
DOC_TOTAL_TEMPLATES=$(extract_documented "Total .yaml template file count" "$DOC_TOTAL_TEMPLATES")

echo "Documented counts (from $METRICS_FILE):"
echo "  Flask endpoints:        $DOC_FLASK"
echo "  api-gw-app paths:       $DOC_API_APP"
echo "  api-gw-infra paths:     $DOC_API_INFRA"
echo "  url-add paths:          $DOC_URL_ADD"
echo "  Lambda total:           $DOC_LAMBDA_TOTAL"
echo "  Lambda CF-managed:      $DOC_LAMBDA_CF"
echo "  deploy.ini templates:   $DOC_DEPLOY_TEMPLATES"
echo "  Total .yaml templates:  $DOC_TOTAL_TEMPLATES"
echo ""

# ============================================================
# SECTION 2: Count actual infrastructure values
# ============================================================

# Flask routes: count @app.route decorators in server.py
ACTUAL_FLASK=$(grep -c '@app\.route' "$SERVER_FILE" || true)

# api-gw-app.yaml: count unique OpenAPI paths (lines starting with 10 spaces + /path:)
# Pattern handles CRLF files by not anchoring to end-of-line
ACTUAL_API_APP=$(grep -cP '^ {10}/[a-zA-Z_]' "$API_GW_APP" || true)

# api-gw-infra.yaml: count unique OpenAPI paths (lines starting with 10 spaces + /infra/)
ACTUAL_API_INFRA=$(grep -cP '^ {10}/infra/' "$API_GW_INFRA" || true)

# url-add.yaml: count PathPart resources (each defines one endpoint path)
ACTUAL_URL_ADD=$(grep -c 'PathPart:' "$URL_ADD" || true)

# Lambda CF-managed: count AWS::Lambda::Function resources in templates listed in deploy.ini
ACTUAL_LAMBDA_CF=0
while IFS= read -r line; do
    # Strip trailing CR if present (CRLF files)
    line=$(echo "$line" | tr -d '\r')
    template_path="infra/aws/cloudformation/$line"
    if [ -f "$template_path" ]; then
        count=$(grep -c 'AWS::Lambda::Function' "$template_path" || true)
        ACTUAL_LAMBDA_CF=$((ACTUAL_LAMBDA_CF + count))
    fi
done < <(grep -E '^\s*templates/' "$DEPLOY_INI" | sed 's/^[[:space:]]*//')

# Lambda non-CF: count unique function names hardcoded in api-gw-app.yaml
# These are lenie_2_db and lenie_2_internet, referenced as Lambda function URIs
# NOTE: Pattern depends on current Lambda naming convention (lenie_2_ prefix).
# Must be updated when backlog item B-3 (rename-legacy-lambda-lenie-2-internet-and-db) is implemented.
ACTUAL_LAMBDA_NON_CF=$(grep -oE 'function:lenie_2_[a-z_]+' "$API_GW_APP" | sort -u | wc -l)

ACTUAL_LAMBDA_TOTAL=$((ACTUAL_LAMBDA_CF + ACTUAL_LAMBDA_NON_CF))

# deploy.ini [dev] active templates: non-commented lines starting with templates/
# Use awk to extract only [dev] section (stops at next [section] or EOF)
ACTUAL_DEPLOY_TEMPLATES=$(awk '/^\[dev\]/{found=1; next} /^\[/{found=0} found' "$DEPLOY_INI" | grep -cE '^\s*templates/' || true)

# Total .yaml files in templates directory
ACTUAL_TOTAL_TEMPLATES=$(find "$TEMPLATES_DIR" -name "*.yaml" -type f | wc -l)

echo "Actual counts (from source files):"
echo "  Flask endpoints:        $ACTUAL_FLASK"
echo "  api-gw-app paths:       $ACTUAL_API_APP"
echo "  api-gw-infra paths:     $ACTUAL_API_INFRA"
echo "  url-add paths:          $ACTUAL_URL_ADD"
echo "  Lambda total:           $ACTUAL_LAMBDA_TOTAL (CF: $ACTUAL_LAMBDA_CF + non-CF: $ACTUAL_LAMBDA_NON_CF)"
echo "  Lambda CF-managed:      $ACTUAL_LAMBDA_CF"
echo "  deploy.ini templates:   $ACTUAL_DEPLOY_TEMPLATES"
echo "  Total .yaml templates:  $ACTUAL_TOTAL_TEMPLATES"
echo ""

# ============================================================
# SECTION 3: Compare documented vs actual
# ============================================================

echo "=== Comparison Results ==="
echo ""

compare "Flask endpoints" "$DOC_FLASK" "$ACTUAL_FLASK"
compare "api-gw-app endpoint paths" "$DOC_API_APP" "$ACTUAL_API_APP"
compare "api-gw-infra endpoint paths" "$DOC_API_INFRA" "$ACTUAL_API_INFRA"
compare "url-add endpoint paths" "$DOC_URL_ADD" "$ACTUAL_URL_ADD"
compare "Lambda functions total" "$DOC_LAMBDA_TOTAL" "$ACTUAL_LAMBDA_TOTAL"
compare "Lambda CF-managed" "$DOC_LAMBDA_CF" "$ACTUAL_LAMBDA_CF"
compare "deploy.ini templates" "$DOC_DEPLOY_TEMPLATES" "$ACTUAL_DEPLOY_TEMPLATES"
compare "Total .yaml template files" "$DOC_TOTAL_TEMPLATES" "$ACTUAL_TOTAL_TEMPLATES"

echo ""
echo "=== Summary: $PASSED/$CHECKS checks passed, $ERRORS failed ==="

if [ "$ERRORS" -gt 0 ]; then
    exit 1
fi

exit 0
