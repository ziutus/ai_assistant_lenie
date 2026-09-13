"""Shared contact photo thumbnail encoding for uploads and backfills."""

from io import BytesIO

from PIL import Image, ImageOps


def _photo_thumbnail_storage_key(contact_uuid: str, photo_storage_key: str | None = None) -> str:
    # A shared photo's thumbnail must remain stable when one contact replaces
    # its photo. Keep the one-argument convention for existing callers.
    if photo_storage_key:
        return f"{photo_storage_key}.thumb.jpg"
    return f"contacts/{contact_uuid}/photo_thumb.jpg"


def generate_photo_thumbnail(data: bytes) -> bytes:
    """Encode the first frame as an upright, aspect-preserving JPEG <= 256px.

    When a face can be detected (optional `imaging` extra, see
    `library/face_detection.py`), the source is first cropped to a square
    around the largest face — otherwise a tall full-body photo shrinks the
    face down to a speck instead of filling the thumbnail. Falls back to the
    plain whole-image thumbnail whenever no face is found, the extra isn't
    installed, or detection fails for any reason.
    """
    try:
        from library.face_detection import crop_around_largest_face
        face_crop = crop_around_largest_face(data)
    except Exception:
        face_crop = None
    if face_crop is not None:
        data = face_crop
    with Image.open(BytesIO(data)) as source:
        source.seek(0)
        image = ImageOps.exif_transpose(source)
        image.thumbnail((256, 256), Image.Resampling.LANCZOS)
        # Composite transparency onto white before dropping the alpha channel.
        rgba = image.convert("RGBA")
        rgb = Image.new("RGB", rgba.size, "white")
        rgb.paste(rgba, mask=rgba.getchannel("A"))
        output = BytesIO()
        rgb.save(output, format="JPEG", quality=85)
        return output.getvalue()
