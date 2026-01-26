from __future__ import annotations

import random
from pathlib import Path
from typing import Dict, List, Tuple

from waveos.models import Link, TelemetrySample
from waveos.utils import should_shutdown, utc_now, write_json, write_jsonl


def _make_links(count: int) -> List[Link]:
    links: List[Link] = []
    for idx in range(count):
        links.append(
            Link(
                id=f"link-{idx+1}",
                src_port=f"sw{idx+1}/1",
                dst_port=f"sw{idx+1}/2",
                capacity_gbps=400.0,
            )
        )
    return links


def _sample_for_link(link_id: str, baseline: bool, drift: Dict[str, float]) -> TelemetrySample:
    base_errors = random.randint(0, 2)
    base_drops = random.randint(0, 1)
    base_retries = random.randint(0, 1)
    base_fec = random.randint(0, 3)
    base_temp = random.uniform(35, 50)
    base_ber = random.uniform(1e-9, 3e-9)
    base_cong = random.uniform(2, 8)

    if not baseline:
        base_errors *= drift.get("errors", 1.0)
        base_drops *= drift.get("drops", 1.0)
        base_retries *= drift.get("retries", 1.0)
        base_fec *= drift.get("fec_uncorrected", 1.0)
        base_temp += drift.get("temperature_c", 0.0)
        base_ber *= drift.get("ber", 1.0)
        base_cong += drift.get("congestion_pct", 0.0)

    return TelemetrySample(
        timestamp=utc_now(),
        link_id=link_id,
        errors=int(base_errors),
        drops=int(base_drops),
        retries=int(base_retries),
        fec_corrected=int(base_fec * 2),
        fec_uncorrected=int(base_fec),
        ber=float(base_ber),
        tx_power_dbm=random.uniform(-2.0, 2.0),
        rx_power_dbm=random.uniform(-4.0, 1.0),
        temperature_c=float(base_temp),
        congestion_pct=float(base_cong),
    )


def generate_telemetry(
    out_dir: Path,
    links: List[Link],
    samples_per_link: int,
    drift_map: Dict[str, Dict[str, float]] | None = None,
    baseline: bool = True,
) -> List[TelemetrySample]:
    drift_map = drift_map or {}
    samples: List[TelemetrySample] = []
    for link in links:
        drift = drift_map.get(link.id, {})
        for _ in range(samples_per_link):
            if should_shutdown():
                return samples
            samples.append(_sample_for_link(link.id, baseline, drift))
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "links.json", [link.model_dump() for link in links])
    write_jsonl(out_dir / "telemetry.jsonl", [sample.model_dump() for sample in samples])
    return samples


def build_demo_dataset(out_dir: Path) -> Tuple[Path, Path]:
    random.seed(42)
    links = _make_links(4)
    baseline_dir = out_dir / "baseline"
    run_dir = out_dir / "run"
    generate_telemetry(baseline_dir, links, samples_per_link=80, baseline=True)

    drift_map = {
        "link-2": {"errors": 3.2, "drops": 2.5, "ber": 2.2},
        "link-3": {"temperature_c": 12.0},
        "link-4": {"congestion_pct": 20.0, "retries": 2.0},
    }
    generate_telemetry(run_dir, links, samples_per_link=80, baseline=False, drift_map=drift_map)
    return baseline_dir, run_dir
