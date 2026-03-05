"""MLX batch embedding generator with model fallback.

Generates GPU-accelerated embeddings on Apple Silicon using mlx-embeddings.
Primary model: ModernBERT (8192 token context, 768d).
Fallback model: MiniLM (512 token context, 384d).
"""

from __future__ import annotations

import logging

import mlx.core as mx
import numpy as np
from mlx_embeddings.utils import load

log = logging.getLogger(__name__)

PRIMARY_MODEL = "mlx-community/nomicai-modernbert-embed-base-4bit"
FALLBACK_MODEL = "mlx-community/all-MiniLM-L6-v2-4bit"
DOC_PREFIX = "search_document: "


def load_embedding_model() -> tuple:
    """Load embedding model with automatic fallback.

    Tries ModernBERT first; falls back to MiniLM on any failure.
    Returns (model, tokenizer, model_name) tuple.
    """
    try:
        model, tokenizer = load(PRIMARY_MODEL)
        log.info("Loaded primary model: %s", PRIMARY_MODEL)
        return model, tokenizer, PRIMARY_MODEL
    except Exception as exc:
        log.warning("Primary model failed (%s), falling back to MiniLM", exc)
        model, tokenizer = load(FALLBACK_MODEL)
        log.info("Loaded fallback model: %s", FALLBACK_MODEL)
        return model, tokenizer, FALLBACK_MODEL


def batch_embed(
    texts: list[str],
    model,
    tokenizer,
    model_name: str,
    batch_size: int = 64,
    max_length: int = 512,
    progress_callback: callable | None = None,
) -> np.ndarray:
    """Generate embeddings in GPU batches.

    Args:
        texts: Input texts to embed.
        model: MLX embedding model.
        tokenizer: MLX tokenizer.
        model_name: Model identifier -- prefix applied if "modernbert" in name.
        batch_size: Texts per GPU batch.
        max_length: Max token length for truncation.
        progress_callback: Called with batch_size after each batch completes.

    Returns:
        (N, dim) numpy array of L2-normalized embeddings.
    """
    prefix = DOC_PREFIX if "modernbert" in model_name.lower() else ""
    all_embeds: list[np.ndarray] = []

    # mlx-embeddings TokenizerWrapper doesn't expose batch_encode_plus;
    # use the inner HF tokenizer with numpy tensors, then convert to MLX
    inner_tokenizer = getattr(tokenizer, "_tokenizer", tokenizer)

    for i in range(0, len(texts), batch_size):
        batch = [prefix + t for t in texts[i : i + batch_size]]
        inputs = inner_tokenizer(
            batch,
            return_tensors="np",
            padding=True,
            truncation=True,
            max_length=max_length,
        )
        input_ids = mx.array(inputs["input_ids"])
        attention_mask = mx.array(inputs["attention_mask"])
        outputs = model(
            input_ids,
            attention_mask=attention_mask,
        )
        # mx.eval is MLX's GPU synchronization barrier (forces lazy compute)
        mx.eval(outputs.text_embeds)
        batch_np = np.array(outputs.text_embeds)
        all_embeds.append(batch_np)
        if progress_callback:
            progress_callback(len(batch))

    return np.vstack(all_embeds)
