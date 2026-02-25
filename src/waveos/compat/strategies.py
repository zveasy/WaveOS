"""Dependency mismatch tolerance strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

from waveos.utils import get_logger

logger = get_logger("waveos.compat.strategies")


class RuntimeStrategy(str, Enum):
    BUNDLED = "bundled"
    SIDE_BY_SIDE = "side_by_side"
    CONTAINER = "container"
    VM = "vm"


@dataclass
class StrategyConfig:
    strategy: RuntimeStrategy = RuntimeStrategy.BUNDLED
    install_prefix: str = "/opt/waveos/apps"
    isolation_level: str = "none"  # none | namespace | container | vm
    runtime_version: str = ""
    bundled_libs: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy.value,
            "install_prefix": self.install_prefix,
            "isolation_level": self.isolation_level,
            "runtime_version": self.runtime_version,
            "bundled_libs": self.bundled_libs,
        }


def get_strategy(name: str) -> StrategyConfig:
    """Get a named strategy configuration."""
    strategies = {
        "bundled": StrategyConfig(strategy=RuntimeStrategy.BUNDLED, isolation_level="none"),
        "side_by_side": StrategyConfig(strategy=RuntimeStrategy.SIDE_BY_SIDE, install_prefix="/opt/waveos/apps"),
        "container": StrategyConfig(strategy=RuntimeStrategy.CONTAINER, isolation_level="container"),
        "vm": StrategyConfig(strategy=RuntimeStrategy.VM, isolation_level="vm"),
    }
    return strategies.get(name, strategies["bundled"])


def describe_strategies() -> List[Dict[str, Any]]:
    """Return descriptions of all available strategies."""
    return [
        {"name": "bundled", "description": "Ship required libs/runtime with app. No host dependencies.", "mvp": True},
        {"name": "side_by_side", "description": "Install multiple versions under /opt/waveos/apps/<app>/<version>/. Zero conflict.", "mvp": True},
        {"name": "container", "description": "Run in container (Docker/Podman). Full isolation.", "mvp": False},
        {"name": "vm", "description": "Run in VM for extreme legacy stacks.", "mvp": False},
    ]
