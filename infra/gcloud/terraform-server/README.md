
# Setup

```shell
gcloud config set project lenie-ai-dev-2025-03
```

```shell
gcloud services enable artifactregistry.googleapis.com --project=lenie-ai-dev-2025-03
gcloud services enable run.googleapis.com
gcloud services enable dns.googleapis.com
```

For API Gateway, the following services need to be enabled:

```shell
gcloud services enable apigateway.googleapis.com
gcloud services enable servicecontrol.googleapis.com
```

```bash
terraform plan -target="module.lenie-ai-server"
```

```shell
gcloud artifacts docker images list europe-west3-docker.pkg.dev/lenie-ai-dev-2025-03/lenie-ai-dev-2025-03/convert-ebook --include-tags
```

Allow Docker to authenticate via gcloud:

```shell
gcloud auth configure-docker europe-west3-docker.pkg.dev
```

```text
❯     gcloud auth configure-docker europe-west3-docker.pkg.dev
WARNING: Your config file at [C:\Users\ziutus\.docker\config.json] contains these credential helper entries:
{
  "credHelpers": {
    "asia.gcr.io": "gcloud",
    "eu.gcr.io": "gcloud",
    "gcr.io": "gcloud",
    "marketplace.gcr.io": "gcloud",
    "staging-k8s.gcr.io": "gcloud",
    "us.gcr.io": "gcloud"
  }
}
Adding credentials for: europe-west3-docker.pkg.dev
After update, the following will be written to your Docker config file located at [C:\Users\ziutus\.docker\config.json]:
 {
  "credHelpers": {
    "asia.gcr.io": "gcloud",
    "eu.gcr.io": "gcloud",
    "gcr.io": "gcloud",
    "marketplace.gcr.io": "gcloud",
    "staging-k8s.gcr.io": "gcloud",
    "us.gcr.io": "gcloud",
    "europe-west3-docker.pkg.dev": "gcloud"
  }
}

Do you want to continue (Y/n)?

Docker configuration file updated.
```

Test image pull:
```shell
 docker pull europe-west3-docker.pkg.dev/lenie-ai-dev-2025-03/lenie-ai-dev-2025-03/convert-ebook:0.0.1
```
