"""Tests for the MLX batch embedding generator with model fallback."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# --- Mock infrastructure ---

@dataclass
class MockOutputs:
    """Simulates model output with text_embeds attribute."""
    text_embeds: np.ndarray


class MockTokenizer:
    """Simulates mlx_embeddings tokenizer with batch_encode_plus."""

    def batch_encode_plus(
        self,
        texts: list[str],
        *,
        return_tensors: str = "mlx",
        padding: bool = True,
        truncation: bool = True,
        max_length: int = 512,
    ) -> dict[str, np.ndarray]:
        seq_len = min(max_length, max(len(t.split()) for t in texts) if texts else 1)
        batch_size = len(texts)
        return {
            "input_ids": np.zeros((batch_size, seq_len), dtype=np.int32),
            "attention_mask": np.ones((batch_size, seq_len), dtype=np.int32),
        }


class MockModel:
    """Simulates mlx embedding model producing normalized embeddings."""

    def __init__(self, dim: int = 768):
        self.dim = dim
        self.call_count = 0
        self.last_input_ids = None

    def __call__(self, input_ids, attention_mask=None):
        self.call_count += 1
        self.last_input_ids = input_ids
        batch_size = input_ids.shape[0]
        rng = np.random.RandomState(42 + self.call_count)
        raw = rng.randn(batch_size, self.dim).astype(np.float32)
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        normalized = raw / norms
        return MockOutputs(text_embeds=normalized)


# --- Tests for load_embedding_model ---

class TestLoadEmbeddingModel:
    """Tests for model loading with fallback behavior."""

    @patch("icloud_cleanup.embedder.load")
    def test_loads_primary_model(self, mock_load):
        from icloud_cleanup.embedder import (
            PRIMARY_MODEL,
            load_embedding_model,
        )

        mock_model = MockModel()
        mock_tokenizer = MockTokenizer()
        mock_load.return_value = (mock_model, mock_tokenizer)

        model, tokenizer, model_name = load_embedding_model()

        mock_load.assert_called_once_with(PRIMARY_MODEL)
        assert model is mock_model
        assert tokenizer is mock_tokenizer
        assert model_name == PRIMARY_MODEL

    @patch("icloud_cleanup.embedder.load")
    def test_falls_back_to_minilm_on_primary_failure(self, mock_load):
        from icloud_cleanup.embedder import (
            FALLBACK_MODEL,
            load_embedding_model,
        )

        mock_model = MockModel()
        mock_tokenizer = MockTokenizer()
        mock_load.side_effect = [
            RuntimeError("ModernBERT not found"),
            (mock_model, mock_tokenizer),
        ]

        model, tokenizer, model_name = load_embedding_model()

        assert mock_load.call_count == 2
        assert model is mock_model
        assert tokenizer is mock_tokenizer
        assert model_name == FALLBACK_MODEL

    @patch("icloud_cleanup.embedder.load")
    def test_returns_tuple_of_three(self, mock_load):
        from icloud_cleanup.embedder import load_embedding_model

        mock_load.return_value = (MockModel(), MockTokenizer())
        result = load_embedding_model()
        assert isinstance(result, tuple)
        assert len(result) == 3


# --- Tests for batch_embed ---

class TestBatchEmbed:
    """Tests for batch embedding generation."""

    def test_returns_correct_shape(self):
        from icloud_cleanup.embedder import batch_embed

        model = MockModel(dim=768)
        tokenizer = MockTokenizer()
        texts = ["hello world", "test email", "another text"]

        with patch("icloud_cleanup.embedder.mx") as mock_mx:
            mock_mx.eval = MagicMock()
            result = batch_embed(texts, model, tokenizer, "some-model")

        assert isinstance(result, np.ndarray)
        assert result.shape == (3, 768)

    def test_applies_prefix_for_modernbert(self):
        from icloud_cleanup.embedder import DOC_PREFIX, batch_embed

        model = MockModel(dim=768)
        tokenizer = MockTokenizer()
        tokenizer.batch_encode_plus = MagicMock(wraps=tokenizer.batch_encode_plus)
        texts = ["hello", "world"]

        with patch("icloud_cleanup.embedder.mx") as mock_mx:
            mock_mx.eval = MagicMock()
            batch_embed(texts, model, tokenizer, "modernbert-embed-base")

        call_args = tokenizer.batch_encode_plus.call_args[0][0]
        for text in call_args:
            assert text.startswith(DOC_PREFIX)

    def test_no_prefix_for_non_modernbert(self):
        from icloud_cleanup.embedder import DOC_PREFIX, batch_embed

        model = MockModel(dim=768)
        tokenizer = MockTokenizer()
        tokenizer.batch_encode_plus = MagicMock(wraps=tokenizer.batch_encode_plus)
        texts = ["hello", "world"]

        with patch("icloud_cleanup.embedder.mx") as mock_mx:
            mock_mx.eval = MagicMock()
            batch_embed(texts, model, tokenizer, "all-MiniLM-L6-v2")

        call_args = tokenizer.batch_encode_plus.call_args[0][0]
        for text in call_args:
            assert not text.startswith(DOC_PREFIX)

    def test_handles_empty_strings(self):
        from icloud_cleanup.embedder import batch_embed

        model = MockModel(dim=768)
        tokenizer = MockTokenizer()
        texts = ["", "", ""]

        with patch("icloud_cleanup.embedder.mx") as mock_mx:
            mock_mx.eval = MagicMock()
            result = batch_embed(texts, model, tokenizer, "some-model")

        assert result.shape == (3, 768)

    def test_batches_correctly_when_not_divisible(self):
        from icloud_cleanup.embedder import batch_embed

        model = MockModel(dim=768)
        tokenizer = MockTokenizer()
        texts = [f"text {i}" for i in range(7)]

        with patch("icloud_cleanup.embedder.mx") as mock_mx:
            mock_mx.eval = MagicMock()
            result = batch_embed(
                texts, model, tokenizer, "some-model", batch_size=3,
            )

        # 7 texts with batch_size=3 = 3 batches (3 + 3 + 1)
        assert model.call_count == 3
        assert result.shape == (7, 768)

    def test_output_embeddings_are_normalized(self):
        from icloud_cleanup.embedder import batch_embed

        model = MockModel(dim=768)
        tokenizer = MockTokenizer()
        texts = ["hello", "world", "test"]

        with patch("icloud_cleanup.embedder.mx") as mock_mx:
            mock_mx.eval = MagicMock()
            result = batch_embed(texts, model, tokenizer, "some-model")

        norms = np.linalg.norm(result, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5)

    def test_single_text_works(self):
        from icloud_cleanup.embedder import batch_embed

        model = MockModel(dim=768)
        tokenizer = MockTokenizer()

        with patch("icloud_cleanup.embedder.mx") as mock_mx:
            mock_mx.eval = MagicMock()
            result = batch_embed(
                ["just one"], model, tokenizer, "some-model",
            )

        assert result.shape == (1, 768)

    def test_prefix_case_insensitive_check(self):
        """modernbert match should be case-insensitive."""
        from icloud_cleanup.embedder import DOC_PREFIX, batch_embed

        model = MockModel(dim=768)
        tokenizer = MockTokenizer()
        tokenizer.batch_encode_plus = MagicMock(wraps=tokenizer.batch_encode_plus)
        texts = ["hello"]

        with patch("icloud_cleanup.embedder.mx") as mock_mx:
            mock_mx.eval = MagicMock()
            batch_embed(texts, model, tokenizer, "ModernBERT-Embed-Base")

        call_args = tokenizer.batch_encode_plus.call_args[0][0]
        assert call_args[0].startswith(DOC_PREFIX)
