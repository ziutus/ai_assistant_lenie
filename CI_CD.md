# CI/CD Reference Documentation

Ten dokument stanowi **bazę wiedzy dla agenta AI** do tworzenia nowych pipeline'ów CI/CD. Zawiera sprawdzone wzorce, komendy i konfiguracje zebrane z poprzednich implementacji (GitLab CI, Jenkins, CircleCI).

> **Uwaga:** Ten dokument nie opisuje aktywnego pipeline'u. Służy jako referencja do budowy nowych konfiguracji CI/CD.

## Kontekst projektu

**Projekt hobbystyczny** - infrastruktura nie działa 24/7. Maszyny wirtualne są uruchamiane tylko gdy są potrzebne, w celu obniżenia kosztów.

**Dynamiczne adresy IP** - ze względów oszczędnościowych adresy IP nie są rezerwowane (Elastic IP), lecz przypisywane dynamicznie przy starcie instancji. Dlatego skrypty startowe zawierają aktualizację rekordów DNS (np. Route 53).

**Historia i kierunek rozwoju:**
- **Początki (AWS)** - projekt pierwotnie był tworzony jako serverless w AWS, aby poznać możliwości tej platformy
- **Obecny kierunek (GCP)** - autor pracuje zawodowo w Google Cloud Platform, więc projekt będzie migrowany do GCP
- **Kubernetes** - opcja wdrożenia na Kubernetes jest wspierana ze względu na chęć pogłębienia wiedzy w tym obszarze

## Cel dokumentu

Agent AI powinien wykorzystać tę dokumentację do:
- Tworzenia nowych pipeline'ów CI/CD dla dowolnej platformy
- Wyboru odpowiednich narzędzi bezpieczeństwa i testowania
- Konfiguracji infrastruktury AWS (EC2 runner)
- Implementacji buildów i deploymentu Docker

## Spis treści

