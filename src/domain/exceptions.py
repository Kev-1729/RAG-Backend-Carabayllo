class LLMUnavailableError(Exception):
    """El proveedor no responde (caído, rate limit, red)."""
