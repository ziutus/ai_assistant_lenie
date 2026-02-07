# CI/CD Tools — Installation and Usage

Detailed installation, configuration, and invocation instructions for all tools used in the CI/CD pipeline.

> **Parent document:** [CI_CD.md](CI_CD.md) — general CI/CD pipeline rules and conventions.

## Pipeline Environment Setup

### Installing uv (fast Python package manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"
```

### Installing dependencies

```bash
uv pip install --system -r backend/requirements_server.txt
```

### Creating Report Directories

```bash
mkdir -p results/
mkdir -p pytest-results/
mkdir -p flake_reports/
```

---

## Security Tools

### Local Development - Quick Security Checks

For local development, all security tools can be run via `uvx` (uv tool runner) without installing to project venv:

```bash
make security        # Semgrep static analysis
make security-deps   # pip-audit - dependency vulnerabilities
make security-bandit # Bandit - Python security linter
make security-safety # Safety - dependency check
make security-all    # Run all checks
```

### Semgrep - Static Code Analysis

Semgrep detects potential security vulnerabilities in code.

```bash
# CI - Installation and run
uv pip install --system semgrep
semgrep --config=auto --output semgrep-report.json
```

**Local development:** Use `uvx` to run semgrep without installing to project venv:
```bash
make security
# or directly:
uvx semgrep --config=auto backend/
```

**Artifact:** `semgrep-report.json`

### TruffleHog - Secret Detection

TruffleHog scans the repository for accidentally committed secrets (API keys, passwords, tokens).

```bash
docker run --rm --name trufflehog \
    trufflesecurity/trufflehog:latest git file://. \
    --only-verified --bare 2>&1 | tee trufflehog.txt
```

**Flags:**
- `--only-verified` - reports only verified secrets
- `--bare` - minimalistic output

**Artifact:** `trufflehog.txt`

### OSV Scanner - Dependency Vulnerability Scanning

OSV Scanner checks dependencies for known vulnerabilities.

```bash
/usr/local/bin/osv-scanner scan --lockfile requirements.txt
```

**Note:** This stage may require additional configuration.

**Artifact:** `osv_scan_results.json`

### Qodana - JetBrains Code Analysis

Qodana is a JetBrains tool for static code analysis, integrating inspections from PyCharm/IntelliJ.

#### Configuration (`qodana.yaml`)

```yaml
version: "1.0"
profile:
  name: qodana.starter           # Inspection profile (starter/recommended/all)
linter: jetbrains/qodana-python:latest  # Python linter

# Optional - enable/disable inspections
# include:
#   - name: PyUnusedLocalInspection
# exclude:
#   - name: PyBroadExceptionInspection
#     paths:
#       - legacy/
```

#### Running in CI/CD

**GitLab CI:**
```yaml
image: jetbrains/qodana-python-community:2024.1
cache:
  key: qodana-2024.1-$CI_DEFAULT_BRANCH-$CI_COMMIT_REF_SLUG
  paths:
    - .qodana/cache
variables:
  QODANA_TOKEN: $QODANA_TOKEN
  QODANA_ENDPOINT: "https://qodana.cloud"
script:
  - qodana --cache-dir=$CI_PROJECT_DIR/.qodana/cache
```

**Locally (Docker):**
```bash
docker run --rm -it \
  -v $(pwd):/data/project/ \
  -v $(pwd)/.qodana:/data/results/ \
  jetbrains/qodana-python:latest
```

#### Detected Issues (Python Inspections)

| Inspection | Description | Priority |
|------------|-------------|----------|
| `PyArgumentListInspection` | Missing/extra function arguments | WARNING |
| `PyBroadExceptionInspection` | Too broad exception catching (`except Exception`) | WARNING |
| `PyDefaultArgumentInspection` | Mutable default argument (e.g., `def f(x=[])`) | WARNING |
| `PyTypeCheckerInspection` | Type mismatch (type hints) | WARNING |
| `PyUnusedLocalInspection` | Unused local variables | WARNING |
| `PyUnresolvedReferencesInspection` | Unresolved references/imports | ERROR |

#### SARIF Report Format

Qodana generates a report in SARIF format (Static Analysis Results Interchange Format):

```json
{
  "version": "2.1.0",
  "runs": [{
    "tool": {
      "driver": {
        "name": "PY",
        "fullName": "Qodana",
        "version": "242.23726.102"
      }
    },
    "results": [{
      "ruleId": "PyArgumentListInspection",
      "level": "warning",
      "message": { "text": "Parameter 'stack' unfilled" },
      "locations": [{
        "physicalLocation": {
          "artifactLocation": { "uri": "library/api/aws/s3_aws.py" },
          "region": { "startLine": 30, "startColumn": 39 }
        }
      }]
    }]
  }]
}
```

**Artifacts:**
- `qodana.sarif.json` - detailed results report
- `.qodana/` - cache and additional reports

**Requires:** `QODANA_TOKEN` token and qodana.cloud account (optional for local use)

---

## Tests and Code Quality

### Pytest - Unit and Integration Tests

```bash
# Run with HTML report
pytest --self-contained-html --html=pytest-results/report.html
```

**Flags:**
- `--self-contained-html` - generates a standalone HTML file (without external resources)
- `--html=pytest-results/report.html` - path to report

**Artifact:** `pytest-results/` (entire directory)

### Flake8 - Code Style Checking

```bash
# Installation
uv pip install --system flake8-html

# Run with HTML report
flake8 --format=html --htmldir=flake_reports/

# With directory exclusion
flake8 --format=html --exclude=ai_dev3 --htmldir=flake_reports/
```

**Artifact:** `flake_reports/` (entire directory)

