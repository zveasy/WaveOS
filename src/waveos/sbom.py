"""WaveOS SBOM — Software Bill of Materials generation and verification."""

from __future__ import annotations

import importlib.metadata
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.sbom")


@dataclass
class SBOMComponent:
    """A single component in the SBOM."""
    name: str
    version: str
    type: str = "library"  # library | framework | application
    purl: str = ""
    license: str = ""
    supplier: str = ""

    def to_dict(self) -> dict:
        d: Dict[str, Any] = {"type": self.type, "name": self.name, "version": self.version}
        if self.purl:
            d["purl"] = self.purl
        if self.license:
            d["licenses"] = [{"license": {"id": self.license}}]
        if self.supplier:
            d["supplier"] = {"name": self.supplier}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> SBOMComponent:
        license_id = ""
        if d.get("licenses"):
            lic = d["licenses"][0]
            if isinstance(lic, dict):
                license_id = lic.get("license", {}).get("id", "")
        return cls(
            name=d.get("name", ""),
            version=d.get("version", ""),
            type=d.get("type", "library"),
            purl=d.get("purl", ""),
            license=license_id,
            supplier=d.get("supplier", {}).get("name", "") if isinstance(d.get("supplier"), dict) else "",
        )


@dataclass
class SBOM:
    """CycloneDX-style Software Bill of Materials."""
    serial_number: str = ""
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
    components: List[SBOMComponent] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "serialNumber": self.serial_number or f"urn:uuid:{uuid.uuid4()}",
            "version": self.version,
            "metadata": self.metadata,
            "components": [c.to_dict() for c in self.components],
        }

    @classmethod
    def from_dict(cls, d: dict) -> SBOM:
        return cls(
            serial_number=d.get("serialNumber", ""),
            version=d.get("version", 1),
            metadata=d.get("metadata", {}),
            components=[SBOMComponent.from_dict(c) for c in d.get("components", [])],
        )


def generate_sbom(bundle_id: str = "", extra_components: Optional[List[SBOMComponent]] = None) -> SBOM:
    """Generate SBOM from installed Python packages (CycloneDX format)."""
    components: List[SBOMComponent] = []
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name", "")
        version = dist.metadata.get("Version", "")
        if not name:
            continue
        lic = dist.metadata.get("License", "") or ""
        if lic and len(lic) > 50:
            lic = ""
        classifier_licenses = [
            c.split(" :: ")[-1]
            for c in (dist.metadata.get_all("Classifier") or [])
            if "License" in c and "::" in c
        ]
        if not lic and classifier_licenses:
            lic = classifier_licenses[0]
        purl = f"pkg:pypi/{name.lower()}@{version}"
        components.append(SBOMComponent(name=name, version=version, purl=purl, license=lic))

    if extra_components:
        components.extend(extra_components)

    components.sort(key=lambda c: c.name.lower())

    return SBOM(
        serial_number=f"urn:uuid:{uuid.uuid4()}",
        metadata={
            "timestamp": utc_now().isoformat(),
            "tools": [{"vendor": "waveos", "name": "waveos-sbom", "version": "1.0"}],
            "component": {"type": "application", "name": "waveos", "version": bundle_id or "unknown"},
        },
        components=components,
    )


def write_sbom(sbom: SBOM, output_path: Path) -> Path:
    """Write SBOM to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(sbom.to_dict(), indent=2) + "\n", encoding="utf-8")
    return output_path


def read_sbom(path: Path) -> Optional[SBOM]:
    """Read SBOM from JSON file."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return SBOM.from_dict(data)
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Failed to read SBOM: %s", exc)
        return None


def verify_sbom(
    sbom: SBOM,
    blocklist: Optional[List[str]] = None,
    allowlist: Optional[List[str]] = None,
    max_critical_cves: int = 0,
    cve_blocklist: Optional[List[str]] = None,
) -> Tuple[bool, List[str]]:
    """Verify SBOM against policy (blocklist/allowlist).

    Returns (ok, list_of_violations).
    - blocklist: package names that must NOT be present
    - allowlist: if set, ONLY these packages are allowed
    - cve_blocklist: list of CVE IDs that block (matched against component names for simplicity)
    """
    violations: List[str] = []
    component_names = {c.name.lower() for c in sbom.components}

    if blocklist:
        for blocked in blocklist:
            if blocked.lower() in component_names:
                violations.append(f"Blocked package present: {blocked}")

    if allowlist:
        allowed_set = {a.lower() for a in allowlist}
        for name in component_names:
            if name not in allowed_set:
                violations.append(f"Package not in allowlist: {name}")

    if cve_blocklist:
        for cve in cve_blocklist:
            violations.append(f"CVE policy check (manual): {cve}")

    return len(violations) == 0, violations
