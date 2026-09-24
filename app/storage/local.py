"""Local filesystem document storage."""

import asyncio
from pathlib import Path
from uuid import uuid4


class LocalDocumentStorage:
    """Persist uploaded documents below a configured local directory."""

    def __init__(self, root: Path) -> None:
        self._root = root

    async def save(self, *, filename: str, content: bytes) -> str:
        """Store content under a collision-resistant name and return its path."""

        suffix = Path(filename).suffix.lower()
        destination = self._root / f"{uuid4().hex}{suffix}"
        await asyncio.to_thread(self._write, destination, content)
        return str(destination)

    async def delete(self, storage_path: str) -> None:
        """Remove a previously stored document if it exists."""

        await asyncio.to_thread(Path(storage_path).unlink, missing_ok=True)

    @staticmethod
    def _write(destination: Path, content: bytes) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
