"""Dispatcher — async task scheduling with concurrency control and retry.

Inspired by x-algorithm's Dispatcher + Engine pattern.
Manages scoring task execution with priority queue, max_in_flight limiting,
and exponential backoff retry.
"""

from src.dispatcher.dispatcher import Dispatcher
from src.dispatcher.models import TaskPayload, TaskResult, TaskStatus, TaskPriority
from src.dispatcher.task_queue import PriorityTaskQueue

__all__ = [
    "Dispatcher",
    "TaskPayload",
    "TaskResult",
    "TaskStatus",
    "TaskPriority",
    "PriorityTaskQueue",
]
