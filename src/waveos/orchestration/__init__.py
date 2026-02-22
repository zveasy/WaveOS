"""V3: Federated orchestration — node registry, topology, control plane API."""

from waveos.orchestration.nodes import (
    NodeRole,
    NodeRecord,
    get_node_registry,
    get_nodes_by_site,
    get_nodes_in_sites,
    load_nodes_from_file,
    register_node,
    save_nodes_to_file,
)

__all__ = [
    "NodeRole",
    "NodeRecord",
    "get_node_registry",
    "get_nodes_by_site",
    "get_nodes_in_sites",
    "load_nodes_from_file",
    "register_node",
    "save_nodes_to_file",
]
