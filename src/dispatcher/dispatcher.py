"""Core Dispatcher — async task scheduling with concurrency control.

Inspired by x-algorithm's Dispatcher + Engine pattern.
Consumes FeedItems from an asyncio.Queue, manages concurrency via max_in_flight,
retries failed tasks with exponential backoff, and uses a priority queue.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from src.dispatcher.models import (
    DispatcherStats,
    TaskPayload,
    TaskPriority,
    TaskResult,
    TaskStatus,
)
from src.dispatcher.retry import RetryPolicy, calculate_delay, should_retry
from src.dispatcher.task_queue import PriorityTaskQueue

logger = logging.getLogger("dispatcher")


class Dispatcher:
    """Async task dispatcher with priority queue, concurrency control, and retry.

    The dispatcher does NOT import or call the scoring pipeline directly —
    it uses the score_callback pattern for loose coupling.

    Usage:
        dispatcher = Dispatcher(input_queue=feed_queue, max_in_flight=3)
        dispatcher.score_callback = my_scoring_function
        await dispatcher.start()
        ...
        await dispatcher.stop()
    """

    def __init__(
        self,
        input_queue: asyncio.Queue,
        max_in_flight: int = 3,
        retry_policy: RetryPolicy = RetryPolicy(),
    ) -> None:
        self._input_queue = input_queue
        self._max_in_flight = max_in_flight
        self._retry_policy = retry_policy

        # Internal state
        self._task_queue = PriorityTaskQueue()
        self._in_flight: set[str] = set()
        self._results: asyncio.Queue[TaskResult] = asyncio.Queue()
        self._running: bool = False
        self._stats = DispatcherStats()
        self._processing_times: list[float] = []

        # Callback for scoring — set by integration layer
        self.score_callback: Callable[[TaskPayload], Awaitable[TaskResult]] | None = (
            None
        )

        # Internal asyncio tasks
        self._tasks: list[asyncio.Task] = []

    @property
    def stats(self) -> DispatcherStats:
        """Return current dispatcher statistics."""
        self._stats.in_flight = len(self._in_flight)
        self._stats.queue_size = self._task_queue.qsize()
        if self._processing_times:
            self._stats.avg_processing_time_ms = (
                sum(self._processing_times) / len(self._processing_times)
            )
        return self._stats

    async def start(self) -> None:
        """Start the dispatcher — launches fill, execute, and result loops."""
        if self._running:
            logger.warning("Dispatcher is already running")
            return

        self._running = True
        logger.info(
            f"Starting dispatcher (max_in_flight={self._max_in_flight}, "
            f"max_attempts={self._retry_policy.max_attempts})"
        )

        self._tasks = [
            asyncio.create_task(self._fill_loop(), name="dispatcher-fill"),
            asyncio.create_task(self._execute_loop(), name="dispatcher-execute"),
            asyncio.create_task(self._result_loop(), name="dispatcher-result"),
        ]

    async def stop(self) -> None:
        """Graceful shutdown — wait for in_flight to drain, then cancel tasks."""
        logger.info("Stopping dispatcher...")
        self._running = False

        # Wait for in-flight tasks to complete (with timeout)
        timeout = 30.0
        elapsed = 0.0
        while self._in_flight and elapsed < timeout:
            await asyncio.sleep(0.1)
            elapsed += 0.1

        if self._in_flight:
            logger.warning(
                f"Shutdown timeout reached with {len(self._in_flight)} tasks still in flight"
            )

        # Cancel internal loop tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for cancellation to complete
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._tasks.clear()
        logger.info("Dispatcher stopped")

    async def submit(
        self, url: str, priority: TaskPriority = TaskPriority.NORMAL
    ) -> str:
        """Manually submit a single URL for scoring.

        Args:
            url: The URL to score.
            priority: Task priority level.

        Returns:
            The task ID of the submitted task.
        """
        task = TaskPayload(
            url=url,
            source_name="manual",
            priority=priority,
        )
        await self._task_queue.put(task)
        self._stats.total_submitted += 1
        logger.debug(f"Manually submitted task {task.id} for {url}")
        return task.id

    async def _fill_loop(self) -> None:
        """Continuously read FeedItems from input_queue and wrap into TaskPayloads."""
        logger.info("Fill loop started")
        try:
            while self._running:
                try:
                    # Wait for a FeedItem with a timeout so we can check _running
                    feed_item = await asyncio.wait_for(
                        self._input_queue.get(), timeout=0.5
                    )
                except asyncio.TimeoutError:
                    continue

                task = TaskPayload(
                    url=feed_item.url,
                    title=getattr(feed_item, "title", None),
                    source_name=getattr(feed_item, "source_name", "unknown"),
                    priority=TaskPriority(
                        min(
                            max(getattr(feed_item, "priority", 5), 1),
                            9,
                        )
                    ),
                )
                await self._task_queue.put(task)
                self._stats.total_submitted += 1
                logger.debug(
                    f"Queued task {task.id} from feed: {feed_item.url} "
                    f"(priority={task.priority.name})"
                )
        except asyncio.CancelledError:
            logger.debug("Fill loop cancelled")
        except Exception as e:
            logger.error(f"Fill loop error: {e}")

    async def _execute_loop(self) -> None:
        """Continuously get tasks from priority queue and execute them."""
        logger.info("Execute loop started")
        try:
            while self._running or not self._task_queue.empty():
                # Wait if at capacity
                if len(self._in_flight) >= self._max_in_flight:
                    await asyncio.sleep(0.05)
                    continue

                # Try to get a task (non-blocking check first to allow loop exit)
                if self._task_queue.empty():
                    await asyncio.sleep(0.05)
                    continue

                try:
                    task = await asyncio.wait_for(
                        self._task_queue.get(), timeout=0.5
                    )
                except asyncio.TimeoutError:
                    continue

                # Spawn execution
                asyncio.create_task(
                    self._execute_task(task), name=f"task-{task.id[:8]}"
                )
        except asyncio.CancelledError:
            logger.debug("Execute loop cancelled")
        except Exception as e:
            logger.error(f"Execute loop error: {e}")

    async def _execute_task(self, task: TaskPayload) -> None:
        """Execute a single task via score_callback and put result in results queue."""
        task.status = TaskStatus.RUNNING
        self._in_flight.add(task.id)
        started_at = datetime.now(timezone.utc)

        try:
            if self.score_callback is None:
                raise RuntimeError("No score_callback configured on dispatcher")

            result = await self.score_callback(task)
            result.started_at = started_at
            result.finished_at = datetime.now(timezone.utc)
            result.attempts_used = task.attempt + 1
        except Exception as e:
            result = TaskResult(
                task_id=task.id,
                success=False,
                error=str(e),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                attempts_used=task.attempt + 1,
            )

        # Track processing time
        processing_ms = (
            result.finished_at - result.started_at
        ).total_seconds() * 1000
        self._processing_times.append(processing_ms)

        # Remove from in-flight
        self._in_flight.discard(task.id)

        # Put result for the result loop to handle
        await self._results.put(result)

    async def _result_loop(self) -> None:
        """Process results: update stats, handle retries for failures."""
        logger.info("Result loop started")
        try:
            while self._running or self._in_flight or not self._results.empty():
                try:
                    result = await asyncio.wait_for(
                        self._results.get(), timeout=0.5
                    )
                except asyncio.TimeoutError:
                    # Avoid busy-wait when nothing to process
                    if not self._running and not self._in_flight:
                        break
                    continue

                if result.success:
                    self._stats.total_completed += 1
                    logger.debug(
                        f"Task {result.task_id} completed successfully "
                        f"(attempts={result.attempts_used})"
                    )
                else:
                    # Build a synthetic task to check retry eligibility
                    retry_task = TaskPayload(
                        id=result.task_id,
                        url="",  # placeholder — we need the original task
                        source_name="",
                        attempt=result.attempts_used,
                    )

                    if should_retry(retry_task, self._retry_policy):
                        # Retry: put back into queue with incremented attempt
                        self._stats.total_retried += 1
                        delay = calculate_delay(
                            retry_task.attempt, self._retry_policy
                        )
                        logger.warning(
                            f"Task {result.task_id} failed (attempt "
                            f"{result.attempts_used}), retrying in {delay:.1f}s: "
                            f"{result.error}"
                        )
                        await asyncio.sleep(delay)
                        # Re-submit with retrying status
                        retry_task.status = TaskStatus.RETRYING
                        await self._task_queue.put(retry_task)
                    else:
                        # Dead: exceeded max retries
                        self._stats.total_failed += 1
                        logger.error(
                            f"Task {result.task_id} DEAD after "
                            f"{result.attempts_used} attempts: {result.error}"
                        )
        except asyncio.CancelledError:
            logger.debug("Result loop cancelled")
        except Exception as e:
            logger.error(f"Result loop error: {e}")
