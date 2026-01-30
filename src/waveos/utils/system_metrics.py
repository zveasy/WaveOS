from __future__ import annotations

import os
import resource
from typing import Any, Dict


def collect_system_metrics() -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    try:
        load1, load5, load15 = os.getloadavg()
        metrics["cpu_load_1m"] = load1
        metrics["cpu_load_5m"] = load5
        metrics["cpu_load_15m"] = load15
    except OSError:
        pass
    usage = resource.getrusage(resource.RUSAGE_SELF)
    metrics["max_rss_kb"] = getattr(usage, "ru_maxrss", None)
    metrics["user_cpu_seconds"] = getattr(usage, "ru_utime", None)
    metrics["system_cpu_seconds"] = getattr(usage, "ru_stime", None)
    return metrics
