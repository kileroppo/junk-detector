"""Priority task queue for the dispatcher.

Uses asyncio.PriorityQueue internally with items sorted by
(priority, created_at) — lower priority number = higher urgency.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from src.dispatcher.models import TaskPayload


@dataclass(order=False)
class _PriorityItem:
    """Wrapper that implements __lt__ for proper priority queue ordering.

    Sorting: lower priority value first, then earlier created_at first.
    """

    priority: int
    created_at: datetime
    task: TaskPayload = field(compare=False)

    def __lt__(self, other: _PriorityItem) -> bool:
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.created_at < other.created_at

    def __le__(self, other: _PriorityItem) -> bool:
        return self == other or self < other

    def __gt__(self, other: _PriorityItem) -> bool:
        return not self <= other

    def __ge__(self, other: _PriorityItem) -> bool:
        return not self < other


class PriorityTaskQueue:
    """Async priority queue for TaskPayload items.

    Tasks are dequeued in priority order (lower number = higher urgency).
    Ties are broken by created_at (earlier first).
    """

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: asyncio.PriorityQueue[_PriorityItem] = asyncio.PriorityQueue(maxsize=maxsize)

    async def put(self, task: TaskPayload) -> None:
        """Add a task to the priority queue."""
        item = _PriorityItem(
            priority=int(task.priority),
            created_at=task.created_at,
            task=task,
        )
        await self._queue.put(item)

    async def get(self) -> TaskPayload:
        """Get the highest priority task. Blocks if the queue is empty."""
        item = await self._queue.get()
        return item.task

    def qsize(self) -> int:
        """Return the current queue size."""
        return self._queue.qsize()

    def empty(self) -> bool:
        """Check if the queue is empty."""
        return self._queue.empty()

    async def drain(self) -> list[TaskPayload]:
        """Drain all items from the queue (non-blocking).

        Returns a list of all tasks currently in the queue, ordered by priority.
        """
        items: list[TaskPayload] = []
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                items.append(item.task)
            except asyncio.QueueEmpty:
                break
        return items
