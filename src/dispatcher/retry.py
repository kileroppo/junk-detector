"""Retry strategy with exponential backoff for the dispatcher.

Provides configurable retry policy and delay calculation with jitter.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from src.dispatcher.models import TaskPayload


@dataclass
class RetryPolicy:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    exponential_base: float = 2.0


def calculate_delay(attempt: int, policy: RetryPolicy) -> float:
    """Calculate retry delay with exponential backoff and jitter.

    Formula: min(base_delay * (exponential_base ** attempt) + jitter, max_delay)
    Jitter is a random value between 0 and 0.5 seconds.

    Args:
        attempt: The current attempt number (0-indexed).
        policy: The retry policy configuration.

    Returns:
        Delay in seconds before the next retry.
    """
    jitter = random.uniform(0, 0.5)
    delay = policy.base_delay_seconds * (policy.exponential_base**attempt) + jitter
    return min(delay, policy.max_delay_seconds)


def should_retry(task: TaskPayload, policy: RetryPolicy) -> bool:
    """Determine if a task should be retried.

    Args:
        task: The task payload to evaluate.
        policy: The retry policy configuration.

    Returns:
        True if the task has remaining retry attempts.
    """
    return task.attempt < policy.max_attempts
