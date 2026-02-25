"""Tests for WaveOS Registry Store."""

from __future__ import annotations

import json
from pathlib import Path

from waveos.registry.store import RegistryEntry, RegistryStore


def _make_bundle(tmp_path: Path, bundle_id: str = "test-bundle", version: str = "1.0") -> Path:
    bundle_dir = tmp_path / f"bundle_{bundle_id}"
    bundle_dir.mkdir()
    (bundle_dir / "bundle.json").write_text(json.dumps({
        "bundle_id": bundle_id,
        "version": version,
        "waveos_version": "0.1.0",
    }))
    (bundle_dir / "app.py").write_text("# app\n")
    return bundle_dir


def test_publish_and_list(tmp_path: Path) -> None:
    registry = RegistryStore(tmp_path / "registry")
    bundle_dir = _make_bundle(tmp_path, "b1")
    entry = registry.publish(bundle_dir, channel="dev")
    assert entry.bundle_id == "b1"
    assert entry.channel == "dev"
    entries = registry.list_bundles()
    assert len(entries) == 1
    assert entries[0].bundle_id == "b1"


def test_list_by_channel(tmp_path: Path) -> None:
    registry = RegistryStore(tmp_path / "registry")
    registry.publish(_make_bundle(tmp_path, "b1"), channel="dev")
    registry.publish(_make_bundle(tmp_path, "b2"), channel="prod")
    assert len(registry.list_bundles(channel="dev")) == 1
    assert len(registry.list_bundles(channel="prod")) == 1
    assert len(registry.list_bundles()) == 2


def test_get_bundle(tmp_path: Path) -> None:
    registry = RegistryStore(tmp_path / "registry")
    registry.publish(_make_bundle(tmp_path, "b1"))
    path = registry.get_bundle("b1")
    assert path is not None
    assert (path / "bundle.json").exists()


def test_get_nonexistent(tmp_path: Path) -> None:
    registry = RegistryStore(tmp_path / "registry")
    assert registry.get_bundle("nope") is None


def test_get_entry(tmp_path: Path) -> None:
    registry = RegistryStore(tmp_path / "registry")
    registry.publish(_make_bundle(tmp_path, "b1"), channel="staging")
    entry = registry.get_entry("b1")
    assert entry is not None
    assert entry.channel == "staging"


def test_delete_bundle(tmp_path: Path) -> None:
    registry = RegistryStore(tmp_path / "registry")
    registry.publish(_make_bundle(tmp_path, "b1"))
    assert registry.delete_bundle("b1")
    assert registry.get_bundle("b1") is None
    assert len(registry.list_bundles()) == 0


def test_registry_entry_roundtrip() -> None:
    entry = RegistryEntry(bundle_id="x", version="1.0", channel="prod")
    d = entry.to_dict()
    restored = RegistryEntry.from_dict(d)
    assert restored.bundle_id == "x"
    assert restored.channel == "prod"
