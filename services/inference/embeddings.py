"""Embedding model wrapper.

Isolates the `fastembed` dependency behind a project-owned interface —
callers never import `fastembed` directly, so swapping the embedding backend
later (a different model, an API-based embedder) touches only this module.

fastembed (ONNX Runtime) over sentence-transformers/torch deliberately: the
optional inference service must fit on a small CPU-only host, while torch's
Linux wheel pulls a large CUDA dependency chain regardless of index.
"""

from functools import lru_cache

from fastembed import TextEmbedding

from services.inference.config import settings


@lru_cache(maxsize=1)
def _get_model() -> TextEmbedding:
    return TextEmbedding(model_name=settings.embedding_model_name)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Encode a batch of texts into embedding vectors.

    Synchronous/CPU-bound — callers running in an async context must offload
    this to a thread pool (see `services.inference.search`).
    """
    if not texts:
        return []
    model = _get_model()
    return [vector.tolist() for vector in model.embed(texts)]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
