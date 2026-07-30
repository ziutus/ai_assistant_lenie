# File storage

Lenie uses one S3-compatible interface for durable document objects. Local disk is the default, so a desktop installation needs no MinIO container.

## Target NAS topology

In the target deployment the NAS is the only execution and persistence environment:

```text
phone / computer browser
          |
          v
React UI -> API container -> PostgreSQL job queue
                              |
                              v
                         worker container
                         /             \
                MinIO durable data   NAS work volume
```

The browser only submits and monitors work. Import, conversion, transcription, analysis and embedding processes run in worker containers on the NAS. No scheduled or manual job may depend on a developer computer.

MinIO is the durable object store and backup boundary. A Docker volume or NAS bind mount is still used as a worker scratch/work directory because path-oriented conversion tools require a filesystem. This is NAS-local ephemeral state, not a dependency on a user's computer. Jobs must be restartable from PostgreSQL plus MinIO and may delete their scratch directory after completion.

The existing persistent `document_analysis_jobs` queue is the implementation pattern to generalize. The target is a common jobs table/API and a dedicated `lenie-worker` container. The API process should not execute long-running jobs in a background thread.

## Configuration

Portable single-computer Compose fallback:

```env
STORAGE_BACKEND=local
STORAGE_LOCAL_ROOT=/app/data
```

NAS MinIO setup:

```env
STORAGE_BACKEND=minio
STORAGE_ENDPOINT_URL=http://lenie-minio:9000
STORAGE_PUBLIC_ENDPOINT_URL=http://192.168.200.7:9000
STORAGE_BUCKET=lenie-storage
STORAGE_ACCESS_KEY=lenie-admin
STORAGE_SECRET_KEY=change-me
STORAGE_REGION=us-east-1
```

AWS S3 uses `STORAGE_BACKEND=s3`, omits `STORAGE_ENDPOINT_URL`, and can use the normal AWS credential chain. Google Cloud Storage is not S3 API compatible by default; use its interoperability/HMAC endpoint or add a native adapter later.

`STORAGE_BACKEND` is explicit. The legacy `AWS_S3_WEBSITE_CONTENT` is accepted as a bucket-name fallback, but no longer selects cloud storage by itself.

## Files uploaded for import

The `/upload-file` page sends an authenticated `POST /upload-file` request to
the configured Lenie API (not to the retired AWS API Gateway). The API writes
the original file to the configured `ObjectStorage`, so on the NAS it lands in
MinIO under a key like:

```text
uploads/2026/07/2dd1...-book.pdf
```

The upload area accepts PDF, EPUB and MOBI. It is a durable staging area,
separate from the final document source and extracted artifacts; users should
retain the returned key until an importer has completed. `UPLOAD_MAX_BYTES`
sets the API limit and defaults to 250 MiB.

The current PDF book wrapper can read an uploaded original directly, including
from a developer machine that can reach MinIO:

```console
cd backend
python imports/book_import_pdf_twierdza_linux.py \
  --storage-key uploads/2026/07/2dd1...-book.pdf --apply
```

EPUB and MOBI are stored in the same area now; their format-specific importer
can use `library.upload_storage.get_uploaded_file()` in the same way, without
changing the UI or storage layout.

## Presigned URLs

`ObjectStorage.presigned_get_url(key, expires_in=3600)` returns a time-limited URL the browser can fetch directly, without going through the API — needed because an `<img src>` request never carries the `x-api-key` header, so a proxied/authenticated route can't serve it.

On `S3Storage` this calls `generate_presigned_url("get_object", ...)`. SigV4 signs the `Host` header, so a link generated against the container-internal endpoint (`STORAGE_ENDPOINT_URL=http://lenie-minio:9000`) would not validate when the browser fetches it — it would resolve to a host the browser can't reach. `STORAGE_PUBLIC_ENDPOINT_URL` (browser-reachable, e.g. `http://192.168.200.7:9000`) is used to build a second, lazily-created client just for signing; when it's unset (plain AWS S3, where the configured endpoint is already public), the normal client is reused.

`LocalStorage.presigned_get_url()` always returns `None` — a local disk has nothing to sign. Callers degrade to a placeholder (no `<img>`, caption only); this path is only exercised in a plain single-computer Compose setup, real testing happens against MinIO on the NAS.

Links expire after 3600 s (1 hour). Callers don't need to cache/refresh them client-side — a page reload (e.g. switching reader chapters) fetches a fresh link.

## Running storage-writing scripts from a developer machine

`STORAGE_ENDPOINT_URL=http://lenie-minio:9000` is a container-internal hostname — it only resolves inside the NAS's Docker network. Any script that writes through `storage_from_config()` from outside that network (a developer's own machine, not a `lenie-worker` container) needs `lenie-minio` to resolve to the NAS's LAN IP. MinIO's S3 API port is published on the host (`compose.nas.yaml`, `9000:9000`), so a hosts-file entry is enough — no tunnel needed:

```console
# Windows, PowerShell as Administrator:
Add-Content -Path "C:\Windows\System32\drivers\etc\hosts" -Value "192.168.200.7`tlenie-minio"
# Linux/macOS:
echo "192.168.200.7  lenie-minio" | sudo tee -a /etc/hosts
```

Without this, `put_bytes()`/`presigned_get_url()`'s underlying boto3 client raises `EndpointConnectionError` trying to reach `lenie-minio`. This applies to `imports/storage_migrate.py` and any `imports/book_import_pdf_<slug>.py` run with `--apply` (both write the source file and extracted images through `ObjectStorage`) — the target hostname doesn't change, so this is a one-time setup step per developer machine, not per script run.

## Migration and accounting

Run from `backend/`, with the target backend configured:

```console
python imports/storage_migrate.py upload --source data --dry-run
python imports/storage_migrate.py upload --source data
python imports/storage_migrate.py upload --source tmp --prefix cache
python imports/storage_migrate.py usage
python imports/storage_migrate.py usage --prefix cache
```

Uploads are non-destructive and skip existing keys. Verify object counts before removing sources manually. The usage command counts logical bytes; physical MinIO usage can be larger because of filesystem overhead, versioning, erasure coding or replication.

On the NAS, this migration step turned out to be a no-op: `lenie-ai-data` (mounted at `/app/data`) held a single stray file (`ner_normalization.json`) — writes to it had actually been failing silently (`root:root drwx-----x` ownership vs. the container's uid 1000), so there was nothing real to move.

## Cache boundary

Source `.html/.txt` files are durable objects. Pipeline files under `CACHE_DIR` are a NAS-local worker scratch space because converters and LLM tools require paths. The temporary `legacy_aws_pull` bridge reads DynamoDB/S3 only to feed `DocumentIngestService`; it writes raw sources to MinIO and queues `document_prepare`. It never performs markdown conversion or LLM extraction itself. Other legacy pipelines must adopt the same materialize/process/sync lifecycle before desktop schedules can be retired.
