from __future__ import annotations

"""Evento pub/sub ligero para orquestar los agentes autónomos entre módulos.

Permite que el Módulo 2 (Loop Agéntico) publique eventos de incidentes, que el
Módulo 5 (Gobernanza) los evalúe contra los umbrales humanos, y que el Módulo 3
reaccione a señalizaciones de inventario. Elimina acoplamiento directo entre
módulos.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Awaitable, Callable

logger = logging.getLogger("event_bus")

Handler = Callable[[dict], Awaitable[None]]

_subscribers: dict[str, list[Handler]] = defaultdict(list)
_history: list[dict] = []
_lock = asyncio.Lock()
MAX_HISTORY = 1000


def topic(*names: str) -> str:
    """Composes a hierarchical topic like 'incident.routing.delay'."""
    return ".".join(names)


async def publish(name: str, payload: dict) -> None:
    event = {"topic": name, "payload": payload}
    async with _lock:
        _history.append(event)
        if len(_history) > MAX_HISTORY:
            del _history[: len(_history) - MAX_HISTORY]
    logger.info("Event published: %s", name)
    for handler in list(_subscribers.get(name, [])):
        try:
            await handler(payload)
        except Exception:  # noqa: BLE001 - un listener no bloquea a los demás
            logger.exception("Handler failed for topic %s", name)


def subscribe(name: str, handler: Handler) -> None:
    _subscribers[name].append(handler)


def history(topic_filter: str | None = None) -> list[dict]:
    if topic_filter:
        return [e for e in _history if e["topic"].startswith(topic_filter)]
    return list(_history)
