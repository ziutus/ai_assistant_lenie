#!/usr/bin/env python3
"""Detect faces in an image and print bounding boxes as JSON. No DB access.

Used by the `/lenie-contact-photo-split` skill to get precise pixel
boundaries for splitting a multi-person contact photo, instead of eyeballing
crop coordinates. Requires the optional `imaging` dependency group:
`uv sync --extra imaging`.

Usage:
    python imports/detect_faces.py path/to/photo.png
    python imports/detect_faces.py path/to/photo.png --min-size 60
"""

import argparse
import json

from library.face_detection import detect_faces


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", help="Path to the image file")
    parser.add_argument("--min-size", type=int, default=40, help="Minimum face box side in pixels (default: 40)")
    args = parser.parse_args()
    with open(args.image, "rb") as fh:
        data = fh.read()
    faces = detect_faces(data, min_size=args.min_size)
    print(json.dumps({"count": len(faces), "faces": faces}, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
