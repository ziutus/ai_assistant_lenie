from unittest.mock import MagicMock

from library.storage import LocalStorage, S3Storage, usage


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
