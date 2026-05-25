"""
Event Engine Core for Async-First Decoupled Architecture.
Defines base Event structure and high-performance EventEngine dispatcher.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from typing import Any, Callable, Coroutine, Dict, List, Set, Union

from utils import get_logger

logger = get_logger(__name__)

# Event Types Constants
EVENT_TICK = "EVENT_TICK"          # Real-time tick stream update
EVENT_SIGNAL = "EVENT_SIGNAL"      # Trading signal generation
EVENT_ORDER = "EVENT_ORDER"        # Order OMS routing
EVENT_FILL = "EVENT_FILL"          # Successful execution fill details
EVENT_RISK = "EVENT_RISK"          # Sentry safety/risk event
EVENT_HEALTH = "EVENT_HEALTH"      # Heartbeat / connection status


class Event:
    """Represents a discrete system event message."""

    def __init__(self, event_type: str, data: Any = None):
        self.type: str = event_type
        self.timestamp: float = time.time()
        self.data: Any = data

    def __repr__(self) -> str:
        return f"<Event type={self.type} ts={self.timestamp:.4f}>"


# Define Type alias for event handlers (can be standard function or coroutine)
EventHandler = Callable[[Event], Union[None, Coroutine[Any, Any, None]]]


class EventEngine:
    """
    High-performance asynchronous Event Engine.
    Coordinates decoupled components by registering listeners and dispatching events via an asyncio Queue.
    """

    def __init__(self):
        self._handlers: Dict[str, Set[EventHandler]] = {}
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._active: bool = False
        self._task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def register_listener(self, event_type: str, handler: EventHandler) -> None:
        """Register a callback function/coroutine to listen for a specific event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = set()
        self._handlers[event_type].add(handler)
        logger.debug("Registered handler %s for event %s", handler.__name__, event_type)

    def unregister_listener(self, event_type: str, handler: EventHandler) -> None:
        """Deregister an existing listener."""
        if event_type in self._handlers:
            self._handlers[event_type].discard(handler)
            if not self._handlers[event_type]:
                del self._handlers[event_type]
            logger.debug("Unregistered handler %s for event %s", handler.__name__, event_type)

    def put(self, event: Event) -> None:
        """
        Thread-safe, non-blocking submission of an event to the queue.
        Works seamlessly from inside or outside the main event loop thread.
        """
        if not self._active:
            return

        if self._loop and self._loop.is_running():
            try:
                # If currently running in the loop's thread
                self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
            except Exception as e:
                logger.error("Failed placing event %s in queue: %s", event.type, e)
        else:
            # Fallback for synchronous/initialization thread setups
            try:
                self._queue.put_nowait(event)
            except Exception:
                pass

    async def _run(self) -> None:
        """Main asynchronous processing loop."""
        logger.info("EventEngine main loop task started.")
        while self._active:
            try:
                # Wait for next event
                event = await self._queue.get()
                
                # Dispatch to all registered listeners
                handlers = self._handlers.get(event.type, set()).copy()
                if handlers:
                    tasks = []
                    for handler in handlers:
                        try:
                            # Handle both coroutines and standard synchronous functions gracefully
                            if inspect.iscoroutinefunction(handler):
                                tasks.append(asyncio.create_task(handler(event)))
                            else:
                                handler(event)
                        except Exception as ex:
                            logger.error("Error executing handler for %s: %s", event.type, ex)
                    
                    # Await all coroutine dispatches concurrently
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)

                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in EventEngine run loop: %s", e)

    def start(self) -> None:
        """Start the async event processing task."""
        if self._active:
            return
        
        self._active = True
        self._loop = asyncio.get_event_loop()
        self._task = self._loop.create_task(self._run())
        logger.info("EventEngine started.")

    async def stop(self) -> None:
        """Stop processing and drain remaining events."""
        if not self._active:
            return

        logger.info("Stopping EventEngine...")
        self._active = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # Clean queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except (asyncio.QueueEmpty, ValueError):
                break

        logger.info("EventEngine stopped.")
