from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

from waveos.models import BaselineStats, HealthScore, HealthStatus, RunStats, TelemetrySample
from waveos.utils import get_logger, histograms, span

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
        if sample.power_kw is not None:
            buckets[key]["power_kw"] += sample.power_kw
        if sample.energy_kwh is not None:
            buckets[key]["energy_kwh"] += sample.energy_kwh
        if sample.current_a is not None:
            buckets[key]["current_a"] += sample.current_a
        if sample.voltage_v is not None:
            buckets[key]["voltage_v"] += sample.voltage_v
        if sample.battery_soc_pct is not None:
            buckets[key]["battery_soc_pct"] += sample.battery_soc_pct
        if sample.charger_status == "fault" or sample.charger_fault_code:
            buckets[key]["charger_faults"] += 1.0
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


def score_links(
    baseline: Dict[str, BaselineStats],
    run: Dict[str, RunStats],
    run_id: str | None = None,
) -> List[HealthScore]:
    scores: List[HealthScore] = []
    duration = histograms()["scoring_duration"]
    with duration.time(), span("score_links") as active_span:
        if run_id:
            active_span.set_attribute("waveos.run_id", run_id)
        active_span.set_attribute("waveos.entity_count", len(run))
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
                elif metric == "charger_faults":
                    if run_value >= 1:
                        drivers.append("charger_fault")
                        severity += 40
                elif metric == "current_a":
                    if base_value > 0 and run_value >= base_value * 1.5:
                        drivers.append("overcurrent")
                        severity += 30
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
                    details={
                        "charger_faults": run_stats.metrics.get("charger_faults", 0.0),
                        "current_a": run_stats.metrics.get("current_a"),
                        "power_kw": run_stats.metrics.get("power_kw"),
                        "voltage_v": run_stats.metrics.get("voltage_v"),
                        "battery_soc_pct": run_stats.metrics.get("battery_soc_pct"),
                        "charger_status": "fault" if run_stats.metrics.get("charger_faults", 0.0) >= 1 else "ok",
                    },
                    window_start=run_stats.window_start,
                    window_end=run_stats.window_end,
                )
            )
    return scores
