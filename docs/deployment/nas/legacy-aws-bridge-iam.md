# IAM dla tymczasowego bridge'a AWS → NAS

`lenie-cloud-bridge` odczytuje wyłącznie historyczny bufor AWS i przekazuje dane
do NAS. Nie uruchamia Lambda, nie czyta SSM i nie zapisuje niczego w AWS.

Aktualne konto, region i nazwy wdrożonych zasobów są prowadzone w prywatnym
runbooku operatorskim. Ten dokument zachowuje wyłącznie parametryzowany
kontrakt wdrożeniowy.

## Minimalne uprawnienia

Dedykowany użytkownik IAM potrzebuje wyłącznie:

| Usługa | Akcja | Zasób |
|---|---|---|
| DynamoDB | `dynamodb:Query` | tabela `lenie_dev_documents` i jej indeks `DateIndex` |
| S3 | `s3:GetObject` | `lenie-dev-website-content/*` |
| S3 | `s3:ListBucket` | bucket `lenie-dev-website-content` — wyłącznie do rozróżnienia brakującego obiektu od braku uprawnień |

Nie przyznawaj `AdministratorAccess`, żadnego zapisu S3,
`dynamodb:Scan`, `dynamodb:GetItem`, `dynamodb:PutItem`, SSM ani uprawnień do
Lambda.

`s3:ListBucket` jest celowym wyjątkiem: bez niego S3 zwraca `AccessDenied`
zamiast `NoSuchKey` dla nieistniejącego klucza. Dzięki temu bridge może
rozpoznać historyczny rekord AWS bez raw source, zamiast mylić go z błędem
dostępu.

Szablon [legacy-aws-pull-policy.yaml](../../../infra/aws/cloudformation/templates/legacy-aws-pull-policy.yaml)
tworzy tylko managed policy, nie tworzy użytkownika, grupy ani klucza. Nie jest
wpisany do `deploy.ini`, więc zwykły deploy całej infrastruktury go nie uruchomi.

## Ręczne utworzenie użytkownika

1. W AWS IAM utwórz użytkownika, np. `lenie-dev-nas-legacy-pull`.
2. Nie włączaj dostępu do konsoli AWS.
3. Utwórz access key dla zastosowania „Application running outside AWS”.
4. Utwórz policy z treści szablonu powyżej albo najpierw wdroż osobny stack
   CloudFormation i podepnij wygenerowaną managed policy do użytkownika.
5. Skopiuj `Access key ID` i `Secret access key` tylko do bezpiecznego kanału;
   sekret jest widoczny tylko przy utworzeniu.
6. Nie zapisuj kluczy w repozytorium, w `nas.env`, parametrach joba ani w logach.

## Konfiguracja bridge'a na NAS

Po utworzeniu użytkownika operator zapisuje w Vault (`secret/lenie/dev`):

```text
AWS_LEGACY_PULL_ACCESS_KEY_ID=<access-key-id>
AWS_LEGACY_PULL_SECRET_ACCESS_KEY=<secret-access-key>
AWS_LEGACY_PULL_REGION=us-east-1
AWS_LEGACY_PULL_ACCOUNT_ID=<optional-expected-account-id>
AWS_LEGACY_PULL_DYNAMODB_TABLE=lenie_dev_documents
AWS_LEGACY_PULL_S3_BUCKET=lenie-dev-website-content
AWS_LEGACY_PULL_OVERLAP_SECONDS=300
```

`AWS_LEGACY_PULL_SESSION_TOKEN` dodaj tylko dla poświadczeń tymczasowych. `AWS_LEGACY_PULL_ACCOUNT_ID`
jest opcjonalne i obecnie służy wyłącznie przyszłej kontroli operatorskiej.

Następnie zrestartuj wyłącznie `lenie-cloud-bridge` i uruchom ręczny job dry-run
z jawnym `since`. Nie włączaj schedulera — to należy do PR4.

## Opcjonalne wdrożenie samej policy przez CloudFormation

Uruchom z WSL (nie zmienia to użytkownika ani klucza):

```bash
cd /mnt/c/Users/ziutus/git/_lenie-all/lenie-server-2025/infra/aws/cloudformation
aws cloudformation deploy \
  --region us-east-1 \
  --stack-name lenie-dev-legacy-aws-pull-policy \
  --template-file templates/legacy-aws-pull-policy.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides ProjectCode=lenie Environment=dev
```

Przed wykonaniem użyj `aws cloudformation validate-template` albo change setu.
