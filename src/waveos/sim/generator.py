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


def _sample_for_link(
    link_id: str,
    baseline: bool,
    drift: Dict[str, float],
    base: Dict[str, float] | None = None,
) -> TelemetrySample:
    if base is None:
        base_errors = random.randint(0, 2)
        base_drops = random.randint(0, 1)
        base_retries = random.randint(0, 1)
        base_fec = random.randint(0, 3)
        base_temp = random.uniform(35, 50)
        base_ber = random.uniform(1e-9, 3e-9)
        base_cong = random.uniform(2, 8)
        base_voltage = random.uniform(350.0, 800.0)
        base_current = random.uniform(50.0, 250.0)
        base_power_kw = (base_voltage * base_current) / 1000.0
        base_energy_kwh = random.uniform(10.0, 200.0)
        base_soc = random.uniform(20.0, 90.0)
        base_status = "charging"
        base_fault = None
    else:
        base_errors = base["errors"]
        base_drops = base["drops"]
        base_retries = base["retries"]
        base_fec = base["fec_uncorrected"]
        base_temp = base["temperature_c"]
        base_ber = base["ber"]
        base_cong = base["congestion_pct"]
        base_voltage = base["voltage_v"]
        base_current = base["current_a"]
        base_power_kw = base["power_kw"]
        base_energy_kwh = base["energy_kwh"]
        base_soc = base["battery_soc_pct"]
        base_status = base.get("charger_status", "charging")
        base_fault = base.get("charger_fault_code")

    if not baseline:
        base_errors *= drift.get("errors", 1.0)
        base_drops *= drift.get("drops", 1.0)
        base_retries *= drift.get("retries", 1.0)
        base_fec *= drift.get("fec_uncorrected", 1.0)
        base_temp += drift.get("temperature_c", 0.0)
        base_ber *= drift.get("ber", 1.0)
        base_cong += drift.get("congestion_pct", 0.0)
        base_power_kw *= drift.get("power_kw", 1.0)
        base_current *= drift.get("current_a", 1.0)
        base_voltage *= drift.get("voltage_v", 1.0)
        if drift.get("charger_fault", 0.0) > 0:
            base_status = "fault"
            base_fault = "FAULT_OVERCURRENT"

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
        power_kw=float(base_power_kw),
        energy_kwh=float(base_energy_kwh),
        voltage_v=float(base_voltage),
        current_a=float(base_current),
        battery_soc_pct=float(base_soc),
        charger_status=base_status,
        charger_fault_code=base_fault,
    )


def _make_base_map(links: List[Link]) -> Dict[str, Dict[str, float]]:
    base_map: Dict[str, Dict[str, float]] = {}
    for link in links:
        base_errors = random.randint(0, 2)
        base_drops = random.randint(0, 1)
        base_retries = random.randint(0, 1)
        base_fec = random.randint(0, 3)
        base_temp = random.uniform(35, 50)
        base_ber = random.uniform(1e-9, 3e-9)
        base_cong = random.uniform(2, 8)
        base_voltage = random.uniform(350.0, 800.0)
        base_current = random.uniform(50.0, 250.0)
        base_power_kw = (base_voltage * base_current) / 1000.0
        base_energy_kwh = random.uniform(10.0, 200.0)
        base_soc = random.uniform(20.0, 90.0)
        base_map[link.id] = {
            "errors": float(base_errors),
            "drops": float(base_drops),
            "retries": float(base_retries),
            "fec_uncorrected": float(base_fec),
            "temperature_c": float(base_temp),
            "ber": float(base_ber),
            "congestion_pct": float(base_cong),
            "voltage_v": float(base_voltage),
            "current_a": float(base_current),
            "power_kw": float(base_power_kw),
            "energy_kwh": float(base_energy_kwh),
            "battery_soc_pct": float(base_soc),
            "charger_status": "charging",
            "charger_fault_code": None,
        }
    return base_map


def generate_telemetry(
    out_dir: Path,
    links: List[Link],
    samples_per_link: int,
    drift_map: Dict[str, Dict[str, float]] | None = None,
    baseline: bool = True,
    base_map: Dict[str, Dict[str, float]] | None = None,
) -> List[TelemetrySample]:
    drift_map = drift_map or {}
    if base_map is None:
        base_map = _make_base_map(links)
    samples: List[TelemetrySample] = []
    for link in links:
        drift = drift_map.get(link.id, {})
        base = base_map.get(link.id) if base_map else None
        for _ in range(samples_per_link):
            if should_shutdown():
                return samples
            samples.append(_sample_for_link(link.id, baseline, drift, base=base))
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "links.json", [link.model_dump() for link in links])
    write_jsonl(out_dir / "telemetry.jsonl", [sample.model_dump() for sample in samples])
    return samples


def build_demo_dataset(out_dir: Path) -> Tuple[Path, Path]:
    random.seed(42)
    links = _make_links(4)
    baseline_dir = out_dir / "baseline"
    run_dir = out_dir / "run"
    base_map = _make_base_map(links)
    generate_telemetry(baseline_dir, links, samples_per_link=80, baseline=True, base_map=base_map)

    drift_map = {
        "link-2": {"errors": 1.6, "drops": 1.6},
        "link-4": {"errors": 3.2, "drops": 2.5, "current_a": 1.8, "charger_fault": 1.0},
    }
    generate_telemetry(run_dir, links, samples_per_link=80, baseline=False, drift_map=drift_map, base_map=base_map)
    return baseline_dir, run_dir
