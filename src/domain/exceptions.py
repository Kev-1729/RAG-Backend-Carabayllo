class LLMUnavailableError(Exception):
    """El proveedor no responde (caído, rate limit, red)."""


class EmbeddingUnavailableError(Exception):
    """El servicio de embeddings no responde (caído, rate limit, red)."""


class InvalidDocumentError(Exception):
    """El PDF no se pudo leer (dañado, protegido o sin texto)."""


class InvalidChunkingError(Exception):
    """El LLM no devolvió grupos de párrafos válidos."""
