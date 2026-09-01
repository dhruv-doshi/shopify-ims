import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from src.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class PendingPhoto:
    bytes: bytes
    mime: str
    filename: str


@dataclass
class ChatBuffer:
    photos: list[PendingPhoto] = field(default_factory=list)
    user_id: int = 0
    chat_id: int = 0
    task: asyncio.Task | None = None


class PhotoBatcher:
    def __init__(
        self,
        on_flush: Callable[[int, int, list[PendingPhoto]], Awaitable[None]],
        idle_seconds: int | None = None,
    ):
        self._on_flush = on_flush
        self._idle_seconds = idle_seconds or get_settings().photo_batch_idle_seconds
        self._buffers: dict[int, ChatBuffer] = {}

    def add(self, chat_id: int, user_id: int, photo: PendingPhoto) -> None:
        buf = self._buffers.get(chat_id)
        if buf is None:
            buf = ChatBuffer(user_id=user_id, chat_id=chat_id)
            self._buffers[chat_id] = buf
        buf.user_id = user_id
        buf.chat_id = chat_id
        buf.photos.append(photo)
        if buf.task and not buf.task.done():
            buf.task.cancel()
        buf.task = asyncio.create_task(self._schedule_flush(chat_id))

    async def _schedule_flush(self, chat_id: int) -> None:
        try:
            await asyncio.sleep(self._idle_seconds)
            await self.flush(chat_id)
        except asyncio.CancelledError:
            return

    async def flush(self, chat_id: int) -> None:
        buf = self._buffers.pop(chat_id, None)
        if buf is None or not buf.photos:
            return
        photos = list(buf.photos)
        await self._on_flush(buf.user_id, buf.chat_id, photos)

    async def flush_all(self) -> None:
        for chat_id in list(self._buffers.keys()):
            await self.flush(chat_id)
