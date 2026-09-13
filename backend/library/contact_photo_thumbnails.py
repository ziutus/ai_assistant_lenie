"""Shared contact photo thumbnail encoding for uploads and backfills."""

from io import BytesIO

from PIL import Image, ImageOps


def _photo_thumbnail_storage_key(contact_uuid: str) -> str:
    return f"contacts/{contact_uuid}/photo_thumb.jpg"


def generate_photo_thumbnail(data: bytes) -> bytes:
    """Encode the first frame as an upright, aspect-preserving JPEG <= 256px."""
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
