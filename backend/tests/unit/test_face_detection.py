"""cv2 is an optional dependency (`uv sync --extra imaging`) and is lazily
imported inside the function under test, so these tests fake it via
sys.modules rather than requiring it to be installed — same convention as
test_article_pipeline.py's library.document_prepare faking."""

import sys
import types
from unittest.mock import MagicMock

import numpy as np
import pytest

from library.face_detection import detect_faces


def fake_cv2(*, imdecode_result, detected_faces=()):
    module = types.SimpleNamespace()
    module.imdecode = MagicMock(return_value=imdecode_result)
    module.IMREAD_GRAYSCALE = 0
    module.data = types.SimpleNamespace(haarcascades="/fake/haarcascades/")
    cascade = MagicMock()
    cascade.detectMultiScale = MagicMock(return_value=np.array(detected_faces, dtype=int)
                                          if detected_faces else np.empty((0, 4), dtype=int))
    module.CascadeClassifier = MagicMock(return_value=cascade)
    return module, cascade


def test_returns_empty_list_when_image_cannot_be_decoded(monkeypatch):
    module, _ = fake_cv2(imdecode_result=None)
    monkeypatch.setitem(sys.modules, "cv2", module)
    assert detect_faces(b"not an image") == []


def test_returns_empty_list_when_no_faces_found(monkeypatch):
    module, _ = fake_cv2(imdecode_result=np.zeros((100, 100), dtype=np.uint8))
    monkeypatch.setitem(sys.modules, "cv2", module)
    assert detect_faces(b"fake-bytes") == []


def test_sorts_faces_left_to_right_and_returns_plain_ints(monkeypatch):
    module, _ = fake_cv2(
        imdecode_result=np.zeros((200, 400), dtype=np.uint8),
        detected_faces=[(300, 10, 50, 60), (20, 15, 55, 65)],
    )
    monkeypatch.setitem(sys.modules, "cv2", module)
    faces = detect_faces(b"fake-bytes")
    assert faces == [
        {"x": 20, "y": 15, "w": 55, "h": 65},
        {"x": 300, "y": 10, "w": 50, "h": 60},
    ]
    assert all(isinstance(v, int) for face in faces for v in face.values())


@pytest.mark.parametrize("min_size", [20, 80])
def test_min_size_is_forwarded_to_detect_multi_scale(monkeypatch, min_size):
    module, cascade = fake_cv2(imdecode_result=np.zeros((10, 10), dtype=np.uint8))
    monkeypatch.setitem(sys.modules, "cv2", module)
    detect_faces(b"fake-bytes", min_size=min_size)
    assert cascade.detectMultiScale.call_args.kwargs["minSize"] == (min_size, min_size)
