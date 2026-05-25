"""Data models for the Dispatcher task scheduling system."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskPriority(IntEnum):
    """Task priority levels. Lower number = higher urgency."""

    CRITICAL = 1
    HIGH = 3
    NORMAL = 5
    LOW = 7
    BACKGROUND = 9


class TaskStatus(str, Enum):
    """Lifecycle status of a task."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD = "dead"  # exceeded max retries


class TaskPayload(BaseModel):
    """Represents a scoring task to be dispatched."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    url: str
    title: str | None = None
    source_name: str
    priority: TaskPriority = TaskPriority.NORMAL
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attempt: int = 0
    max_attempts: int = 3
    status: TaskStatus = TaskStatus.PENDING


class TaskResult(BaseModel):
    """Result of executing a scoring task."""

    task_id: str
    success: bool
    score_result: Any | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime
    attempts_used: int


class DispatcherStats(BaseModel):
    """Runtime statistics for the dispatcher."""

    total_submitted: int = 0
    total_completed: int = 0
    total_failed: int = 0
    total_retried: int = 0
    in_flight: int = 0
    queue_size: int = 0
    avg_processing_time_ms: float = 0.0
