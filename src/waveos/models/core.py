from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class EventLevel(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class ActionType(str, Enum):
    QOS_PRIORITIZATION = "QOS_PRIORITIZATION"
    RATE_LIMIT = "RATE_LIMIT"
    REROUTE = "REROUTE"
    POWER_THERMAL_CONSTRAINT = "POWER_THERMAL_CONSTRAINT"


class Link(BaseModel):
    id: str
    src_port: str
    dst_port: str
    capacity_gbps: float = Field(..., gt=0)


class Port(BaseModel):
    id: str
    device: str
    name: str


class Path(BaseModel):
    id: str
    links: List[str]


class Workload(BaseModel):
    id: str
    name: str
    priority: int = Field(ge=0, le=10)
    bandwidth_gbps: float = Field(..., ge=0)


class TelemetrySample(BaseModel):
    timestamp: datetime
    link_id: str
    port_id: Optional[str] = None
    errors: int = Field(default=0, ge=0)
    drops: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0)
    fec_corrected: int = Field(default=0, ge=0)
    fec_uncorrected: int = Field(default=0, ge=0)
    ber: Optional[float] = Field(default=None, ge=0.0)
    tx_power_dbm: Optional[float] = Field(default=None, ge=-50.0, le=50.0)
    rx_power_dbm: Optional[float] = Field(default=None, ge=-50.0, le=50.0)
    temperature_c: Optional[float] = Field(default=None, ge=-50.0, le=150.0)
    congestion_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    power_kw: Optional[float] = Field(default=None, ge=0.0)
    energy_kwh: Optional[float] = Field(default=None, ge=0.0)
    charger_status: Optional[str] = None
    charger_fault_code: Optional[str] = None
    battery_soc_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    voltage_v: Optional[float] = Field(default=None, ge=0.0)
    current_a: Optional[float] = Field(default=None, ge=0.0)
    meta: Dict[str, Any] = Field(default_factory=dict)


class HealthScore(BaseModel):
    entity_type: str
    entity_id: str
    score: float = Field(..., ge=0, le=100)
    status: HealthStatus
    drivers: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)
    window_start: datetime
    window_end: datetime


class Event(BaseModel):
    timestamp: datetime
    level: EventLevel
    message: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class ActionRecommendation(BaseModel):
    action: ActionType
    entity_type: str
    entity_id: str
    rationale: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class BaselineStats(BaseModel):
    entity_type: str
    entity_id: str
    metrics: Dict[str, float]
    window_start: datetime
    window_end: datetime


class RunStats(BaseModel):
    entity_type: str
    entity_id: str
    metrics: Dict[str, float]
    window_start: datetime
    window_end: datetime
