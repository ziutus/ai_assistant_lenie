"""Local face-bounding-box detection (OpenCV Haar cascade) — no cloud/API
calls, no DB access. Used to pick precise crop boundaries when splitting a
multi-person contact photo (see `.claude/commands/lenie-contact-photo-split.md`).

Optional dependency — install with `uv sync --extra imaging`. Not part of
the deployed backend image or any REST endpoint: this is a local-dev-machine
helper for the photo-split skill, not a production feature.
"""

import numpy as np


def detect_faces(image_bytes: bytes, min_size: int = 40) -> list[dict]:
    """Return detected face bounding boxes as [{"x", "y", "w", "h"}, ...],
    sorted left-to-right by x. Empty list if none found or the image can't
    be decoded."""
    import cv2

    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_GRAYSCALE)
    if image is None:
        return []
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = cascade.detectMultiScale(image, scaleFactor=1.1, minNeighbors=5, minSize=(min_size, min_size))
    boxes = [{"x": int(x), "y": int(y), "w": int(w), "h": int(h)} for x, y, w, h in faces]
    boxes.sort(key=lambda box: box["x"])
    return boxes
