class LLMUnavailableError(Exception):
    """El proveedor no responde (caído, rate limit, red)."""


class ConversationNotFoundError(Exception):
    """La conversación solicitada no existe."""


class ConversationUnavailableError(Exception):
    """El almacenamiento de conversaciones no está disponible."""


class EmbeddingUnavailableError(Exception):
    """El servicio de embeddings no responde (caído, rate limit, red)."""


class RetrievalUnavailableError(Exception):
    """La búsqueda de fragmentos no está disponible (conexión o timeout)."""


class InvalidDocumentError(Exception):
    """El PDF no se pudo leer (dañado, protegido o sin texto)."""


class InvalidChunkingError(Exception):
    """El LLM no devolvió grupos de párrafos válidos."""
