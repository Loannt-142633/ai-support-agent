import asyncio
from unittest.mock import MagicMock, patch

import pytest
from app.embeddings.client import EmbeddingError, EmbeddingInputType
from app.embeddings.sentence_transformer import SentenceTransformerEmbeddingClient


def test_adapter_reuses_model_and_maps_query_and_document_prefixes() -> None:
    module = MagicMock()
    model = module.SentenceTransformer.return_value
    model.encode.return_value.tolist.return_value = [[1.0, 0.0]]
    client = SentenceTransformerEmbeddingClient("test-model")

    with patch("app.embeddings.sentence_transformer.importlib.import_module", return_value=module):
        assert asyncio.run(client.embed(["Refunds."], input_type=EmbeddingInputType.QUERY)) == [
            [1.0, 0.0]
        ]
        asyncio.run(client.embed(["Shipping."], input_type=EmbeddingInputType.DOCUMENT))

    module.SentenceTransformer.assert_called_once_with("test-model")
    assert model.encode.call_args_list[0].args == (["query: Refunds."],)
    assert model.encode.call_args_list[1].args == (["passage: Shipping."],)
    assert model.encode.call_args.kwargs["normalize_embeddings"] is True


def test_adapter_reports_missing_optional_dependency() -> None:
    with (
        patch(
            "app.embeddings.sentence_transformer.importlib.import_module", side_effect=ImportError
        ),
        pytest.raises(EmbeddingError, match="semantic"),
    ):
        asyncio.run(
            SentenceTransformerEmbeddingClient("test-model").embed(
                ["Hello."], input_type=EmbeddingInputType.QUERY
            )
        )
