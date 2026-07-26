"""
Google Gemini embedding provider.

Uses the Gemini text-embedding-004 model via the google-genai SDK.
Outputs 768-dim vectors (matches Synapse default schema).

Setup:
    pip install synapse-mcp[gemini]
    export GEMINI_API_KEY=your_key_here

    Get a free API key at: https://aistudio.google.com/app/apikey
    (Free tier: 1,500 requests/day — more than enough for personal use.)

Config (~/.synapse/config.toml):
    [embedding]
    provider = "gemini"
    model = "text-embedding-004"   # default, recommended
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Union

EMBEDDING_DIM = 768
_DEFAULT_MODEL = "text-embedding-004"
_TASK_TYPE_DOC = "RETRIEVAL_DOCUMENT"
_TASK_TYPE_QUERY = "RETRIEVAL_QUERY"


@lru_cache(maxsize=1)
def _get_client():
    try:
        import google.genai as genai
    except ImportError:
        raise ImportError(
            "google-genai is required for Gemini embeddings.\n"
            "Install with: pip install synapse-mcp[gemini]\n"
            "Or manually: pip install google-genai"
        )

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY environment variable is not set.\n"
            "Get a free key at: https://aistudio.google.com/app/apikey\n"
            "Then: export GEMINI_API_KEY=your_key"
        )
    return genai.Client(api_key=api_key)


def _get_model() -> str:
    from synapse.config import get_embedding_config
    cfg = get_embedding_config()
    return cfg.get("model", _DEFAULT_MODEL)


def encode(text: Union[str, list[str]]) -> list[list[float]]:
    """
    Encode one or more texts via the Gemini Embeddings API.

    Uses RETRIEVAL_DOCUMENT task type for accurate code/document retrieval.
    Outputs 768-dim vectors to match Synapse's local embedding schema.

    Args:
        text: A single string or list of strings.

    Returns:
        List of float lists, one per input text.
    """
    client = _get_client()
    model = _get_model()
    texts = [text] if isinstance(text, str) else text

    result = client.models.embed_content(
        model=model,
        contents=texts,
        config={
            "task_type": _TASK_TYPE_DOC,
            "output_dimensionality": EMBEDDING_DIM,
        },
    )
    return [list(emb.values) for emb in result.embeddings]


def encode_query(query: str) -> list[float]:
    """
    Encode a search query with RETRIEVAL_QUERY task type.
    Gemini uses distinct task types for queries vs documents for better accuracy.
    Returns a single embedding vector.
    """
    client = _get_client()
    model = _get_model()

    result = client.models.embed_content(
        model=model,
        contents=[query],
        config={
            "task_type": _TASK_TYPE_QUERY,
            "output_dimensionality": EMBEDDING_DIM,
        },
    )
    return list(result.embeddings[0].values)


def embedding_dim() -> int:
    return EMBEDDING_DIM
