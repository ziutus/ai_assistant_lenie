
```bash
gcloud run jobs create lenie-ai-dev-list-storage \
  --image=europe-central2-docker.pkg.dev/core-almanac-466614-s3/my-repo/my-script \
  --volume=name=dane,bucket=lenie-ai-dev-books \
  --volume-mount=name=dane,mount-path=/mnt/dane

```
