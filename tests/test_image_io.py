import base64

from src.core.image_io import decode_image_b64, image_extension, is_valid_image, write_image


def test_decode_strips_data_url_prefix():
    raw = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 20).decode()
    wrapped = f"data:image/png;base64,{raw}"
    assert decode_image_b64(wrapped).startswith(b"\x89PNG")


def test_valid_png(tmp_path):
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    assert is_valid_image(png)
    path = write_image(tmp_path / "out.jpg", png)
    assert path.suffix == ".png"
    assert path.read_bytes() == png
