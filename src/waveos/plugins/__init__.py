"""V2: Plugin API and registry. Plugins can register collectors, actuators, and policy extensions."""

from waveos.plugins.registry import get_registry, register_plugin, PluginMetadata, PluginKind

__all__ = ["get_registry", "register_plugin", "PluginMetadata", "PluginKind"]
