"""Side Effects — async post-scoring actions that don't block the main flow.

Inspired by x-algorithm's SideEffect pattern.
Fire-and-forget: failures in side effects never affect scoring results.
"""
from src.core.side_effects.base import SideEffect, SideEffectRunner
from src.core.side_effects.notification import NotificationSideEffect
from src.core.side_effects.stats_collector import StatsCollectorSideEffect

__all__ = [
    "SideEffect",
    "SideEffectRunner",
    "NotificationSideEffect",
    "StatsCollectorSideEffect",
]
