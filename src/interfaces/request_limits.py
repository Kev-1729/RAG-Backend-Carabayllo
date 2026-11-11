import asyncio

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _BodyTooLargeError(Exception):
    pass


class RequestBodyLimit:
    def __init__(self, app: ASGIApp, max_bytes: int, timeout: float) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.timeout = timeout

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        try:
            body = await asyncio.wait_for(
                self._read_body(receive), timeout=self.timeout
            )
        except asyncio.TimeoutError:
            await JSONResponse(
                {"detail": "Tiempo agotado al recibir la solicitud."}, status_code=408
            )(scope, receive, send)
            return
        except _BodyTooLargeError:
            await JSONResponse(
                {"detail": "La solicitud excede el tamaño permitido."}, status_code=413
            )(scope, receive, send)
            return
        if body is None:
            return
        consumed = False

        async def replay() -> Message:
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    async def _read_body(self, receive: Receive) -> bytes | None:
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return None
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_bytes:
                raise _BodyTooLargeError()
            body.extend(chunk)
            if not message.get("more_body", False):
                return bytes(body)
