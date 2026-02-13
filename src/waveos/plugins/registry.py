"""V2: Plugin registry and lifecycle. Supports collectors, actuators, and policy extensions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type

from waveos.utils import get_logger

logger = get_logger("waveos.plugins")


class PluginKind(str, Enum):
    COLLECTOR = "collector"
    ACTUATOR = "actuator"
    POLICY_EXTENSION = "policy_extension"
    DEVICE_ADAPTER = "device_adapter"


@dataclass
class PluginMetadata:
    """Metadata for a registered plugin."""
    name: str
    kind: PluginKind
    version: str
    description: str = ""
    entry_point: Optional[str] = None  # e.g. "waveos_plugins.my_collector:load"
    config_schema_version: int = 1
    signed: bool = False


_registry: Dict[str, PluginMetadata] = {}
_factories: Dict[str, Callable[..., Any]] = {}  # name -> factory(config) -> instance


def get_registry() -> Dict[str, PluginMetadata]:
    """Return a copy of the plugin registry (read-only view)."""
    return dict(_registry)


def register_plugin(
    name: str,
    kind: PluginKind,
    version: str,
    description: str = "",
    entry_point: Optional[str] = None,
    signed: bool = False,
    factory: Optional[Callable[..., Any]] = None,
) -> None:
    """Register a plugin. Called at load time or via entry point discovery."""
    meta = PluginMetadata(
        name=name,
        kind=kind,
        version=version,
        description=description,
        entry_point=entry_point,
        signed=signed,
    )
    _registry[name] = meta
    if factory is not None:
        _factories[name] = factory
    logger.debug("Registered plugin %s kind=%s version=%s", name, kind.value, version)


def get_plugin_instance(name: str, config: Optional[Dict[str, Any]] = None) -> Any:
    """Return an instance of a plugin by name, or None if not found / no factory."""
    if name not in _factories:
        return None
    try:
        return _factories[name](**(config or {}))
    except Exception as exc:
        logger.warning("Failed to instantiate plugin %s: %s", name, type(exc).__name__)
        return None


def list_plugins(kind: Optional[PluginKind] = None) -> List[PluginMetadata]:
    """List registered plugins, optionally filtered by kind."""
    if kind is None:
        return list(_registry.values())
    return [m for m in _registry.values() if m.kind == kind]


def discover_entry_points() -> None:
    """Discover plugins declared via setuptools entry points (waveos.plugins)."""
    try:
        from importlib import metadata
        eps = metadata.entry_points(group="waveos.plugins")
    except Exception:
        return
    for ep in eps:
        try:
            load = ep.load()
            if callable(load):
                load()
        except Exception as exc:
            logger.warning("Failed to load plugin entry point %s: %s", ep.name, type(exc).__name__)
