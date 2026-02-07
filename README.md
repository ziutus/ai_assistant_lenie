# Project Lenie: Personal AI Assistant

Project Lenie, named after the enigmatic protagonist from Peter Watts' novel "Starfish," 
offers advanced solutions for collecting, managing, and searching data using 
Language Model Models (LLMs). 

Lenie enables users to:
* collect and manage links, allowing easy searching of accumulated references using LLM,
* download content from webpages and store it in a PostgreSQL database for later search in a private archive,
* transcribe YouTube videos and store them in a database, facilitating the search for interesting segments (given the ease of finding engaging videos compared to books or articles).

Lenie's functionalities represent an advanced integration of AI technology with users' daily needs, providing efficient data management and deeper content analysis and utilization. However, similar to the literary character who brings inevitable consequences of her existence, Lenie raises questions about the boundaries of technology and our own control over it. It is both a fascinating and daunting tool that requires a conscious approach and responsible usage to maximize benefits and minimize risks associated with the increasing role of artificial intelligence in our lives.

This is a side project. Please be aware that code is during refactoring and correcting as I'm still learning Python and LLMs.

## Komponenty 

* Webowy interfejs do przeglądania zawartości bazy danych
* Wtyczka do Chrome i Kiwi Browser
* Backed napisany w Python

## Wspierane platformy

Platforma | Wsparcie |
|---|---|
|Windows | Chrome + wtyczka |
| Android | Kiwi Browser i wtyczka |
| MacOS | Brak |

## Różnice w porównaniu do firmowych baz wiedzy
W firmowych bazach wiedzy nie zakładamy, że mamy kłamliwe, niewłaściwe lub propagandowe artykuły.
Każdy artykuł jest uważany za równoważny.

W przypadku tematów drażliwych, politycznych lub związanych z pieniędzmi możemy spotkać:
* propagandę państwową (szczególnie w tematach geopolitycznych i politycznych)
* propagandą tematyczną partii (zła Unia, uchodźcy i imigranci, szczepionki itp.)
* działaniami Public Relation firm  (np. to nie prawda, że Tesla została z tyłu w rozwoju aut autonomicznych i elektrycznych)
* działalność oszustów internetowych
* amatorskie teksty udające eksperckie (np. tutoriale mówiące, aby wyłączyć wszystkie mechanizmy bezpieczeństwa Linkusa, bo przeszkadzają)
* działalność troli internetowych
* masowe treści bez wartości generowane przez AI, by zdobyć pozycję w indeksach google,

W związku z tym jest potrzeba zbudowania mechanizmu oceny wiarygodności źródła (np. strony internetowej albo filmu na youtube) oraz autora.

Potrzebna jest również możliwość wybrania tylko określonych źródeł (z wszystkich posiadanych) oraz jawnego wskazywania w wypowiedzi źródeł danych.

## Problemy, które należy rozwiązać podczas budowy takiego rozwiązania

W przypadku posiadania firmowych dokumentów najczęstszym problemem będzie przygotowanie konwersji firmowej wiki, notion czy dokumentów word do formatu wygodnego dla LLmów.

W przypadku korzystania ze źródeł internetowych problemy są inne:
* dostęp do treści jest za paywall-em (rozwiązaniem stosowanym u mnie jest wtyczka do przeglądarki),
* brak możliwości łatwego importowania danych ze stron takich jak linkedin, Facebook itp. (chronią się przed łatwą kradzieżą treści),
* potrzeba napisania analizatorów treści stron pobarnych wtyczką by obniżyć koszty (patrz niżej)
* jakość napisów tworzonych przez automatyczne tłumaczenia youtube,
* cena konwersji (i jakość) audio do tekstu

Przykładowe wielkości dokumentów
* Oryginalny dokument HTML będący zapisaną kopią artykułu z Onet.pl: 300 KB,
* Przekonwertowany do formatu markdown: 15 KB,
* Sama treść artykułu: 3000 słów,

Duże modele językowe, np. te od OpenAI, doskonale radzą sobie z analizą treści całej strony artykułu w formacie markdown, 
ale generuje to duże koszty w porównaniu z analizą samego tekstu artykułu.

