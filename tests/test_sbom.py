"""Tests for WaveOS SBOM module."""

from __future__ import annotations

from pathlib import Path

from waveos.sbom import (
    SBOM,
    SBOMComponent,
    generate_sbom,
    read_sbom,
    verify_sbom,
    write_sbom,
)


def test_generate_sbom() -> None:
    sbom = generate_sbom(bundle_id="test-sbom")
    assert len(sbom.components) > 0
    assert sbom.metadata.get("component", {}).get("name") == "waveos"
    d = sbom.to_dict()
    assert d["bomFormat"] == "CycloneDX"
    assert d["specVersion"] == "1.5"


def test_sbom_write_and_read(tmp_path: Path) -> None:
    sbom = generate_sbom()
    path = tmp_path / "sbom.json"
    write_sbom(sbom, path)
    assert path.exists()
    loaded = read_sbom(path)
    assert loaded is not None
    assert len(loaded.components) == len(sbom.components)


def test_sbom_roundtrip() -> None:
    comp = SBOMComponent(name="test-pkg", version="1.0", purl="pkg:pypi/test-pkg@1.0")
    sbom = SBOM(components=[comp])
    d = sbom.to_dict()
    restored = SBOM.from_dict(d)
    assert len(restored.components) == 1
    assert restored.components[0].name == "test-pkg"


def test_verify_sbom_pass() -> None:
    sbom = SBOM(components=[SBOMComponent(name="safe-pkg", version="1.0")])
    ok, violations = verify_sbom(sbom, blocklist=["evil-pkg"])
    assert ok
    assert violations == []


def test_verify_sbom_blocklist() -> None:
    sbom = SBOM(components=[SBOMComponent(name="evil-pkg", version="1.0")])
    ok, violations = verify_sbom(sbom, blocklist=["evil-pkg"])
    assert not ok
    assert any("evil-pkg" in v for v in violations)


def test_verify_sbom_allowlist() -> None:
    sbom = SBOM(components=[
        SBOMComponent(name="allowed", version="1.0"),
        SBOMComponent(name="not-allowed", version="1.0"),
    ])
    ok, violations = verify_sbom(sbom, allowlist=["allowed"])
    assert not ok
    assert any("not-allowed" in v for v in violations)


def test_read_sbom_missing(tmp_path: Path) -> None:
    result = read_sbom(tmp_path / "nope.json")
    assert result is None
