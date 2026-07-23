"""Storage abstraction for durable document files and processing cache.

The S3 implementation works with AWS S3, MinIO and other S3-compatible stores.
Local storage remains the zero-configuration default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol


class ObjectStorage(Protocol):
    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None: ...
    def get_bytes(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def iter_objects(self, prefix: str = ""): ...


def _safe_key(key: str) -> str:
    value = key.replace("\\", "/").lstrip("/")
    if not value or any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError(f"Invalid storage key: {key!r}")
    return value


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int


class LocalStorage:
    def __init__(self, root: str | os.PathLike):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / _safe_key(key)).resolve()
        if self.root not in path.parents:
            raise ValueError(f"Storage key escapes root: {key!r}")
        return path

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def iter_objects(self, prefix: str = ""):
        base = self.root / prefix if prefix else self.root
        if not base.exists():
            return
        for path in base.rglob("*"):
            if path.is_file():
                yield StoredObject(path.relative_to(self.root).as_posix(), path.stat().st_size)


class S3Storage:
    def __init__(self, bucket: str, endpoint_url: str | None = None, region: str | None = None,
                 access_key: str | None = None, secret_key: str | None = None, client=None):
        self.bucket = bucket
        if client is None:
            import boto3
            kwargs = {"endpoint_url": endpoint_url, "region_name": region}
            if access_key:
                kwargs["aws_access_key_id"] = access_key
            if secret_key:
                kwargs["aws_secret_access_key"] = secret_key
            client = boto3.client("s3", **{k: v for k, v in kwargs.items() if v})
        self.client = client

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None:
        kwargs = {"Bucket": self.bucket, "Key": _safe_key(key), "Body": data}
        if content_type:
            kwargs["ContentType"] = content_type
        self.client.put_object(**kwargs)

    def get_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=_safe_key(key))["Body"].read()

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError
        try:
            self.client.head_object(Bucket=self.bucket, Key=_safe_key(key))
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def iter_objects(self, prefix: str = ""):
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                yield StoredObject(item["Key"], item["Size"])


def storage_from_config(cfg, *, local_root: str = "/app/data") -> ObjectStorage:
    """Build storage. STORAGE_BACKEND defaults to local for desktop installs."""
    backend = (cfg.get("STORAGE_BACKEND") or "local").lower()
    if backend == "local":
        return LocalStorage(cfg.get("STORAGE_LOCAL_ROOT") or local_root)
    if backend not in ("s3", "minio"):
        raise ValueError(f"Unsupported STORAGE_BACKEND: {backend}")
    bucket = cfg.get("STORAGE_BUCKET") or cfg.get("AWS_S3_WEBSITE_CONTENT")
    if not bucket:
        raise ValueError("STORAGE_BUCKET is required for S3/MinIO storage")
    return S3Storage(
        bucket=bucket,
        endpoint_url=cfg.get("STORAGE_ENDPOINT_URL") or cfg.get("S3_ENDPOINT_URL"),
        region=cfg.get("STORAGE_REGION") or cfg.get("AWS_REGION"),
        access_key=cfg.get("STORAGE_ACCESS_KEY") or cfg.get("AWS_ACCESS_KEY_ID"),
        secret_key=cfg.get("STORAGE_SECRET_KEY") or cfg.get("AWS_SECRET_ACCESS_KEY"),
    )


def usage(storage: ObjectStorage, prefix: str = "") -> tuple[int, int]:
    count = total = 0
    for obj in storage.iter_objects(prefix):
        count += 1
        total += obj.size
    return count, total
