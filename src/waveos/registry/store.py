"""File-system-based registry store for bundles."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.store")


@dataclass
class RegistryEntry:
    """A bundle entry in the registry."""
    bundle_id: str
    version: str
    channel: str = "dev"
    published_at: str = ""
    publisher: str = ""
    signature_ref: str = ""
    attestation_ref: str = ""
    sbom_ref: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    size_bytes: int = 0

    def to_dict(self) -> dict:
        return {
            "bundle_id": self.bundle_id,
            "version": self.version,
            "channel": self.channel,
            "published_at": self.published_at or utc_now().isoformat(),
            "publisher": self.publisher,
            "signature_ref": self.signature_ref,
            "attestation_ref": self.attestation_ref,
            "sbom_ref": self.sbom_ref,
            "metadata": self.metadata,
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RegistryEntry:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


class RegistryStore:
    """File-system-based bundle registry.

    Layout:
      registry_root/
        index.json                    # list of all entries
        bundles/<bundle_id>/
          bundle.json                 # manifest
          bundle.sig                  # signature
          attestation.json            # attestation (optional)
          sbom.json                   # SBOM (optional)
          <payload files>
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / "index.json"

    def _load_index(self) -> List[RegistryEntry]:
        if not self._index_path.exists():
            return []
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            return [RegistryEntry.from_dict(e) for e in data]
        except (json.JSONDecodeError, KeyError):
            return []

    def _save_index(self, entries: List[RegistryEntry]) -> None:
        self._index_path.write_text(
            json.dumps([e.to_dict() for e in entries], indent=2) + "\n",
            encoding="utf-8",
        )

    def publish(self, bundle_dir: Path, channel: str = "dev", publisher: str = "") -> RegistryEntry:
        """Publish a bundle to the registry."""
        manifest_path = bundle_dir / "bundle.json"
        if not manifest_path.exists():
            raise ValueError(f"No manifest in {bundle_dir}")

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        bundle_id = data.get("bundle_id", "")
        version = data.get("version", data.get("waveos_version", "unknown"))

        dest = self.root / "bundles" / bundle_id
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(bundle_dir, dest)

        total_size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())

        entry = RegistryEntry(
            bundle_id=bundle_id,
            version=version,
            channel=channel,
            published_at=utc_now().isoformat(),
            publisher=publisher,
            signature_ref=f"bundles/{bundle_id}/bundle.sig" if (dest / "bundle.sig").exists() else "",
            attestation_ref=f"bundles/{bundle_id}/attestation.json" if (dest / "attestation.json").exists() else "",
            sbom_ref=f"bundles/{bundle_id}/sbom.json" if (dest / "sbom.json").exists() else "",
            size_bytes=total_size,
        )

        entries = self._load_index()
        entries = [e for e in entries if e.bundle_id != bundle_id]
        entries.append(entry)
        self._save_index(entries)
        logger.info("Published bundle %s to channel %s", bundle_id, channel)
        return entry

    def list_bundles(self, channel: Optional[str] = None) -> List[RegistryEntry]:
        """List bundles, optionally filtered by channel."""
        entries = self._load_index()
        if channel:
            entries = [e for e in entries if e.channel == channel]
        return sorted(entries, key=lambda e: e.published_at, reverse=True)

    def get_bundle(self, bundle_id: str) -> Optional[Path]:
        """Get path to a published bundle directory."""
        dest = self.root / "bundles" / bundle_id
        if dest.is_dir() and (dest / "bundle.json").exists():
            return dest
        return None

    def get_entry(self, bundle_id: str) -> Optional[RegistryEntry]:
        """Get registry entry for a bundle."""
        for entry in self._load_index():
            if entry.bundle_id == bundle_id:
                return entry
        return None

    def delete_bundle(self, bundle_id: str) -> bool:
        """Remove a bundle from the registry."""
        dest = self.root / "bundles" / bundle_id
        if dest.exists():
            shutil.rmtree(dest)
        entries = self._load_index()
        new_entries = [e for e in entries if e.bundle_id != bundle_id]
        if len(new_entries) == len(entries):
            return False
        self._save_index(new_entries)
        return True
