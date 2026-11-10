import asyncio
from collections.abc import AsyncGenerator

from fastapi.responses import StreamingResponse
from starlette.requests import ClientDisconnect
from starlette.types import Message, Receive, Scope, Send


class EventStreamResponse(StreamingResponse):
    media_type = "text/event-stream"

    def __init__(self, events: AsyncGenerator[bytes, None]) -> None:
        super().__init__(
            events,
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
        self._events = events

    async def stream_response(self, send: Send) -> None:
        # Espera el primer evento para conservar los errores HTTP del caso de uso.
        first = await anext(self._events)
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self.raw_headers,
            }
        )
        await send({"type": "http.response.body", "body": first, "more_body": True})
        async for event in self._events:
            await send({"type": "http.response.body", "body": event, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_event(message: Message) -> None:
            try:
                await send(message)
            except OSError as error:
                raise ClientDisconnect() from error

        streaming = asyncio.create_task(self.stream_response(send_event))
        disconnect = asyncio.create_task(self.listen_for_disconnect(receive))
        try:
            done, _ = await asyncio.wait(
                (streaming, disconnect), return_when=asyncio.FIRST_COMPLETED
            )
            if streaming in done:
                try:
                    streaming.result()
                except ClientDisconnect:
                    return
            if disconnect in done:
                disconnect.result()
        finally:
            streaming.cancel()
            disconnect.cancel()
            await asyncio.gather(streaming, disconnect, return_exceptions=True)
            await self._events.aclose()
