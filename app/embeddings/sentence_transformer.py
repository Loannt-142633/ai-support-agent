"""Local sentence-transformers adapter, loaded only when first used."""

import asyncio
import importlib
from threading import Lock
from typing import Protocol, cast

from app.embeddings.client import EmbeddingError, EmbeddingInputType


class _EncodedVectors(Protocol):
    def tolist(self) -> list[list[float]]: ...


class _Encoder(Protocol):
    def encode(
        self,
        sentences: list[str],
        *,
        batch_size: int,
        normalize_embeddings: bool,
        convert_to_numpy: bool,
        show_progress_bar: bool,
    ) -> _EncodedVectors: ...


class SentenceTransformerEmbeddingClient:
    """Apply E5 query/passage prefixes and run local inference off the event loop."""

    _prefixes = {
        EmbeddingInputType.QUERY: "query: ",
        EmbeddingInputType.DOCUMENT: "passage: ",
    }

    def __init__(self, model_name: str, *, batch_size: int = 32) -> None:
        if not model_name.strip() or batch_size <= 0:
            raise ValueError("model_name must be nonempty and batch_size must be positive")
        self._model_name = model_name
        self._batch_size = batch_size
        self._model: _Encoder | None = None
        self._lock = Lock()

    async def embed(
        self, texts: list[str], *, input_type: EmbeddingInputType
    ) -> list[list[float]]:
        """Encode queries or documents using the corresponding E5 prefix."""

        if not texts:
            return []
        try:
            prefix = self._prefixes[input_type]
            return await asyncio.to_thread(self._embed_sync, texts, prefix)
        except KeyError as error:
            raise ValueError("Unsupported embedding input type") from error
        except EmbeddingError:
            raise
        except Exception as error:
            raise EmbeddingError("Could not generate semantic embeddings") from error

    def _embed_sync(self, texts: list[str], prefix: str) -> list[list[float]]:
        with self._lock:
            if self._model is None:
                try:
                    module = importlib.import_module("sentence_transformers")
                except ImportError as error:
                    raise EmbeddingError(
                        'Install semantic chunking dependencies with: pip install -e ".[semantic]"'
                    ) from error
                self._model = cast(_Encoder, module.SentenceTransformer(self._model_name))
            vectors = self._model.encode(
                [prefix + text for text in texts],
                batch_size=self._batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            return vectors.tolist()
