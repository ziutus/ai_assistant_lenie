"""Local face-bounding-box detection (OpenCV Haar cascade) — no cloud/API
calls, no DB access. Used to pick precise crop boundaries when splitting a
multi-person contact photo (see `.claude/commands/lenie-contact-photo-split.md`).

Optional dependency — install with `uv sync --extra imaging`. Not part of
the deployed backend image or any REST endpoint: this is a local-dev-machine
helper for the photo-split skill, not a production feature.
"""

from io import BytesIO

import numpy as np
from PIL import Image, ImageOps


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


def crop_around_largest_face(image_bytes: bytes, padding: float = 1.6) -> bytes | None:
    """Return a square PNG crop centered on the largest detected face, sized
    to `padding` times the face's longest side (clamped to image bounds).

    None if no face is found, the image can't be decoded/opened, or the
    optional cv2 dependency isn't installed — callers should fall back to
    their own default framing in that case. Detection runs on the same
    EXIF-upright bytes the crop is taken from, so face coordinates and crop
    coordinates always agree on orientation.
    """
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except Exception:
        return None
    upright = BytesIO()
    image.save(upright, format="PNG")
    try:
        faces = detect_faces(upright.getvalue())
    except ImportError:
        return None
    if not faces:
        return None
    largest = max(faces, key=lambda face: face["w"] * face["h"])
    img_w, img_h = image.size
    center_x = largest["x"] + largest["w"] / 2
    center_y = largest["y"] + largest["h"] / 2
    side = min(max(largest["w"], largest["h"]) * padding, img_w, img_h)
    x0 = max(0, min(img_w - side, center_x - side / 2))
    y0 = max(0, min(img_h - side, center_y - side / 2))
    box = (int(x0), int(y0), int(x0 + side), int(y0 + side))
    output = BytesIO()
    image.crop(box).save(output, format="PNG")
    return output.getvalue()
