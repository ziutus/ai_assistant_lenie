from unittest.mock import MagicMock

from library.storage import LocalStorage, S3Storage, storage_from_config, usage


def test_local_roundtrip_and_usage(tmp_path):
    storage = LocalStorage(tmp_path)
    storage.put_bytes("cache/42/42.html", b"hello")
    assert storage.get_bytes("cache/42/42.html") == b"hello"
    assert storage.exists("cache/42/42.html")
    assert usage(storage, "cache") == (1, 5)


def test_s3_uses_endpoint_agnostic_api():
    client = MagicMock()
    client.get_object.return_value = {"Body": MagicMock(read=lambda: b"value")}
    storage = S3Storage("lenie", client=client)
    storage.put_bytes("documents/a.txt", b"value", "text/plain")
    assert storage.get_bytes("documents/a.txt") == b"value"
    client.put_object.assert_called_once_with(
        Bucket="lenie", Key="documents/a.txt", Body=b"value", ContentType="text/plain"
    )


def test_local_rejects_path_traversal(tmp_path):
    storage = LocalStorage(tmp_path)
    try:
        storage.put_bytes("../outside", b"bad")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_local_storage_has_no_presigned_url(tmp_path):
    storage = LocalStorage(tmp_path)
    assert storage.presigned_get_url("a") is None


def test_s3_presigned_uses_injected_client():
    client = MagicMock()
    client.generate_presigned_url.return_value = "https://signed.example/a/b.png"
    storage = S3Storage("lenie", client=client)
    url = storage.presigned_get_url("a/b.png", expires_in=900)
    assert url == "https://signed.example/a/b.png"
    client.generate_presigned_url.assert_called_once_with(
        "get_object", Params={"Bucket": "lenie", "Key": "a/b.png"}, ExpiresIn=900
    )


def test_s3_presign_uses_public_endpoint(monkeypatch):
    created_clients = []

    def fake_boto3_client(service, **kwargs):
        client = MagicMock()
        client.generate_presigned_url.return_value = f"https://{kwargs.get('endpoint_url')}/signed"
        created_clients.append(kwargs)
        return client

    fake_boto3 = MagicMock()
    fake_boto3.client.side_effect = fake_boto3_client
    monkeypatch.setitem(__import__("sys").modules, "boto3", fake_boto3)

    storage = S3Storage(
        "lenie",
        endpoint_url="http://lenie-minio:9000",
        public_endpoint_url="http://192.168.200.7:9000",
        client=MagicMock(),
    )
    url = storage.presigned_get_url("a.png")
    assert url == "https://http://192.168.200.7:9000/signed"
    assert created_clients == [{"endpoint_url": "http://192.168.200.7:9000"}]


def test_storage_from_config_passes_public_endpoint(monkeypatch):
    fake_boto3 = MagicMock()
    fake_boto3.client.return_value = MagicMock()
    monkeypatch.setitem(__import__("sys").modules, "boto3", fake_boto3)

    cfg = {
        "STORAGE_BACKEND": "minio",
        "STORAGE_BUCKET": "lenie-storage",
        "STORAGE_ENDPOINT_URL": "http://lenie-minio:9000",
        "STORAGE_PUBLIC_ENDPOINT_URL": "http://192.168.200.7:9000",
    }
    storage = storage_from_config(cfg)
    assert isinstance(storage, S3Storage)
    assert storage.public_endpoint_url == "http://192.168.200.7:9000"
