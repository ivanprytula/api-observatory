"""Embedding model wrapper.

Isolates the `fastembed` dependency behind a project-owned interface —
callers never import `fastembed` directly, so swapping the embedding backend
later (a different model, an API-based embedder) touches only this module.

fastembed (ONNX Runtime) over sentence-transformers/torch deliberately: this
service targets a free-tier Azure VM, and torch's Linux wheel pulls a full
CUDA dependency chain (~2GB) unconditionally, regardless of index — wildly
disproportionate for CPU-only embedding inference on a 1GB-RAM box.
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
