```bash
aws organizations create-account --email krzysztof+lenie-dev@lenie-ai.eu --account-name lenie_ai_dev
```
```text
Fedora40 WSL cloudformation$ ./deploy.sh --help
./deploy.sh: illegal option -- -
ERROR: Unknown option ?
Usage:
   ./deploy.sh -r <aws_region>  [-h]

   -r aws-region - A AWS Region where stack should be created/updated/deleted (default: us-east-1)
   -p PROJECT_CODE - project code (for example: lenie)
   -s stage - Deployment stage (one of prod,cob,qa,dev,test,feature,staging) (default: )
   -d - change default action from Create/Update to Delete
   -t  - create change-sets instead of apply changes (default: false)


   -h show this message

  The configuration file is deploy.ini in current directory.

  In Cloudformation you have main types of actions for stacks: create stack, update stack, delete stack.
  This script can automatically choose action between create or update depends on existing stacks (it is checking names
  of stacks)

  This script can also works with changesets.

  Example usage:
   ./deploy.sh -r us-east-1 -p lenie -s dev -t

```

```text
Fedora40 WSL cloudformation$ ./deploy.sh -p lenie -s dev
Create stacks in us-east-1
creating or updating stack - inside function
Processing template templates/vpc.yaml
Processing template templates/vpc.yaml
Creating stack lenie-dev-vpc
action: create
finally create section looks like:
--template-body file:///mnt/c/Users/ziutus/git/_lenie-all/lenie-server-2025/infra/aws/cloudformation/templates/vpc.yaml --capabilities 
CAPABILITY_NAMED_IAM --parameters file:///mnt/c/Users/ziutus/git/_lenie-all/lenie-server-2025/infra/aws/cloudformation/parameters/dev/vpc.json
Calling: aws --region "us-east-1" cloudformation create-stack --stack-name "lenie-dev-vpc" --template-body file:///mnt/c/Users/ziutus/g
it/_lenie-all/lenie-server-2025/infra/aws/cloudformation/templates/vpc.yaml --capabilities CAPABILITY_NAMED_IAM --parameters file:///mnt/c/Users/ziutus/git/_lenie-all/lenie-server-2025/infra/aws/cloudformation/parameters/dev/vpc.json
Waiting for stack lenie-dev-vpc

```

Czynności na starym koncie
* zrobienie snapshotu bazy danych i udostępnienie go dla nowego konta,
* zrobienie obrazu AMI maszyn i udostępnienie dla nowego konta (w przyszłości maszyny EC2 powinny być budowane z IaC ale teraz jeszcze nie są)

Kolejność tworzenia ustawień na nowym koncie

* włączenie cost explorer by móc podłączyć soft do analizy kosztów konta,
* stworzenie budzetów by dostawać ostrzeżenia w postaci emaili,

* tworzenie VPC (vpc.yaml),
* tworzenie haseł, by RDS miał wartości typu użytkownik i hasło,
* zmiana domyślnego hasła utworzonego w poprzednim kroku,
* zmiana w parameters vpc_id dla rds.json (do poprawy w przyszłości)
* zmiana w parameters dla rds.json informacji o lokazliacji hasła (account ID jest na sztywno)
* stworzenie klucza KMS by móc skopiować backup RDS-a między kontami
* stworzenie kolejki sqs-application-errors by móc być informowanym o problemach
* stworzenie warstw dla lambd
* 
