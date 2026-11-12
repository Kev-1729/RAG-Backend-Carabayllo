class LLMUnavailableError(Exception):
    """El proveedor no responde (caído, rate limit, red)."""


class InvalidConversationTokenError(Exception):
    """El token de acceso a la conversación es inválido."""


class RequestLimitUnavailableError(Exception):
    """El almacenamiento de límites de solicitudes no está disponible."""


class ConversationNotFoundError(Exception):
    """La conversación solicitada no existe."""


class ConversationUnavailableError(Exception):
    """El almacenamiento de conversaciones no está disponible."""


class MessageNotFoundError(Exception):
    """El mensaje solicitado no existe."""


class InvalidRatingError(Exception):
    """Las estrellas o el tipo de mensaje no permiten la calificación."""


class RatingAlreadyExistsError(Exception):
    """El mensaje ya tiene una calificación."""


class RatingUnavailableError(Exception):
    """El almacenamiento de calificaciones no está disponible."""


class EmbeddingUnavailableError(Exception):
    """El servicio de embeddings no responde (caído, rate limit, red)."""


class RetrievalUnavailableError(Exception):
    """La búsqueda de fragmentos no está disponible (conexión o timeout)."""


class InvalidDocumentError(Exception):
    """El PDF no se pudo leer (dañado, protegido o sin texto)."""


class InvalidChunkingError(Exception):
    """El LLM no devolvió grupos de párrafos válidos."""


class DocumentReplacementError(Exception):
    """El documento solicitado no permite este reemplazo."""
