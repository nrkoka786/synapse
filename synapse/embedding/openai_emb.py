"""
OpenAI embedding provider (optional alternative to local).
Requires: OPENAI_API_KEY environment variable.
Model: text-embedding-3-small (1536-dim, but we truncate to 768 to match local)
Cost: ~$0.02 per 1M tokens — negligible for personal use.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Union

EMBEDDING_DIM = 768
_MODEL_NAME = "text-embedding-3-small"


@lru_cache(maxsize=1)
def _get_client():
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai package required: pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY environment variable is not set.\n"
            "Set it or switch embedding provider to 'local' in your config."
        )
    return OpenAI(api_key=api_key)


def encode(text: Union[str, list[str]]) -> list[list[float]]:
    """
    Encode one or more texts via the OpenAI Embeddings API.
    Returns list of float lists, each of length EMBEDDING_DIM (768).
    """
    client = _get_client()
    single = isinstance(text, str)
    texts = [text] if single else text

    response = client.embeddings.create(
        model=_MODEL_NAME,
        input=texts,
        dimensions=EMBEDDING_DIM,  # text-embedding-3-small supports dimension reduction
    )
    return [item.embedding for item in response.data]


def encode_query(query: str) -> list[float]:
    """Encode a search query. Returns a single embedding vector."""
    result = encode(query)
    return result[0]


def embedding_dim() -> int:
    return EMBEDDING_DIM
