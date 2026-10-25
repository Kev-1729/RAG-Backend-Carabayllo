def split_text(text: str, size: int, overlap: int) -> list[str]:
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("size must be positive and overlap must be in [0, size)")

    text = " ".join(text.split())
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            # Termina en el último espacio para no cortar una palabra.
            space = text.rfind(" ", start, end + 1)
            if space > start:
                end = space
        chunks.append(text[start:end])
        if end == len(text):
            break
        # Retrocede `overlap` caracteres y avanza hasta el inicio de una palabra.
        next_start = max(end - overlap, start + 1)
        space = text.find(" ", next_start - 1, end + 1)
        start = space + 1 if space != -1 else next_start
    return chunks
