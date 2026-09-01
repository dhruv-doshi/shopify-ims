import asyncio

import pytest

from src.bot.batching import PendingPhoto, PhotoBatcher


@pytest.mark.asyncio
async def test_photo_batcher_flushes_after_idle():
    flushed: list[tuple[int, int, int]] = []

    async def on_flush(user_id: int, chat_id: int, photos: list[PendingPhoto]) -> None:
        flushed.append((user_id, chat_id, len(photos)))

    batcher = PhotoBatcher(on_flush=on_flush, idle_seconds=0.05)
    batcher.add(1, 10, PendingPhoto(bytes=b"a", mime="image/jpeg", filename="a.jpg"))
    batcher.add(1, 10, PendingPhoto(bytes=b"b", mime="image/jpeg", filename="b.jpg"))
    await asyncio.sleep(0.1)
    assert flushed == [(10, 1, 2)]
