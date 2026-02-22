from __future__ import annotations

import resource

from waveos.utils import get_logger

logger = get_logger("waveos.resource_limits")


def apply_resource_limits(max_memory_mb: int | None = None, max_cpu_seconds: int | None = None) -> None:
    """Apply process resource limits. On failure (e.g. unsupported platform), log and skip that limit."""
    if max_memory_mb:
        limit = max_memory_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        except (ValueError, OSError) as exc:
            logger.warning("Could not set memory limit (max_memory_mb=%s): %s", max_memory_mb, type(exc).__name__)
    if max_cpu_seconds:
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (max_cpu_seconds, max_cpu_seconds))
        except (ValueError, OSError) as exc:
            logger.warning("Could not set CPU limit (max_cpu_seconds=%s): %s", max_cpu_seconds, type(exc).__name__)
