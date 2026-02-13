"""V2: Energy scheduler API — prioritize loads, dispatch BESS/charger, throttle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger

logger = get_logger("waveos.scheduler")


class Priority(int, Enum):
    """Load or dispatch priority (higher = more urgent)."""
    LOW = 1
    NORMAL = 5
    HIGH = 8
    CRITICAL = 10


@dataclass
class ScheduledLoad:
    """A load or demand to be scheduled."""
    load_id: str
    priority: Priority = Priority.NORMAL
    power_kw: float = 0.0
    duration_minutes: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DispatchInstruction:
    """Instruction to dispatch a device (BESS, charger, inverter)."""
    device_id: str
    capability: str  # charger, inverter, bess
    power_kw: float  # positive = charge/import, negative = discharge/export
    duration_seconds: Optional[float] = None
    reason: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GridSignal:
    """V3: Grid signal for response (frequency, price, island indicator)."""
    frequency_hz: Optional[float] = None
    price_signal: Optional[float] = None  # e.g. $/kWh
    is_island: bool = False  # microgrid islanding


class EnergyScheduler:
    """V2/V3: Scheduler that orders loads by priority; V3: island mode and grid response."""

    def __init__(
        self,
        max_export_kw: float = 0.0,
        max_import_kw: Optional[float] = None,
        island_mode: bool = False,
    ) -> None:
        self.max_export_kw = max_export_kw
        self.max_import_kw = max_import_kw
        self.island_mode = island_mode  # V3: microgrid islanding
        self._loads: List[ScheduledLoad] = []
        self._grid_signal: Optional[GridSignal] = None

    def set_grid_signal(self, signal: GridSignal) -> None:
        """V3: Set current grid signal for response (frequency, price, island)."""
        self._grid_signal = signal
        if signal.is_island:
            self.island_mode = True

    def add_load(self, load: ScheduledLoad) -> None:
        """Add a load to the queue (sorted by priority)."""
        self._loads.append(load)
        self._loads.sort(key=lambda L: (-L.priority, L.load_id))

    def schedule(self, available_kw: float) -> List[DispatchInstruction]:
        """Given available power (e.g. from BESS or grid), return dispatch instructions to satisfy loads in priority order."""
        instructions: List[DispatchInstruction] = []
        remaining_kw = available_kw
        for load in self._loads:
            if remaining_kw <= 0:
                break
            need = min(load.power_kw, remaining_kw)
            if need <= 0:
                continue
            instructions.append(
                DispatchInstruction(
                    device_id=load.load_id,
                    capability="load",
                    power_kw=need,
                    duration_seconds=load.duration_minutes * 60.0 if load.duration_minutes else None,
                    reason=f"priority={load.priority.name}",
                    meta=load.meta,
                )
            )
            remaining_kw -= need
        return instructions

    def clear(self) -> None:
        """Clear the load queue."""
        self._loads.clear()
