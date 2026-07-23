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
STORAGE_BUCKET=lenie-storage
STORAGE_ACCESS_KEY=lenie-admin
STORAGE_SECRET_KEY=change-me
STORAGE_REGION=us-east-1
```

AWS S3 uses `STORAGE_BACKEND=s3`, omits `STORAGE_ENDPOINT_URL`, and can use the normal AWS credential chain. Google Cloud Storage is not S3 API compatible by default; use its interoperability/HMAC endpoint or add a native adapter later.

`STORAGE_BACKEND` is explicit. The legacy `AWS_S3_WEBSITE_CONTENT` is accepted as a bucket-name fallback, but no longer selects cloud storage by itself.

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

## Cache boundary

Source `.html/.txt` files are durable objects. Pipeline files under `CACHE_DIR` are a NAS-local worker scratch space because converters and LLM tools require paths. `dynamodb_sync.py` mirrors its cache to `cache/markdown/` in MinIO/S3 after processing. Other legacy pipelines must adopt the same materialize/process/sync lifecycle before desktop schedules can be retired.
