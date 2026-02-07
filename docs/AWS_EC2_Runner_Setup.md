# Preparing Self-hosted EC2 Runner

Instructions for preparing an EC2 instance as a self-hosted CI/CD runner (Amazon Linux 2023).

> **Parent document:** [CI_CD.md](CI_CD.md) — general CI/CD pipeline rules and conventions.

## 1. Installing Python 3.11

The project requires Python 3.11. Installation and setting as default version:

```bash
# Install Python 3.11 (if not installed)
sudo dnf install python3.11 -y

# Set Python 3.11 as default
sudo alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
sudo alternatives --config python3

# Verification
python3 --version
# Python 3.11.6
```

## 2. Installing pip

```bash
sudo dnf install python3-pip -y
```

## 3. Installing Go (for osv-scanner)

```bash
sudo dnf update -y
sudo dnf install -y golang

# Verification
go version
```

## 4. Installing Testing Tools

**Flake8 with HTML reports:**
```bash
pip3 install flake8-html
```

**Pytest with HTML reports:**
```bash
pip3 install pytest-html
```

## 5. Installing Security Tools

**Semgrep:**
```bash
python3 -m pip install semgrep

# If there are dependency conflicts:
python3 -m pip install --ignore-installed semgrep
```

**OSV Scanner (via Go):**
```bash
go install github.com/google/osv-scanner/cmd/osv-scanner@v1

# Binary will be installed in ~/go/bin/
# Add to PATH or copy to /usr/local/bin/
sudo cp ~/go/bin/osv-scanner /usr/local/bin/
```

## 6. Installing Docker (optional)

```bash
sudo dnf install docker -y
sudo systemctl start docker
sudo systemctl enable docker

# Add user to docker group
sudo usermod -aG docker $USER
```

## 7. Installing uv (fast package manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"
```

## Summary of Installed Tools

| Tool | Command | Description |
|------|---------|-------------|
| Python 3.11 | `python3` | Python interpreter |
| pip | `pip3` | Python package manager |
| Go | `go` | Go compiler |
| Flake8 | `flake8` | Code style linter |
| Pytest | `pytest` | Testing framework |
| Semgrep | `semgrep` | Security static analysis |
| OSV Scanner | `osv-scanner` | Vulnerability scanning |
| Docker | `docker` | Containerization |
| uv | `uv` | Fast Python package manager |