Źródła danych dla asystenta osobistego:
* SMS-y, czyli wiadomości wielkośći do 120 znaków (od jakiegoś czasu Google Play blokuje aplikacje mające dostęp do SMS-ów, należy zainstalować "własną" aplikację, np. make),
* emaile (format HTML), kilkaset słów,
* dokumenty PDF (np faktury) i DOC (np. wymagania na stanowisko pracy),
* ebooki (kilkaset tysięcy słów, potrzebny podział na kawałki przed embeddingiem)
* obrazki (np zdjęcia stron książek, faktury, zdjęcia z istotnym kontentem)
* czaty whats up, messanger, itp
* dostęp do kalendarza,
* historia przeglądanych stron (dostęp do slqlite np. w Chromie),
* dostęp do płatnego API serwisu Meetup (graphQL) by mieć informacje kogo możesz spotkać i na kogo uwazać,
* dostęp do płatnych API przeglądających KRS (by wiedzieć czy rozmówca ma własną firmę, fundację itp.)


## Skalowalność i niezawodność rozwiązania
Dla jednego użytkownika wystarczy baza danych Postgersql z odpowiednimi rozszerzeniami.

Jeżeli chcemy, aby pojedyńczy użytkownik mógł działać z różnych urządzeń, należy umożliwić
mu pracę z zewnętrznym serwerem działającym 24h/7. 
Wtedy musimy zadbać o:
* dostępność rozwiązania z dowolnego miejsca na świecie,
* bezpieczeństwo rozwiązania (potrzeba aktualizacji bezpieczeństwa, ochrona przed DDOS itp),
* niskie koszty.
* mało czasu potrzebnego na utrzymanie



W przypadku większej ilości użytkowników należy rozważyć 2 rzeczy:
* koszty skalowania infrastruktury (np. bazy danych)
* wydajność rozwiązania (można dostawiać kontenery albo iść w rozwiązania serverless i kolejki)
* bezpieczeństwo izolacji danych każdego klienta,

## Used technologies
In this project, I'm using:
* Python as server backend
* Postgresql as embedding database
* React as web interface (during creation)
* Hashicorp Vault for secrets (for local and kubernetes environment) 
* AWS as deploying a platform (as I'm lazy and don't want to manage infrastructure)

I'm also preparing a few ways to deploy it:
* docker image (to easy run application)
* Kubernetes helm (to test scalability options)
* AWS lambda (to test Event Driver way of writing application)

As I'm big fun on AWS, you will also see deploy ways like:
* Lambdas (to see Event Driver way of writing applications like that),
* ECS (to see nice way of scalling docker images)
* EKS (to learn more about the costs of managing own Kubernetes cluster and application on it)


## Python notes

### Using uv to manage dependencies

Install uv:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
or on Windows
```
pip install uv
```

Quick start with Makefile:
```bash
make install          # Install base dependencies
make install-all      # Install all dependencies (including optional)
make install-docker   # Install docker dependencies only
make lock             # Update uv.lock after changing pyproject.toml
```

Manual usage:
```bash
cd backend
uv sync                    # Install base dependencies
uv sync --all-extras       # Install all optional dependencies
uv sync --extra docker     # Install specific extra
uv lock                    # Update lock file
```

### Project configuration

Dependencies are managed via `backend/pyproject.toml` with optional dependency groups:
- Base dependencies (server)
- `[docker]` - Minimal dependencies for Docker image
- `[markdown]` - Markdown processing tools
- `[all]` - All dependencies including Google APIs, AWS tools, etc.


## Prerequisites
Before running the Docker container with the Stalker application, make sure you have:

* Docker installed on your computer. Installation instructions can be found in the official Docker documentation.

To create a Docker image for the Stalker application, you need a Dockerfile in your project directory. Below is an example process of building the image.

1. Open a terminal in the directory where the Dockerfile is located.

2. Run the following command to build the Docker image:

```bash
docker build -t stalker-server2:latest .
```

* The -t flag is used to tag (name) the image, in this case stalker.
* The dot . at the end indicates that the Dockerfile is in the current directory.

After the build process is complete, you can run the Docker container with the newly created image by using the command described in the section Running the Stalker Container.

## Virtual Linux Machine

### Debian machine
```bash
useradd lenie-ai
mkdir /home/lenie-ai
chown lenie-ai:lenie-ai /home/lenie-ai/

apt-get install git
apt install python3.11-venv
apt install python3-pip

```

Installation of postgresql database

```bash

```

```bash
python3 server.py
```

## AWS

### Sending image to ECR
```powershell
(Get-ECRLoginCommand -ProfileName stalker-free-developer -Region us-east-1).Password | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
```

