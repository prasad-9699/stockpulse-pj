"""
stream.py — SSE endpoints for the Agent Activity Feed.

GET /events/stream provides a live Server-Sent Events stream that the
frontend renders as the "Agent Activity" panel. Each connected client
gets its own asyncio.Queue from the event bus.
"""

import asyncio
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app import event_bus

router = APIRouter(tags=["Events"])


@router.get("/events/stream")
async def event_stream():
    """
    SSE endpoint for the Agent Activity Feed.
    Streams events from the agentic loop in real-time so judges can watch
    the reactive loop detect, reason, and act on inventory signals live.
    Each client gets its own queue; disconnection cleans up automatically.
    """
    queue = event_bus.subscribe()

    async def generate():
        """Generator that yields SSE-formatted events from the client's queue."""
        try:
            while True:
                try:
                    # Wait up to 30s for an event, then send a keepalive comment
                    data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive comment to prevent connection timeout
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering if behind a proxy
        },
    )