1. [Kontekst projektu](#kontekst-projektu)
2. [Przegląd pipeline'u](#przegląd-pipelineu)
3. [Wzorzec CircleCI](#wzorzec-circleci)
4. [Infrastruktura AWS](#infrastruktura-aws)
   - [Skrypty do uruchamiania instancji z aktualizacją DNS](#skrypty-do-ręcznego-uruchamiania-instancji-z-aktualizacją-dns)
5. [Przygotowanie Self-hosted Runner EC2](#przygotowanie-self-hosted-runner-ec2)
6. [Self-hosted Jenkins na EC2](#self-hosted-jenkins-na-ec2)
7. [Etapy pipeline'u](#etapy-pipelineu)
8. [Narzędzia bezpieczeństwa](#narzędzia-bezpieczeństwa)
   - [Semgrep](#semgrep---analiza-statyczna-kodu)
   - [TruffleHog](#trufflehog---wykrywanie-sekretów)
   - [OSV Scanner](#osv-scanner---skanowanie-podatności-zależności)
   - [Qodana](#qodana---analiza-kodu-jetbrains)
9. [Testy i jakość kodu](#testy-i-jakość-kodu)
10. [Build i deploy Docker](#build-i-deploy-docker)
11. [Zmienne środowiskowe](#zmienne-środowiskowe)
12. [Artefakty](#artefakty)

---

## Przegląd pipeline'u

Pipeline CI/CD składa się z następujących głównych etapów:

```
.pre (start_runner)
    ↓
test + security-checks (równolegle)
    ↓
build
    ↓
deploy
    ↓
clean-node
    ↓
.post (stop_runner)
```

## Wzorzec CircleCI

Przykładowa konfiguracja CircleCI z self-hosted runnerem na EC2.

### Architektura

```
start-ec2
    ↓
run-job-on-ec2 (testy)
    ↓
run-job-on-ec2-docker (build)
    ↓
stop-ec2
```

### Orbs i Executors

```yaml
orbs:
  aws-cli: circleci/aws-cli@3.1    # Integracja z AWS CLI

executors:
  python-executor:                  # Lekki kontener Python
    docker:
      - image: cimg/python:3.11

  machine-executor:                 # Maszyna z Docker
    machine:
      docker_layer_caching: true    # Cache warstw Docker
```

### Jobs

#### 1. start-ec2
Uruchamia instancję EC2 przed rozpoczęciem testów.

```yaml
jobs:
  start-ec2:
    executor: python-executor
    steps:
      - aws-cli/setup
      - run:
          name: "Start EC2 instances"
          command: |
            aws ec2 start-instances --instance-ids $INSTANCE_ID
```

#### 2. run-job-on-ec2
Instaluje zależności i uruchamia testy na self-hosted runner EC2.

```yaml
run-job-on-ec2:
  executor: machine-executor
  resource_class: itsnap/itsnap-runner    # Self-hosted runner
  steps:
    - checkout
    - run:
        name: "Install uv and dependencies"
        command: |
          curl -LsSf https://astral.sh/uv/install.sh | sh
          export PATH="$HOME/.cargo/bin:$PATH"
          uv venv venv
          . venv/bin/activate
          uv pip install -r backend/requirements_server.txt
    - run:
        name: "Run tests"
        command: |
          . venv/bin/activate
          mkdir -p test-results
          python -m pytest tests/unit --junitxml=test-results/results.xml || true
    - store_test_results:
        path: test-results/results.xml
```

**Uwagi:**
- Używa `uv venv` zamiast `--system` (izolowane środowisko)
- Generuje raport w formacie JUnit XML
- Testy tylko jednostkowe (`tests/unit`)

#### 3. run-job-on-ec2-docker
Buduje obraz Docker na self-hosted runner.

```yaml
run-job-on-ec2-docker:
  executor: machine-executor
  resource_class: itsnap/itsnap-runner
  steps:
    - checkout
    - run:
        name: "Execute job on EC2"
        command: |
          docker build -t lenie-ai-server:latest .
```

#### 4. stop-ec2
Zatrzymuje instancję EC2 po zakończeniu pipeline'u.

```yaml
stop-ec2:
  executor: python-executor
  steps:
    - aws-cli/setup
    - run:
        name: "Stop EC2 instances"
        command: |
          aws ec2 stop-instances --instance-ids $INSTANCE_ID
```

### Workflow

```yaml
workflows:
  ec2-workflow:
    jobs:
      - start-ec2:
          filters:
            branches:
              only: [main, dev]
      - run-job-on-ec2:
          requires: [start-ec2]
          filters:
            branches:
              only: [main, dev]
      - run-job-on-ec2-docker:
          requires: [run-job-on-ec2]
          filters:
            branches:
              only: [main, dev]
      - stop-ec2:
          requires: [run-job-on-ec2-docker]
          filters:
            branches:
              only: [main, dev]
```

### Self-hosted Runner

CircleCI używa self-hosted runnera na EC2:
- **Resource class:** `itsnap/itsnap-runner`
- Runner musi być zainstalowany na instancji EC2
- Dokumentacja: https://circleci.com/docs/runner-overview/

### Przechowywanie wyników testów

```yaml
- store_test_results:
    path: test-results/results.xml
```

CircleCI automatycznie parsuje format JUnit XML i wyświetla wyniki w UI.

## Infrastruktura AWS

### Automatyczne zarządzanie instancją EC2

Pipeline automatycznie zarządza instancją EC2 AWS, która służy jako runner:

**Uruchomienie instancji (przed pipeline'em):**
```bash
aws ec2 start-instances --instance-ids $INSTANCE_ID --region $AWS_REGION
aws ec2 wait instance-running --instance-ids $INSTANCE_ID --region $AWS_REGION
```

**Zatrzymanie instancji (po pipeline'ie):**
```bash
aws ec2 stop-instances --instance-ids $INSTANCE_ID --region $AWS_REGION
aws ec2 wait instance-stopped --instance-ids $INSTANCE_ID --region $AWS_REGION
```

**Sprawdzenie stanu instancji (Jenkins):**
```bash
aws ec2 describe-instances \
    --instance-ids $INSTANCE_ID \
    --query "Reservations[0].Instances[0].State.Name" \
    --output text \
    --region $AWS_REGION
```

### Konfiguracja AWS CLI

```bash
aws configure set aws_access_key_id $AWS_ACCESS_KEY_ID
aws configure set aws_secret_access_key $AWS_SECRET_ACCESS_KEY
aws configure set region $AWS_REGION
```

### Skrypty do ręcznego uruchamiania instancji z aktualizacją DNS

Przy wyłączaniu infrastruktury AWS w celach oszczędnościowych, po ponownym uruchomieniu instancji EC2 zmienia się jej publiczne IP. Poniższy wzorzec automatycznie aktualizuje rekord DNS w Route 53.

**Wzorzec skryptu Python (`ec2_start_with_dns.py`):**

```python
import boto3
import time
import os
from dotenv import load_dotenv

load_dotenv()

# Konfiguracja z pliku .env
INSTANCE_ID = os.getenv("AWS_INSTANCE_ID")
HOSTED_ZONE_ID = os.getenv("AWS_HOSTED_ZONE_ID")
DOMAIN_NAME = os.getenv("DOMAIN_NAME")


def start_ec2_instance(instance_id):
    """Uruchamia instancję EC2"""
    ec2 = boto3.client("ec2")
    print(f"Uruchamiam instancję EC2 o ID: {instance_id}")
    ec2.start_instances(InstanceIds=[instance_id])

    print("Czekam na uruchomienie instancji...")
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance_id])
    print("Instancja EC2 została uruchomiona!")


def get_instance_public_ip(instance_id):
    """Pobiera publiczny adres IP instancji EC2"""
    ec2 = boto3.client("ec2")
    response = ec2.describe_instances(InstanceIds=[instance_id])

    public_ip = response["Reservations"][0]["Instances"][0].get("PublicIpAddress")
    if not public_ip:
        print("Publiczny adres IP nie jest jeszcze dostępny. Czekam...")
        time.sleep(10)
        return get_instance_public_ip(instance_id)

    print(f"Publiczny adres IP instancji: {public_ip}")
    return public_ip


def update_route53_record(hosted_zone_id, domain_name, public_ip):
    """Aktualizuje rekord A w Route 53"""
    route53 = boto3.client("route53")
    print(f"Aktualizuję rekord A w Route 53 dla domeny: {domain_name}")

    response = route53.change_resource_record_sets(
        HostedZoneId=hosted_zone_id,
        ChangeBatch={
            "Changes": [
                {
                    "Action": "UPSERT",
                    "ResourceRecordSet": {
                        "Name": domain_name,
                        "Type": "A",
                        "TTL": 300,
                        "ResourceRecords": [{"Value": public_ip}],
                    },
                }
            ]
        },
    )
    print(f"Rekord A zaktualizowany! Status: {response['ChangeInfo']['Status']}")


if __name__ == "__main__":
    if not all([INSTANCE_ID, HOSTED_ZONE_ID, DOMAIN_NAME]):
        raise ValueError("Ustaw zmienne INSTANCE_ID, HOSTED_ZONE_ID i DOMAIN_NAME w .env")

    # 1. Uruchomienie instancji EC2
    start_ec2_instance(INSTANCE_ID)

    # 2. Pobranie publicznego adresu IP
    public_ip = get_instance_public_ip(INSTANCE_ID)

    # 3. Aktualizacja rekordu Route 53
    update_route53_record(HOSTED_ZONE_ID, DOMAIN_NAME, public_ip)
```

**Wymagane zmienne w `.env`:**

```bash
# Dla Jenkins
JENKINS_AWS_INSTANCE_ID=i-0123456789abcdef0
JENKINS_DOMAIN_NAME=jenkins.example.com

# Dla OpenVPN
OPENVPN_OWN_AWS_INSTANCE_ID=i-0987654321fedcba0
OPENVPN_OWN_DOMAIN_NAME=vpn.example.com

# Wspólne
AWS_HOSTED_ZONE_ID=Z0123456789ABCDEFGHIJ
```

**Wymagane uprawnienia IAM:**

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:StartInstances",
                "ec2:DescribeInstances"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "route53:ChangeResourceRecordSets"
            ],
            "Resource": "arn:aws:route53:::hostedzone/HOSTED_ZONE_ID"
        }
    ]
}
```

**Użycie:**

```bash
# Instalacja zależności
pip install boto3 python-dotenv

# Uruchomienie
python ec2_start_with_dns.py
```

## Przygotowanie Self-hosted Runner EC2

Instrukcja przygotowania instancji EC2 jako self-hosted runnera CI/CD (Amazon Linux 2023).

### 1. Instalacja Python 3.11

Projekt wymaga Python 3.11. Instalacja i ustawienie jako domyślna wersja:

```bash
# Instalacja Python 3.11 (jeśli nie jest zainstalowany)
sudo dnf install python3.11 -y

# Ustawienie Python 3.11 jako domyślny
sudo alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
sudo alternatives --config python3

# Weryfikacja
python3 --version
# Python 3.11.6
```

### 2. Instalacja pip

```bash
sudo dnf install python3-pip -y
```

### 3. Instalacja Go (dla osv-scanner)

```bash
sudo dnf update -y
sudo dnf install -y golang

# Weryfikacja
go version
```

### 4. Instalacja narzędzi testowych

**Flake8 z raportami HTML:**
```bash
pip3 install flake8-html
```

**Pytest z raportami HTML:**
```bash
pip3 install pytest-html
```

### 5. Instalacja narzędzi bezpieczeństwa

**Semgrep:**
```bash
python3 -m pip install semgrep

# Jeśli występują konflikty zależności:
python3 -m pip install --ignore-installed semgrep
```

**OSV Scanner (via Go):**
```bash
go install github.com/google/osv-scanner/cmd/osv-scanner@v1

# Binarka zostanie zainstalowana w ~/go/bin/
# Dodaj do PATH lub skopiuj do /usr/local/bin/
sudo cp ~/go/bin/osv-scanner /usr/local/bin/
```

### 6. Instalacja Docker (opcjonalnie)

```bash
sudo dnf install docker -y
sudo systemctl start docker
sudo systemctl enable docker

# Dodanie użytkownika do grupy docker
sudo usermod -aG docker $USER
```

### 7. Instalacja uv (szybki menedżer pakietów)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"
```

### Podsumowanie zainstalowanych narzędzi

| Narzędzie | Komenda | Opis |
|-----------|---------|------|
| Python 3.11 | `python3` | Interpreter Python |
| pip | `pip3` | Menedżer pakietów Python |
| Go | `go` | Kompilator Go |
| Flake8 | `flake8` | Linter stylu kodu |
| Pytest | `pytest` | Framework testowy |
| Semgrep | `semgrep` | Analiza statyczna bezpieczeństwa |
| OSV Scanner | `osv-scanner` | Skanowanie podatności |
| Docker | `docker` | Konteneryzacja |
| uv | `uv` | Szybki menedżer pakietów Python |

## Self-hosted Jenkins na EC2

Dodatkowe konfiguracje dla self-hosted Jenkins na instancji EC2.

### Automatyczna konfiguracja Security Group przy starcie

Skrypt uruchamiany przy starcie instancji EC2, który automatycznie dodaje publiczne IP workera do Security Group Jenkins, umożliwiając połączenie.

**Skrypt startowy (`/usr/local/bin/aws_jenkins_worker_start.sh`):**

```bash
#!/bin/bash

REGION="us-east-1"

# Pobranie tokena IMDSv2
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

if [ -z "$TOKEN" ]; then
    echo "Failed to retrieve the token."
    exit 1
fi

# Pobranie publicznego IP instancji
IP_ADDRESS=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
    http://169.254.169.254/latest/meta-data/public-ipv4)

# Ustawienie Python 3.11 jako domyślny
alternatives --set python3 /usr/bin/python3.11

# Dodanie reguły do Security Group
aws ec2 authorize-security-group-ingress \
    --region $REGION \
    --group-id sg-XXXXXXXXX \
    --protocol tcp \
    --port 8443 \
    --cidr ${IP_ADDRESS}/32

exit 0
```

**Uwagi:**
- Używa IMDSv2 (Instance Metadata Service v2) dla bezpieczeństwa
- Wymaga uprawnień IAM: `ec2:AuthorizeSecurityGroupIngress`
- Zmień `sg-XXXXXXXXX` na ID swojej Security Group

**Plik systemd (`/etc/systemd/system/jenkins_worker.service`):**

```ini
[Unit]
Description=Update AWS Security Group for Jenkins Server to allow connection
After=network.target

[Service]
ExecStart=/usr/local/bin/aws_jenkins_worker_start.sh
Type=simple
RemainAfterExit=true

[Install]
WantedBy=multi-user.target
```

**Instalacja serwisu:**

```bash
# Skopiuj skrypt
sudo cp aws_jenkins_worker_start.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/aws_jenkins_worker_start.sh

# Skopiuj plik serwisu
sudo cp jenkins_worker.service /etc/systemd/system/

# Włącz i uruchom serwis
sudo systemctl daemon-reload
sudo systemctl enable jenkins_worker.service
sudo systemctl start jenkins_worker.service
```

### Certyfikaty SSL (Let's Encrypt)

Jenkins może używać certyfikatów SSL z Let's Encrypt.

**Odnowienie certyfikatu:**

```bash
letsencrypt renew
```

**Konwersja do formatu PKCS12:**

```bash
openssl pkcs12 -export \
    -in /etc/letsencrypt/live/jenkins.example.com/fullchain.pem \
    -inkey /etc/letsencrypt/live/jenkins.example.com/privkey.pem \
    -out jenkins.p12 \
    -name jenkins \
    -CAfile /etc/letsencrypt/live/jenkins.example.com/chain.pem \
    -caname root
```

**Import do Java KeyStore:**

```bash
keytool -importkeystore \
    -deststorepass <haslo_keystore> \
    -destkeypass <haslo_klucza> \
    -destkeystore /var/lib/jenkins/jenkins.jks \
    -srckeystore jenkins.p12 \
    -srcstoretype PKCS12 \
    -srcstorepass <haslo_p12> \
    -alias jenkins
```

### GitHub Webhooks

Testowanie webhooków GitHub:

```bash
curl -X POST \
    -H "Content-Type: application/json" \
    -d '{"key1":"value1", "key2":"value2"}' \
    https://your-api-gateway.execute-api.us-east-1.amazonaws.com/v1/infra/git-webhooks
```

## Etapy pipeline'u

### 1. Przygotowanie środowiska

**Instalacja uv (szybki menedżer pakietów Python):**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"
```

**Instalacja zależności:**
```bash
uv pip install --system -r backend/requirements_server.txt
```

### 2. Checkout kodu

**Jenkins (z GitHub):**
```groovy
git credentialsId: 'github-token',
    url: 'https://github.com/ziutus/ai_assistant_lenie_server',
    branch: "${env.BRANCH_NAME}"
```

### 3. Tworzenie katalogów na raporty

```bash
mkdir -p results/
mkdir -p pytest-results/
mkdir -p flake_reports/
```

## Narzędzia bezpieczeństwa

### Semgrep - Analiza statyczna kodu

Semgrep wykrywa potencjalne luki bezpieczeństwa w kodzie.

```bash
# Instalacja
uv pip install --system semgrep

# Uruchomienie z automatyczną konfiguracją
semgrep --config=auto --output semgrep-report.json
```

**Artefakt:** `semgrep-report.json`

### TruffleHog - Wykrywanie sekretów

TruffleHog skanuje repozytorium w poszukiwaniu przypadkowo commitowanych sekretów (API keys, hasła, tokeny).

```bash
docker run --rm --name trufflehog \
    trufflesecurity/trufflehog:latest git file://. \
    --only-verified --bare 2>&1 | tee trufflehog.txt
```

**Flagi:**
- `--only-verified` - raportuje tylko zweryfikowane sekrety
- `--bare` - minimalistyczny output

**Artefakt:** `trufflehog.txt`

### OSV Scanner - Skanowanie podatności zależności

OSV Scanner sprawdza zależności pod kątem znanych podatności.

```bash
/usr/local/bin/osv-scanner scan --lockfile requirements.txt
```

**Uwaga:** Ten etap może wymagać dodatkowej konfiguracji.

**Artefakt:** `osv_scan_results.json`

### Qodana - Analiza kodu JetBrains

Qodana to narzędzie JetBrains do statycznej analizy kodu, integrujące inspekcje z PyCharm/IntelliJ.

#### Konfiguracja (`qodana.yaml`)

```yaml
version: "1.0"
profile:
  name: qodana.starter           # Profil inspekcji (starter/recommended/all)
linter: jetbrains/qodana-python:latest  # Linter dla Pythona

# Opcjonalne - włączenie/wyłączenie inspekcji
# include:
#   - name: PyUnusedLocalInspection
# exclude:
#   - name: PyBroadExceptionInspection
#     paths:
#       - legacy/
```

#### Uruchomienie w CI/CD

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

**Lokalnie (Docker):**
```bash
docker run --rm -it \
  -v $(pwd):/data/project/ \
  -v $(pwd)/.qodana:/data/results/ \
  jetbrains/qodana-python:latest
```

#### Wykrywane problemy (inspekcje Python)

| Inspekcja | Opis | Priorytet |
|-----------|------|-----------|
| `PyArgumentListInspection` | Brakujące/nadmiarowe argumenty funkcji | WARNING |
| `PyBroadExceptionInspection` | Zbyt ogólne przechwytywanie wyjątków (`except Exception`) | WARNING |
| `PyDefaultArgumentInspection` | Mutowalny argument domyślny (np. `def f(x=[])`) | WARNING |
| `PyTypeCheckerInspection` | Niezgodność typów (type hints) | WARNING |
| `PyUnusedLocalInspection` | Nieużywane zmienne lokalne | WARNING |
| `PyUnresolvedReferencesInspection` | Nierozpoznane referencje/importy | ERROR |

#### Format raportu SARIF

Qodana generuje raport w formacie SARIF (Static Analysis Results Interchange Format):

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

**Artefakty:**
- `qodana.sarif.json` - szczegółowy raport wyników
- `.qodana/` - cache i dodatkowe raporty

**Wymaga:** Token `QODANA_TOKEN` i konto na qodana.cloud (opcjonalnie dla lokalnego użycia)

## Testy i jakość kodu

### Pytest - Testy jednostkowe i integracyjne

```bash
# Uruchomienie z raportem HTML
pytest --self-contained-html --html=pytest-results/report.html
```

**Flagi:**
- `--self-contained-html` - generuje samodzielny plik HTML (bez zewnętrznych zasobów)
- `--html=pytest-results/report.html` - ścieżka do raportu

**Artefakt:** `pytest-results/` (cały katalog)

### Flake8 - Sprawdzanie stylu kodu

```bash
# Instalacja
uv pip install --system flake8-html

# Uruchomienie z raportem HTML
flake8 --format=html --htmldir=flake_reports/

# Z wykluczeniem katalogów
flake8 --format=html --exclude=ai_dev3 --htmldir=flake_reports/
```

**Artefakt:** `flake_reports/` (cały katalog)

## Build i deploy Docker

### Build obrazu Docker

```bash
# Build z tagiem wersji
docker build -t $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:$TAG_VERSION .

# Tagowanie jako latest
docker tag $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:$TAG_VERSION \
           $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:latest
```

### Push do Docker Hub

```bash
# Logowanie
docker login -u "$DOCKER_HUB_USERNAME" -p "$DOCKER_HUB_TOKEN"

# Push obu tagów
docker push $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:$TAG_VERSION
docker push $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:latest
```

### Czyszczenie starych obrazów

```bash
chmod +x infra/docker/docker_images_clean.sh
infra/docker/docker_images_clean.sh --remove-name lenie
```

## Zmienne środowiskowe

### Wymagane zmienne

| Zmienna | Opis | Przykład |
|---------|------|----------|
| `AWS_REGION` | Region AWS | `us-east-1` |
| `INSTANCE_ID` | ID instancji EC2 runner'a | `i-03908d34c63fce042` |
| `CI_REGISTRY_IMAGE` | Nazwa obrazu Docker | `lenie-ai-server` |
| `TAG_VERSION` | Wersja tagu Docker | `0.2.11.6` |

### Sekrety (przechowywane w CI/CD)

| Sekret | Opis |
|--------|------|
| `AWS_ACCESS_KEY_ID` | Klucz dostępu AWS (GitLab: `GITLAB_AWS_ACCESS_KEY_ID`) |
| `AWS_SECRET_ACCESS_KEY` | Sekretny klucz AWS (GitLab: `GITLAB_AWS_SECRET_ACCESS_KEY`) |
| `DOCKER_HUB_USERNAME` | Nazwa użytkownika Docker Hub |
| `DOCKER_HUB_TOKEN` | Token dostępu Docker Hub |
| `QODANA_TOKEN` | Token Qodana (opcjonalnie) |

## Artefakty

### Lista artefaktów generowanych przez pipeline

| Artefakt | Etap | Opis |
|----------|------|------|
| `semgrep-report.json` | security-checks | Raport analizy statycznej Semgrep |
| `trufflehog.txt` | security-checks | Raport wykrytych sekretów |
| `osv_scan_results.json` | security-checks | Raport podatności zależności |
| `qodana.sarif.json` | security-checks | Raport Qodana w formacie SARIF |
| `pytest-results/` | test | Raporty testów pytest (HTML) |
| `flake_reports/` | test | Raporty stylu kodu Flake8 (HTML) |

### Archiwizacja artefaktów (Jenkins)

```groovy
archiveArtifacts artifacts: 'results/semgrep-report.json', fingerprint: true
archiveArtifacts artifacts: 'pytest-results/**/*', allowEmptyArchive: true
```

## Triggery pipeline'u

Pipeline uruchamia się dla gałęzi:
- `dev`
- `main`

Etapy build i deploy wykonują się tylko dla tych gałęzi.

## Równoległe wykonywanie

Niektóre etapy mogą być wykonywane równolegle:

**GitLab CI:**
- `job-pytest` i `job-style-tool-flake8-scan` (stage: test)
- `job-security-tool-semgrep`, `job-security-tool-trufflehog`, `job-security-tool-osv_scan` (stage: security-checks)

**Jenkins:**
```groovy
stage('Python tests') {
    parallel {
        stage('Run Pytest') { ... }
        stage('Run Flake8 Style Check') { ... }
    }
}
```

---

## Jak używać tej dokumentacji

Przy tworzeniu nowego pipeline'u CI/CD:

1. **Wybierz platformę** (GitHub Actions, GitLab CI, CircleCI, Jenkins, etc.)
2. **Określ etapy** - wykorzystaj [Przegląd pipeline'u](#przegląd-pipelineu) jako szablon
3. **Skonfiguruj infrastrukturę** - jeśli używasz self-hosted runnera, patrz [Infrastruktura AWS](#infrastruktura-aws)
4. **Dodaj narzędzia bezpieczeństwa** - wybierz z sekcji [Narzędzia bezpieczeństwa](#narzędzia-bezpieczeństwa)
5. **Skonfiguruj testy** - patrz [Testy i jakość kodu](#testy-i-jakość-kodu)
6. **Ustaw zmienne** - lista w [Zmienne środowiskowe](#zmienne-środowiskowe)

---

*Dokumentacja referencyjna wygenerowana na podstawie historycznych konfiguracji: CircleCI, GitLab CI, Jenkins (worker scripts, SSL), Qodana, README_RUNNER.md*
