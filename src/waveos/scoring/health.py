from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

from waveos.models import BaselineStats, HealthScore, HealthStatus, RunStats, TelemetrySample
from waveos.utils import get_logger

logger = get_logger("waveos.scoring")


def _aggregate(samples: Iterable[TelemetrySample]) -> Dict[str, Dict[str, float]]:
    buckets: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    counts: Dict[str, int] = defaultdict(int)
    for sample in samples:
        key = sample.link_id
        counts[key] += 1
        buckets[key]["errors"] += sample.errors
        buckets[key]["drops"] += sample.drops
        buckets[key]["retries"] += sample.retries
        buckets[key]["fec_corrected"] += sample.fec_corrected
        buckets[key]["fec_uncorrected"] += sample.fec_uncorrected
        if sample.ber is not None:
            buckets[key]["ber"] += sample.ber
        if sample.temperature_c is not None:
            buckets[key]["temperature_c"] += sample.temperature_c
        if sample.rx_power_dbm is not None:
            buckets[key]["rx_power_dbm"] += sample.rx_power_dbm
        if sample.tx_power_dbm is not None:
            buckets[key]["tx_power_dbm"] += sample.tx_power_dbm
        if sample.congestion_pct is not None:
            buckets[key]["congestion_pct"] += sample.congestion_pct
    metrics: Dict[str, Dict[str, float]] = {}
    for key, totals in buckets.items():
        count = max(counts[key], 1)
        metrics[key] = {metric: value / count for metric, value in totals.items()}
    return metrics


def build_stats(samples: List[TelemetrySample]) -> Tuple[List[BaselineStats], List[RunStats]]:
    if not samples:
        return [], []
    window_start = min(s.timestamp for s in samples)
    window_end = max(s.timestamp for s in samples)
    metrics = _aggregate(samples)
    baseline = [
        BaselineStats(entity_type="link", entity_id=link_id, metrics=values, window_start=window_start, window_end=window_end)
        for link_id, values in metrics.items()
    ]
    run = [
        RunStats(entity_type="link", entity_id=link_id, metrics=values, window_start=window_start, window_end=window_end)
        for link_id, values in metrics.items()
    ]
    return baseline, run


def score_links(baseline: Dict[str, BaselineStats], run: Dict[str, RunStats]) -> List[HealthScore]:
    scores: List[HealthScore] = []
    for link_id, run_stats in run.items():
        base_stats = baseline.get(link_id)
        if not base_stats:
            logger.warning("Missing baseline for link %s", link_id)
            continue
        drivers: List[str] = []
        severity = 0.0
        for metric, run_value in run_stats.metrics.items():
            base_value = base_stats.metrics.get(metric, 0.0)
            if metric == "temperature_c":
                delta = run_value - base_value
                if delta >= 10:
                    drivers.append("temperature_drift")
                    severity += 40
                elif delta >= 5:
                    drivers.append("temperature_warning")
                    severity += 20
            else:
                ratio = (run_value + 1e-6) / (base_value + 1e-6)
                if ratio >= 3:
                    drivers.append(f"{metric}_spike")
                    severity += 35
                elif ratio >= 1.5:
                    drivers.append(f"{metric}_increase")
                    severity += 15
        score = max(0.0, 100.0 - severity)
        if score >= 85:
            status = HealthStatus.PASS
        elif score >= 60:
            status = HealthStatus.WARN
        else:
            status = HealthStatus.FAIL
        scores.append(
            HealthScore(
                entity_type="link",
                entity_id=link_id,
                score=score,
                status=status,
                drivers=drivers,
                window_start=run_stats.window_start,
                window_end=run_stats.window_end,
            )
        )
    return scores