```powershell
docker build -t lenie-ai-server .
```
```powershell
docker tag lenie-ai-server:latest ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/lenie-ai-server:latest
```

```powershell
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/lenie-ai-server:latest
```


## Accessing the Application

After starting the appliaction or container, you can access the Stalker application by going to http://localhost:5000 in your web browser.

### Docker

#### Preparing local environment

Install vault binary from: https://developer.hashicorp.com/vault/install

```bash
docker volume create vault_secrets_dev
docker volume create vault_logs_dev
 
 docker run -d --name=vault_dev --cap-add=IPC_LOCK -e 'VAULT_LOCAL_CONFIG={"storage": {"file": {"path":
 "/vault/file"}}, "listener": [{"tcp": { "address": "0.0.0.0:8200", "tls_disable": true}}], "default_lease_ttl": "168h", "max_lease_ttl":
"720h", "ui": true}' -v vault_secrets_dev:/vault/file -v vault_logs_dev:/vault/logs -p 8200:8200 hashicorp/vault server
```

```bash
docker pull pgvector/pgvector:pg17
```

```bash
docker run -d --name lenie-ai-db -e POSTGRES_PASSWORD=postgres -p 5432:5432 pgvector/pgvector:pg17
```

```sql
CREATE EXTENSION vector
```


#### Running application

Running from local image:
```bash
docker run --rm --env-file .env -p 5000:5000 --name lenie-ai-server -d lenie-ai-server:latest
```

Running from remote image:

```powershell
docker run --rm --env-file .env -p 5000:5000 --name lenie-ai-server -d lenieai/lenie-ai-server:latest
```

### Docker compose

```shell
docker-compose.exe create 
docker-compose.exe start
```

## Working with API

You can send example API request even from command line:

```shell

curl -X POST https://pir31ejsf2.execute-api.us-east-1.amazonaws.com/v1/url_add \
     -H "Content-Type: application/json" \
     -H "x-api-key: XXXX" \
     -d '{
           "url": "https://tech.wp.pl/ukrainski-system-delta-zintegrowany-z-polskim-topazem-zadaje-rosjanom-wielkie-straty,7066814570990208a",
           "type": "webpage",
           "note": "Ciekawa integracja z polskim systemem obrazowania pola walki",
           "text": "html strony z podanego URL"
         }'
```

If we have enabled port forward, we can use to validate our API request:

```
curl -H "x-api-key: XXX" -X GET "http://localhost:5000/website_list?type=ALL&
document_state=ALL&search_in_document="
```


## Services which can use to get data

| Service name | provider   | description | link |
|-------------|------------|---|------|
| Textract    | AWS        | PDF to text | https://aws.amazon.com/textract/     |
| assemblyai  | assemblyai | speach to text (0,12$ per  hour) | https://www.assemblyai.com/ |

## Code quality & security

### Linting and formatting (ruff)
```bash
make lint         # Run ruff linter
make lint-fix     # Run ruff with auto-fix
make format       # Format code with ruff
make format-check # Check formatting (for CI)
```

### Security scanning
All security tools are run via `uvx` (uv tool runner) to avoid adding heavy dependencies to the project venv.

```bash
make security        # Run semgrep static analysis
make security-deps   # Check dependencies for vulnerabilities (pip-audit)
make security-bandit # Run bandit Python security linter
make security-safety # Check dependencies with safety
make security-all    # Run all security checks
```

| Tool | Purpose |
|------|---------|
| Semgrep | Static code analysis, security vulnerabilities |
| pip-audit | Dependency vulnerability scanning (PyPI advisory DB) |
| Bandit | Python-specific security linter |
| Safety | Dependency vulnerability check (requires free account) |

### Pre-commit hooks (trufflehog)
Pre-commit hooks include TruffleHog for secret detection. See `.pre-commit-config.yaml`.


# Planned improvements
* add checker which any lambda does not use AWS Lambda Layers anymore


## Why do we need our own LLM?
So far, available LLMs operate in English or implicitly translate to English, losing context or meaning.

Let's translate two texts into English:

Sąsiad wyszedł z psem o 6 rano.

And:

Psy przyszły po sąsiada o 6 rano

As Poles, we perfectly understand the difference between an animal and the slang term for police officers, but you need to know the cultural context.

Now we have Bielik (https://bielik.ai), which perfectly understands the magic of this sentence:

![img.png](bielik_psy_pl.png)

You can use Bielik on [ClouFerro.com](https://sherlock.cloudferro.com/#pricing)
