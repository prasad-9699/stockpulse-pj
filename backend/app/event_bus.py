"""
event_bus.py — Simple in-process pub/sub for the Agent Activity Feed.

Each connected SSE client gets its own asyncio.Queue. The agentic loop
publishes events to all connected clients at each stage so the frontend
can show the loop firing live.

Uses a thread-safe approach: sync code calls publish_sync() which schedules
the async put onto the event loop.
"""

import asyncio
import json
import threading
from datetime import datetime
from typing import List, Optional

# List of queues — one per connected SSE client
_subscribers: List[asyncio.Queue] = []
_lock = threading.Lock()

# Reference to the main event loop, set during startup
_loop: Optional[asyncio.AbstractEventLoop] = None


def set_event_loop(loop: asyncio.AbstractEventLoop):
    """Store a reference to the main async event loop for cross-thread publishing."""
    global _loop
    _loop = loop


def subscribe() -> asyncio.Queue:
    """Register a new SSE client. Returns a queue that will receive events."""
    q: asyncio.Queue = asyncio.Queue()
    with _lock:
        _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue):
    """Remove a disconnected SSE client's queue."""
    with _lock:
        if q in _subscribers:
            _subscribers.remove(q)


def publish_sync(event_type: str, message: str, product_id: int = None):
    """
    Thread-safe synchronous publish — called from the agentic loop
    which runs in a background thread via asyncio.to_thread().
    Schedules the async put onto the main event loop.
    """
    event = json.dumps({
        "event_type": event_type,
        "message": message,
        "product_id": product_id,
        "timestamp": datetime.utcnow().isoformat(),
    })
    with _lock:
        for q in _subscribers:
            try:
                if _loop and _loop.is_running():
                    _loop.call_soon_threadsafe(q.put_nowait, event)
                else:
                    q.put_nowait(event)
            except (asyncio.QueueFull, RuntimeError):
                pass  # Decision: drop events for slow clients rather than blocking


async def publish(event_type: str, message: str, product_id: int = None):
    """
    Async publish — can be called from async code directly.
    """
    event = json.dumps({
        "event_type": event_type,
        "message": message,
        "product_id": product_id,
        "timestamp": datetime.utcnow().isoformat(),
    })
    with _lock:
        for q in list(_subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass
