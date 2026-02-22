"""Tests for canary-by-site (Fleet Phase 2)."""

import pytest

from waveos.orchestration import get_nodes_by_site, get_nodes_in_sites, NodeRole, register_node
from waveos.orchestration.nodes import _registry


def test_get_nodes_by_site() -> None:
    """get_nodes_by_site returns only nodes with that site_id."""
    _registry.clear()
    try:
        register_node("n1", NodeRole.EDGE, site_id="site-a")
        register_node("n2", NodeRole.EDGE, site_id="site-b")
        register_node("n3", NodeRole.CONTROLLER, site_id="site-a")
        register_node("n4", NodeRole.EDGE, site_id=None)
        by_site_a = get_nodes_by_site("site-a")
        assert len(by_site_a) == 2
        ids = {r.node_id for r in by_site_a}
        assert ids == {"n1", "n3"}
        by_site_b = get_nodes_by_site("site-b")
        assert len(by_site_b) == 1
        assert by_site_b[0].node_id == "n2"
        by_none = get_nodes_by_site("nonexistent")
        assert len(by_none) == 0
    finally:
        _registry.clear()


def test_get_nodes_in_sites() -> None:
    """get_nodes_in_sites returns nodes whose site_id is in the list."""
    _registry.clear()
    try:
        register_node("n1", NodeRole.EDGE, site_id="site-a")
        register_node("n2", NodeRole.EDGE, site_id="site-b")
        register_node("n3", NodeRole.EDGE, site_id="site-a")
        nodes = get_nodes_in_sites(["site-a"])
        assert len(nodes) == 2
        assert {r.node_id for r in nodes} == {"n1", "n3"}
        nodes = get_nodes_in_sites(["site-a", "site-b"])
        assert len(nodes) == 3
        nodes = get_nodes_in_sites([])
        assert len(nodes) == 3  # empty list means all in registry
    finally:
        _registry.clear()
