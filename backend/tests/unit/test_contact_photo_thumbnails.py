from io import BytesIO
from unittest.mock import MagicMock

import pytest
from PIL import Image

from library.contact_photo_thumbnails import generate_photo_thumbnail


def image_bytes(mode="RGB", size=(800, 400), format="PNG", **kwargs):
    output = BytesIO()
    Image.new(mode, size).save(output, format=format, **kwargs)
    return output.getvalue()


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "P", "L"])
def test_thumbnail_is_rgb_jpeg_and_fits(mode):
    with Image.open(BytesIO(generate_photo_thumbnail(image_bytes(mode)))) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
        assert image.size == (256, 128)


def test_exif_orientation_and_no_upscaling():
    exif = Image.Exif()
    exif[274] = 6
    data = image_bytes(size=(80, 40), format="JPEG", exif=exif)
    with Image.open(BytesIO(generate_photo_thumbnail(data))) as image:
        assert image.size == (40, 80)
        assert image.getexif().get(274) is None


def test_animated_gif_uses_first_frame():
    output = BytesIO()
    Image.new("RGB", (400, 200), "red").save(
        output, format="GIF", save_all=True, append_images=[Image.new("RGB", (400, 200), "blue")],
    )
    with Image.open(BytesIO(generate_photo_thumbnail(output.getvalue()))) as image:
        r, g, b = image.getpixel((0, 0))
        assert r > 240 and g < 10 and b < 10
        assert image.size == (256, 128)


def test_corrupt_image_raises():
    with pytest.raises(Exception):
        generate_photo_thumbnail(b"broken")


@pytest.mark.parametrize("apply", [False, True])
def test_backfill_continues_after_bad_original_and_only_writes_on_apply(apply):
    from types import SimpleNamespace
    from imports.contact_photo_thumbnails_backfill import backfill

    session = MagicMock()
    session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [(1,), (2,)]
    contacts = {id_: SimpleNamespace(uuid=str(id_), photo_storage_key=f"{id_}.png",
                                    photo_thumbnail_storage_key=None) for id_ in (1, 2)}
    session.get.side_effect = lambda model, id_: contacts[id_]
    storage = MagicMock()
    storage.get_bytes.side_effect = [b"broken", image_bytes()]
    assert backfill(session, storage, apply=apply) == (1, 1)
    session.rollback.assert_called_once()
    assert storage.put_bytes.call_count == int(apply)
    assert session.commit.call_count == int(apply)
    assert contacts[2].photo_thumbnail_storage_key == ("contacts/2/photo_thumb.jpg" if apply else None)
