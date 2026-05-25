"""MonitorService — orchestrates Thunder + Dispatcher + Pipeline.

Wires together:
- ThunderMonitor (source polling / discovery)
- Dispatcher (task scheduling, concurrency, retries)
- ScoringPipeline (actual content quality scoring)

Usage:
    service = MonitorService.from_config_file("config.yaml")
    await service.start()
    ...
    await service.stop()
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.core.pipeline import PipelineContext, build_default_pipeline
from src.dispatcher.models import TaskPayload, TaskResult, TaskPriority, TaskStatus
from src.dispatcher.retry import RetryPolicy
from src.thunder.models import FeedItem, SourceConfig
from src.thunder.monitor import ThunderMonitor
from src.thunder.sources import ContentSource, RSSSource, WebhookSource

logger = logging.getLogger("monitor")


class MonitorService:
    """Orchestrates Thunder (source monitoring) + Dispatcher (task scheduling) + Pipeline (scoring).

    The MonitorService is the top-level integration object. It:
    1. Creates content sources from configuration
    2. Connects ThunderMonitor -> shared asyncio.Queue -> Dispatcher
    3. Provides a score_callback that runs the scoring pipeline
    4. Exposes combined stats from all subsystems

    Args:
        config: Dictionary with 'thunder' and 'dispatcher' sections.
    """

    def __init__(self, config: dict) -> None:
        self._config = config
        self._running = False

        # Shared queue between Thunder and Dispatcher
        self._queue: asyncio.Queue[FeedItem] = asyncio.Queue()

        # Parse sources from config
        thunder_config = config.get("thunder", {})
        sources = self._build_sources(thunder_config)

        # Create ThunderMonitor
        self.thunder = ThunderMonitor(output_queue=self._queue, sources=sources)

        # Parse dispatcher settings
        dispatcher_config = config.get("dispatcher", {})
        retry_config = dispatcher_config.get("retry", {})
        self._retry_policy = RetryPolicy(
            max_attempts=retry_config.get("max_attempts", 3),
            base_delay_seconds=retry_config.get("base_delay_seconds", 2.0),
            max_delay_seconds=retry_config.get("max_delay_seconds", 60.0),
            exponential_base=retry_config.get("exponential_base", 2.0),
        )
        self._max_in_flight = dispatcher_config.get("max_in_flight", 3)
        self._max_tasks_per_minute = dispatcher_config.get("max_tasks_per_minute", 20)
        self._shutdown_timeout = dispatcher_config.get("shutdown_timeout_seconds", 30)

        # Dispatcher worker task (consumer loop)
        self._consumer_task: asyncio.Task | None = None
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(self._max_in_flight)

        # Stats tracking
        self._total_scored: int = 0
        self._total_failed: int = 0
        self._total_retried: int = 0
        self._in_flight: int = 0

        # Scored items tracking for summary
        self._scored_items: list[dict] = []
        self._last_summary: dict | None = None

        # Webhook source reference (for API integration)
        self._webhook_source: WebhookSource | None = None
        for source in sources:
            if isinstance(source, WebhookSource):
                self._webhook_source = source
                break

    def _build_sources(self, thunder_config: dict) -> list[ContentSource]:
        """Build content sources from thunder configuration.

        Args:
            thunder_config: The 'thunder' section of config.yaml.

        Returns:
            List of ContentSource instances ready for use by ThunderMonitor.
        """
        sources: list[ContentSource] = []
        source_configs = thunder_config.get("sources", [])

        for src_conf in source_configs:
            if not src_conf.get("enabled", True):
                continue

            config = SourceConfig(
                name=src_conf["name"],
                type=src_conf.get("type", "rss"),
                url=src_conf.get("url", ""),
                poll_interval_seconds=src_conf.get("poll_interval_seconds", 300),
                priority=src_conf.get("priority", 5),
                enabled=src_conf.get("enabled", True),
            )

            if config.type == "rss":
                sources.append(RSSSource(config))
            elif config.type == "webhook":
                sources.append(WebhookSource(config))
            else:
                logger.warning(f"Unknown source type '{config.type}' for '{config.name}', skipping")

        # Create a default webhook source if webhook is enabled
        webhook_config = thunder_config.get("webhook", {})
        if webhook_config.get("enabled", False):
            wh_config = SourceConfig(
                name="webhook",
                type="webhook",
                url=webhook_config.get("path", "/webhook/content"),
                poll_interval_seconds=10,  # poll the internal queue frequently
                priority=3,  # webhook items default to higher priority
                enabled=True,
            )
            sources.append(WebhookSource(wh_config))

        return sources

    async def start(self) -> None:
        """Start monitoring all sources.

        Starts the consumer loop first (so it's ready to process items),
        then starts ThunderMonitor (which begins discovering items).
        """
        if self._running:
            logger.warning("MonitorService is already running")
            return

        self._running = True
        logger.info("MonitorService starting...")

        # Start the consumer loop
        self._consumer_task = asyncio.create_task(
            self._consumer_loop(), name="monitor-consumer"
        )

        # Start thunder (begins polling sources)
        await self.thunder.start()

        source_names = [
            s.name for s in self.thunder._sources  # noqa: SLF001
        ]
        logger.info(
            f"MonitorService started — monitoring {len(source_names)} source(s): "
            f"{', '.join(source_names)}"
        )

    async def stop(self) -> None:
        """Graceful shutdown.

        1. Stop Thunder first (stop discovering new items)
        2. Wait for queue to drain (with timeout)
        3. Stop the consumer loop
        """
        if not self._running:
            return

        self._running = False
        logger.info("MonitorService stopping...")

        # Stop thunder first — no more new discoveries
        await self.thunder.stop()

        # Give consumer time to drain remaining items
        try:
            await asyncio.wait_for(self._drain_queue(), timeout=self._shutdown_timeout)
        except asyncio.TimeoutError:
            logger.warning(
                f"Shutdown timeout ({self._shutdown_timeout}s) reached, "
                f"{self._queue.qsize()} items still in queue"
            )

        # Cancel the consumer task
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

        # Generate summary before final stop
        self.generate_summary()

        logger.info("MonitorService stopped")

    async def _drain_queue(self) -> None:
        """Wait until the queue is empty and all in-flight tasks complete."""
        while not self._queue.empty() or self._in_flight > 0:
            await asyncio.sleep(0.5)

    async def _consumer_loop(self) -> None:
        """Main consumer loop — takes items from queue and scores them.

        Respects max_in_flight concurrency via a semaphore.
        Converts FeedItems from Thunder into TaskPayloads for scoring.
        """
        while self._running:
            try:
                # Wait for an item from the queue (with timeout to allow checking _running)
                try:
                    feed_item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                # Convert FeedItem to TaskPayload
                task = TaskPayload(
                    url=feed_item.url,
                    title=feed_item.title,
                    source_name=feed_item.source_name,
                    priority=TaskPriority(
                        min(feed_item.priority, TaskPriority.BACKGROUND)
                    ),
                    max_attempts=self._retry_policy.max_attempts,
                )

                # Acquire semaphore (respects max_in_flight)
                await self._semaphore.acquire()
                asyncio.create_task(
                    self._execute_task(task), name=f"score-{task.id[:8]}"
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Consumer loop error: {type(e).__name__}: {e}")
                await asyncio.sleep(1)

    async def _execute_task(self, task: TaskPayload) -> None:
        """Execute a single scoring task with retry logic.

        Runs the scoring pipeline, handles retries on failure,
        and updates statistics.

        Args:
            task: The task payload to execute.
        """
        self._in_flight += 1
        try:
            result = await self._score_item(task)

            if result.success:
                self._total_scored += 1
                # Track scored item for summary
                item_data: dict = {
                    "title": task.title or task.url,
                    "url": task.url,
                    "source": task.source_name,
                }
                if result.score_result:
                    item_data["score"] = result.score_result.get("overall_score", 0)
                    item_data["labels"] = result.score_result.get("labels", [])
                else:
                    item_data["score"] = 0
                    item_data["labels"] = []
                self._scored_items.append(item_data)
                logger.info(
                    f"Scored '{task.title or task.url}' from {task.source_name} "
                    f"(attempt {result.attempts_used})"
                )
            else:
                # Check if we should retry
                task.attempt += 1
                if task.attempt < task.max_attempts:
                    self._total_retried += 1
                    # Re-enqueue with exponential backoff delay
                    from src.dispatcher.retry import calculate_delay

                    delay = calculate_delay(task.attempt, self._retry_policy)
                    logger.warning(
                        f"Task '{task.title or task.url}' failed (attempt {task.attempt}/"
                        f"{task.max_attempts}), retrying in {delay:.1f}s: {result.error}"
                    )
                    await asyncio.sleep(delay)
                    # Re-acquire semaphore for retry
                    await self._semaphore.acquire()
                    asyncio.create_task(
                        self._execute_task(task), name=f"score-retry-{task.id[:8]}"
                    )
                else:
                    self._total_failed += 1
                    logger.error(
                        f"Task '{task.title or task.url}' exhausted all retries "
                        f"({task.max_attempts}): {result.error}"
                    )
        except Exception as e:
            self._total_failed += 1
            logger.error(f"Unexpected error scoring task {task.id}: {e}")
        finally:
            self._in_flight -= 1
            self._semaphore.release()

    async def _score_item(self, task: TaskPayload) -> TaskResult:
        """Score a single content item using the existing pipeline.

        Builds a PipelineContext from the task URL, runs the scoring
        pipeline, and wraps the result in a TaskResult.

        Args:
            task: The task payload containing the URL to score.

        Returns:
            TaskResult with success/failure status and score data.
        """
        started_at = datetime.now(timezone.utc)

        try:
            # Determine input type
            input_type = "url" if task.url.startswith(("http://", "https://")) else "text"

            # Build pipeline context
            context = PipelineContext(
                raw_input=task.url,
                input_type=input_type,
            )

            # Run the scoring pipeline
            pipeline = build_default_pipeline()
            context = await pipeline.run(context)

            # Check for pipeline errors
            if context.errors and "extract" in " ".join(context.errors):
                return TaskResult(
                    task_id=task.id,
                    success=False,
                    error=f"Pipeline extraction failed: {'; '.join(context.errors)}",
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc),
                    attempts_used=task.attempt + 1,
                )

            # Success — extract score result
            score_result = None
            if context.result:
                score_result = context.result.model_dump(mode="json")

            return TaskResult(
                task_id=task.id,
                success=True,
                score_result=score_result,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                attempts_used=task.attempt + 1,
            )

        except Exception as e:
            return TaskResult(
                task_id=task.id,
                success=False,
                error=f"{type(e).__name__}: {e}",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                attempts_used=task.attempt + 1,
            )

    def generate_summary(self) -> dict:
        """Generate daily summary of scored items.

        Returns:
            Dictionary with:
                total_scored: int
                total_failed: int
                average_score: float (0.0 if no items)
                high_risk_items: list[dict] (items with overall_score < 40)
                top_labels: list[str] (most common labels across all scored items)
        """
        from collections import Counter

        total_scored = len(self._scored_items)
        total_failed = self._total_failed

        # Calculate average score
        if total_scored > 0:
            average_score = sum(item["score"] for item in self._scored_items) / total_scored
        else:
            average_score = 0.0

        # Identify high risk items (score < 40)
        high_risk_items = [
            item for item in self._scored_items if item["score"] < 40
        ]

        # Aggregate labels by frequency
        label_counter: Counter[str] = Counter()
        for item in self._scored_items:
            for label in item.get("labels", []):
                label_counter[label] += 1

        top_labels = [label for label, _ in label_counter.most_common(10)]

        summary = {
            "total_scored": total_scored,
            "total_failed": total_failed,
            "average_score": average_score,
            "high_risk_items": high_risk_items,
            "top_labels": top_labels,
        }

        self._last_summary = summary
        return summary

    @property
    def last_summary(self) -> dict | None:
        """Return the last generated summary, or None if not yet generated."""
        return self._last_summary

    @property
    def stats(self) -> dict[str, Any]:
        """Combined stats from thunder + dispatcher/consumer.

        Returns:
            Dictionary with thunder stats, dispatcher stats, and queue info.
        """
        return {
            "thunder": self.thunder.stats,
            "dispatcher": {
                "total_scored": self._total_scored,
                "total_failed": self._total_failed,
                "total_retried": self._total_retried,
                "in_flight": self._in_flight,
                "queue_size": self._queue.qsize(),
                "max_in_flight": self._max_in_flight,
            },
        }

    @property
    def webhook_source(self) -> WebhookSource | None:
        """Access the webhook source for external item submission."""
        return self._webhook_source

    @classmethod
    def from_config_file(cls, config_path: str = "config.yaml") -> "MonitorService":
        """Create MonitorService from a YAML config file.

        Reads the config file and extracts 'thunder' and 'dispatcher' sections.

        Args:
            config_path: Path to the YAML configuration file.

        Returns:
            A configured MonitorService instance.

        Raises:
            FileNotFoundError: If the config file doesn't exist.
            yaml.YAMLError: If the config file is invalid YAML.
        """
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(path) as f:
            config = yaml.safe_load(f)

        if not config:
            config = {}

        # Validate required sections exist
        if "thunder" not in config:
            logger.warning(
                f"No 'thunder' section in {config_path}, using defaults"
            )
            config["thunder"] = {"enabled": True, "sources": []}

        if "dispatcher" not in config:
            logger.warning(
                f"No 'dispatcher' section in {config_path}, using defaults"
            )
            config["dispatcher"] = {}

        return cls(config)
