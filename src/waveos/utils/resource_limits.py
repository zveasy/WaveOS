from __future__ import annotations

import resource


def apply_resource_limits(max_memory_mb: int | None = None, max_cpu_seconds: int | None = None) -> None:
    if max_memory_mb:
        limit = max_memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    if max_cpu_seconds:
        resource.setrlimit(resource.RLIMIT_CPU, (max_cpu_seconds, max_cpu_seconds))
