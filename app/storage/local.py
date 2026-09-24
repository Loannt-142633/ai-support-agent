"""Local filesystem document storage."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4


class LocalDocumentStorage:
    """Persist uploaded documents below a configured local directory."""

    def __init__(self, root: Path) -> None:
        self._root = root

    async def save(self, *, filename: str, chunks: AsyncIterator[bytes]) -> str:
        """Store content under a collision-resistant name and return its path."""

        suffix = Path(filename).suffix.lower()
        destination = self._root / f"{uuid4().hex}{suffix}"
        file_handle: BinaryIO | None = None
        try:
            await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)
            file_handle = await asyncio.to_thread(destination.open, "wb")
            async for chunk in chunks:
                await asyncio.to_thread(file_handle.write, chunk)
            return str(destination)
        except Exception:
            if file_handle is not None:
                await asyncio.to_thread(file_handle.close)
                file_handle = None
            await asyncio.to_thread(destination.unlink, missing_ok=True)
            raise
        finally:
            if file_handle is not None:
                await asyncio.to_thread(file_handle.close)

    async def delete(self, storage_path: str) -> None:
        """Remove a previously stored document if it exists."""

        await asyncio.to_thread(Path(storage_path).unlink, missing_ok=True)
