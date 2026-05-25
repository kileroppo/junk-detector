"""Tests for the dispatcher module: models, retry, and task_queue."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src.dispatcher.models import (
    DispatcherStats,
    TaskPayload,
    TaskPriority,
    TaskResult,
    TaskStatus,
)
from src.dispatcher.retry import RetryPolicy, calculate_delay, should_retry
from src.dispatcher.task_queue import PriorityTaskQueue

# ===== TaskPriority Tests =====


class TestTaskPriority:
    """Tests for the TaskPriority enum ordering."""

    def test_priority_values(self):
        assert TaskPriority.CRITICAL == 1
        assert TaskPriority.HIGH == 3
        assert TaskPriority.NORMAL == 5
        assert TaskPriority.LOW == 7
        assert TaskPriority.BACKGROUND == 9

    def test_priority_ordering(self):
        assert TaskPriority.CRITICAL < TaskPriority.HIGH
        assert TaskPriority.HIGH < TaskPriority.NORMAL
        assert TaskPriority.NORMAL < TaskPriority.LOW
        assert TaskPriority.LOW < TaskPriority.BACKGROUND

    def test_priority_is_int_enum(self):
        assert isinstance(TaskPriority.CRITICAL, int)
        assert int(TaskPriority.NORMAL) == 5


# ===== TaskStatus Tests =====


class TestTaskStatus:
    """Tests for the TaskStatus enum values."""

    def test_status_values(self):
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.SUCCESS == "success"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.RETRYING == "retrying"
        assert TaskStatus.DEAD == "dead"

    def test_status_is_str_enum(self):
        assert isinstance(TaskStatus.PENDING, str)


# ===== TaskPayload Tests =====


class TestTaskPayload:
    """Tests for the TaskPayload model."""

    def test_default_creation(self):
        task = TaskPayload(url="https://example.com", source_name="test")
        assert task.id is not None
        assert len(task.id) > 0
        assert task.url == "https://example.com"
        assert task.source_name == "test"
        assert task.title is None
        assert task.priority == TaskPriority.NORMAL
        assert task.attempt == 0
        assert task.max_attempts == 3
        assert task.status == TaskStatus.PENDING
        assert task.created_at is not None

    def test_auto_generated_uuid_is_unique(self):
        task1 = TaskPayload(url="https://a.com", source_name="s1")
        task2 = TaskPayload(url="https://b.com", source_name="s2")
        assert task1.id != task2.id

    def test_custom_values(self):
        now = datetime.now(timezone.utc)
        task = TaskPayload(
            id="custom-id",
            url="https://example.com/article",
            title="Test Article",
            source_name="rss-feed",
            priority=TaskPriority.HIGH,
            created_at=now,
            attempt=2,
            max_attempts=5,
            status=TaskStatus.RETRYING,
        )
        assert task.id == "custom-id"
        assert task.title == "Test Article"
        assert task.priority == TaskPriority.HIGH
        assert task.created_at == now
        assert task.attempt == 2
        assert task.max_attempts == 5
        assert task.status == TaskStatus.RETRYING


# ===== TaskResult Tests =====


class TestTaskResult:
    """Tests for the TaskResult model."""

    def test_successful_result(self):
        now = datetime.now(timezone.utc)
        result = TaskResult(
            task_id="task-1",
            success=True,
            score_result={"score": 85},
            error=None,
            started_at=now,
            finished_at=now + timedelta(seconds=2),
            attempts_used=1,
        )
        assert result.task_id == "task-1"
        assert result.success is True
        assert result.score_result == {"score": 85}
        assert result.error is None
        assert result.attempts_used == 1

    def test_failed_result(self):
        now = datetime.now(timezone.utc)
        result = TaskResult(
            task_id="task-2",
            success=False,
            score_result=None,
            error="Timeout",
            started_at=now,
            finished_at=now + timedelta(seconds=10),
            attempts_used=3,
        )
        assert result.success is False
        assert result.error == "Timeout"
        assert result.score_result is None


# ===== DispatcherStats Tests =====


class TestDispatcherStats:
    """Tests for the DispatcherStats model."""

    def test_defaults(self):
        stats = DispatcherStats()
        assert stats.total_submitted == 0
        assert stats.total_completed == 0
        assert stats.total_failed == 0
        assert stats.total_retried == 0
        assert stats.in_flight == 0
        assert stats.queue_size == 0
        assert stats.avg_processing_time_ms == 0.0

    def test_custom_values(self):
        stats = DispatcherStats(
            total_submitted=100,
            total_completed=90,
            total_failed=5,
            total_retried=10,
            in_flight=5,
            queue_size=20,
            avg_processing_time_ms=150.5,
        )
        assert stats.total_submitted == 100
        assert stats.total_completed == 90
        assert stats.avg_processing_time_ms == 150.5


# ===== RetryPolicy Tests =====


class TestRetryPolicy:
    """Tests for the RetryPolicy dataclass."""

    def test_defaults(self):
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.base_delay_seconds == 1.0
        assert policy.max_delay_seconds == 30.0
        assert policy.exponential_base == 2.0

    def test_custom_values(self):
        policy = RetryPolicy(
            max_attempts=5,
            base_delay_seconds=0.5,
            max_delay_seconds=60.0,
            exponential_base=3.0,
        )
        assert policy.max_attempts == 5
        assert policy.base_delay_seconds == 0.5
        assert policy.max_delay_seconds == 60.0
        assert policy.exponential_base == 3.0


# ===== calculate_delay Tests =====


class TestCalculateDelay:
    """Tests for the calculate_delay function."""

    def test_exponential_growth(self):
        policy = RetryPolicy(base_delay_seconds=1.0, exponential_base=2.0)
        with patch("src.dispatcher.retry.random.uniform", return_value=0.0):
            assert calculate_delay(0, policy) == 1.0  # 1 * 2^0 = 1
            assert calculate_delay(1, policy) == 2.0  # 1 * 2^1 = 2
            assert calculate_delay(2, policy) == 4.0  # 1 * 2^2 = 4
            assert calculate_delay(3, policy) == 8.0  # 1 * 2^3 = 8

    def test_capped_at_max_delay(self):
        policy = RetryPolicy(
            base_delay_seconds=1.0,
            max_delay_seconds=10.0,
            exponential_base=2.0,
        )
        with patch("src.dispatcher.retry.random.uniform", return_value=0.0):
            # 1 * 2^5 = 32, should be capped at 10
            assert calculate_delay(5, policy) == 10.0

    def test_jitter_adds_randomness(self):
        policy = RetryPolicy(base_delay_seconds=1.0, exponential_base=2.0)
        with patch("src.dispatcher.retry.random.uniform", return_value=0.25):
            # 1 * 2^0 + 0.25 = 1.25
            assert calculate_delay(0, policy) == 1.25

        with patch("src.dispatcher.retry.random.uniform", return_value=0.5):
            # 1 * 2^0 + 0.5 = 1.5
            assert calculate_delay(0, policy) == 1.5

    def test_jitter_range(self):
        """Verify jitter is between 0 and 0.5 across multiple calls."""
        policy = RetryPolicy(base_delay_seconds=1.0, exponential_base=2.0)
        delays = [calculate_delay(0, policy) for _ in range(100)]
        # Without jitter the delay would be 1.0, with jitter it's in [1.0, 1.5]
        assert all(1.0 <= d <= 1.5 for d in delays)


# ===== should_retry Tests =====


class TestShouldRetry:
    """Tests for the should_retry function."""

    def test_returns_true_when_attempts_remaining(self):
        policy = RetryPolicy(max_attempts=3)
        task = TaskPayload(url="https://example.com", source_name="test", attempt=0)
        assert should_retry(task, policy) is True

        task = TaskPayload(url="https://example.com", source_name="test", attempt=1)
        assert should_retry(task, policy) is True

        task = TaskPayload(url="https://example.com", source_name="test", attempt=2)
        assert should_retry(task, policy) is True

    def test_returns_false_when_max_reached(self):
        policy = RetryPolicy(max_attempts=3)
        task = TaskPayload(url="https://example.com", source_name="test", attempt=3)
        assert should_retry(task, policy) is False

    def test_returns_false_when_exceeded(self):
        policy = RetryPolicy(max_attempts=3)
        task = TaskPayload(url="https://example.com", source_name="test", attempt=5)
        assert should_retry(task, policy) is False


# ===== PriorityTaskQueue Tests =====


class TestPriorityTaskQueue:
    """Tests for the PriorityTaskQueue class."""

    async def test_put_and_get_single_item(self):
        queue = PriorityTaskQueue()
        task = TaskPayload(url="https://example.com", source_name="test")
        await queue.put(task)
        result = await queue.get()
        assert result.id == task.id

    async def test_priority_ordering(self):
        """Lower priority number should be dequeued first."""
        queue = PriorityTaskQueue()
        low = TaskPayload(url="https://low.com", source_name="test", priority=TaskPriority.LOW)
        critical = TaskPayload(
            url="https://critical.com", source_name="test", priority=TaskPriority.CRITICAL
        )
        normal = TaskPayload(
            url="https://normal.com", source_name="test", priority=TaskPriority.NORMAL
        )

        # Put in non-priority order
        await queue.put(low)
        await queue.put(critical)
        await queue.put(normal)

        # Should come out in priority order
        first = await queue.get()
        second = await queue.get()
        third = await queue.get()

        assert first.priority == TaskPriority.CRITICAL
        assert second.priority == TaskPriority.NORMAL
        assert third.priority == TaskPriority.LOW

    async def test_fifo_for_same_priority(self):
        """Items with same priority should come out in created_at order."""
        queue = PriorityTaskQueue()
        now = datetime.now(timezone.utc)

        task1 = TaskPayload(
            url="https://first.com",
            source_name="test",
            priority=TaskPriority.NORMAL,
            created_at=now,
        )
        task2 = TaskPayload(
            url="https://second.com",
            source_name="test",
            priority=TaskPriority.NORMAL,
            created_at=now + timedelta(seconds=1),
        )
        task3 = TaskPayload(
            url="https://third.com",
            source_name="test",
            priority=TaskPriority.NORMAL,
            created_at=now + timedelta(seconds=2),
        )

        await queue.put(task3)
        await queue.put(task1)
        await queue.put(task2)

        first = await queue.get()
        second = await queue.get()
        third = await queue.get()

        assert first.url == "https://first.com"
        assert second.url == "https://second.com"
        assert third.url == "https://third.com"

    async def test_empty_and_qsize(self):
        queue = PriorityTaskQueue()
        assert queue.empty() is True
        assert queue.qsize() == 0

        task = TaskPayload(url="https://example.com", source_name="test")
        await queue.put(task)

        assert queue.empty() is False
        assert queue.qsize() == 1

        await queue.get()
        assert queue.empty() is True
        assert queue.qsize() == 0

    async def test_drain_returns_all_items_in_order(self):
        queue = PriorityTaskQueue()
        high = TaskPayload(url="https://high.com", source_name="test", priority=TaskPriority.HIGH)
        bg = TaskPayload(url="https://bg.com", source_name="test", priority=TaskPriority.BACKGROUND)
        critical = TaskPayload(
            url="https://critical.com", source_name="test", priority=TaskPriority.CRITICAL
        )

        await queue.put(high)
        await queue.put(bg)
        await queue.put(critical)

        items = await queue.drain()
        assert len(items) == 3
        assert items[0].priority == TaskPriority.CRITICAL
        assert items[1].priority == TaskPriority.HIGH
        assert items[2].priority == TaskPriority.BACKGROUND
        assert queue.empty() is True

    async def test_drain_on_empty_queue(self):
        queue = PriorityTaskQueue()
        items = await queue.drain()
        assert items == []


class TestPriorityItemOrdering:
    """Tests for the _PriorityItem comparison operators."""

    def test_le_same_items(self):
        from src.dispatcher.task_queue import _PriorityItem

        now = datetime.now(timezone.utc)
        task = TaskPayload(url="https://example.com", source_name="test")
        item1 = _PriorityItem(priority=5, created_at=now, task=task)
        item2 = _PriorityItem(priority=5, created_at=now, task=task)
        assert item1 <= item2

    def test_le_lower_priority(self):
        from src.dispatcher.task_queue import _PriorityItem

        now = datetime.now(timezone.utc)
        task = TaskPayload(url="https://example.com", source_name="test")
        item_low = _PriorityItem(priority=1, created_at=now, task=task)
        item_high = _PriorityItem(priority=5, created_at=now, task=task)
        assert item_low <= item_high

    def test_gt(self):
        from src.dispatcher.task_queue import _PriorityItem

        now = datetime.now(timezone.utc)
        task = TaskPayload(url="https://example.com", source_name="test")
        item_low = _PriorityItem(priority=1, created_at=now, task=task)
        item_high = _PriorityItem(priority=5, created_at=now, task=task)
        assert item_high > item_low
        assert not item_low > item_high

    def test_ge(self):
        from src.dispatcher.task_queue import _PriorityItem

        now = datetime.now(timezone.utc)
        task = TaskPayload(url="https://example.com", source_name="test")
        item1 = _PriorityItem(priority=5, created_at=now, task=task)
        item2 = _PriorityItem(priority=5, created_at=now, task=task)
        item3 = _PriorityItem(priority=1, created_at=now, task=task)
        assert item1 >= item2
        assert item1 >= item3
        assert not item3 >= item1
