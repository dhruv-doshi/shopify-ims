import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
WEBP_MAGIC = b"RIFF"


def decode_image_b64(b64_data: str) -> bytes:
    value = b64_data.strip()
    if value.startswith("data:"):
        value = value.split(",", 1)[1]
    return base64.b64decode(value)


def image_extension(data: bytes) -> str:
    if data.startswith(PNG_MAGIC):
        return ".png"
    if data.startswith(JPEG_MAGIC):
        return ".jpg"
    if data.startswith(WEBP_MAGIC) and data[8:12] == b"WEBP":
        return ".webp"
    return ".bin"


def is_valid_image(data: bytes) -> bool:
    if len(data) < 12:
        return False
    ext = image_extension(data)
    return ext in {".png", ".jpg", ".webp"}


def write_image(path: Path, data: bytes) -> Path:
    if not is_valid_image(data):
        raise ValueError(f"Invalid image bytes for {path}")
    ext = image_extension(data)
    if path.suffix.lower() != ext:
        path = path.with_suffix(ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path
