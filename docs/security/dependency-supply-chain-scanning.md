# Dependency Supply-Chain Scanning

This project uses several complementary controls for dependencies:

| Tool | Detects | Use it for |
|---|---|---|
| Dependabot, pip-audit, OSV Scanner | Known vulnerable versions (CVEs/GHSAs) | Vulnerability management |
| depx | Known malicious or hijacked packages (`MAL-*`) | Supply-chain malware detection |

`depx` does not replace the existing CVE scanners. It matches local dependency lock files and SBOMs against ProjectDiscovery's malicious-package intelligence, including OpenSSF Malicious Packages data. It is passive: it does not install, change, or remove project dependencies.

## Native Windows use

Install the matching Windows binary from the [depx releases page](https://github.com/projectdiscovery/depx/releases), unpack it, and put `depx.exe` in a directory on `PATH` (normally `$env:USERPROFILE\go\bin`).

Alternatively, build a pinned version from a local clone. This route is needed instead of `go install github.com/projectdiscovery/depx/cmd/depx@...`, because the module currently has Go `replace` directives, which Go does not permit when installing a versioned remote module:

```powershell
$installDir = Join-Path $env:USERPROFILE 'go\bin'
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
git clone --depth 1 --branch v0.1.1 https://github.com/projectdiscovery/depx.git "$env:TEMP\depx-v0.1.1"
Push-Location "$env:TEMP\depx-v0.1.1"
go build -o (Join-Path $installDir 'depx.exe') .\cmd\depx
Pop-Location
```

Make sure Go's binary directory (normally `$env:USERPROFILE\go\bin`) is on `PATH`. From the repository root, run:

```powershell
.\scripts\security-depx.ps1
```

The script audits the entire repository, including Python `uv.lock` files and Node.js `package-lock.json` files, and exits with the same status as `depx`.

Use a narrower path when needed:

```powershell
.\scripts\security-depx.ps1 -Path .\backend
```

If the local PowerShell execution policy blocks the script, run it for the current process only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\security-depx.ps1
```

## CI gate

CI should run the equivalent command before build and deployment steps:

```bash
depx audit . --require-clean
```

`--require-clean` makes the job fail when a known malicious package is found. Exit code `1` means a finding; `2` is a usage error; `3` means the upstream intelligence source was unavailable. Do not prefix this command with shell error-suppression operators, since that would turn the security gate into a report-only check.

For machine-readable artifacts, depx can also export JSON and SARIF:

```bash
depx audit . --require-clean \
  --output results/depx.json \
  --sarif-export results/depx.sarif
```

GitHub Actions can upload the SARIF output to code scanning. See the [depx documentation](https://github.com/projectdiscovery/depx) and GitHub's [SARIF upload guide](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/integrate-with-existing-tools/upload-sarif-file).

## Finding triage

Treat a malicious-package finding as an incident: stop the affected build or deployment, identify any installed version and exposed secrets, remove or replace the dependency, and rotate potentially exposed credentials. If a package is verified as benign, record the investigation and use `depx`'s `--exclude-pkg` file only for that documented exception.
