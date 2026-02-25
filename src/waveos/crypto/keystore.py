"""Key store — key management, rotation, and revocation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.keystore")


@dataclass
class KeyEntry:
    key_id: str
    public_key_hex: str
    algorithm: str = "ed25519"
    created_at: str = ""
    expires_at: str = ""
    revoked: bool = False
    revoked_at: str = ""
    purpose: str = "signing"  # signing | encryption | transport
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "key_id": self.key_id,
            "public_key_hex": self.public_key_hex,
            "algorithm": self.algorithm,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "revoked": self.revoked,
            "revoked_at": self.revoked_at,
            "purpose": self.purpose,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> KeyEntry:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})

    def is_valid(self) -> bool:
        if self.revoked:
            return False
        if self.expires_at:
            return utc_now().isoformat() <= self.expires_at
        return True


class KeyStore:
    """File-system key store with rotation and revocation support.

    Can also serve as an offline trust store for air-gapped verification.
    """

    def __init__(self, store_path: Path) -> None:
        self.path = store_path
        self.path.mkdir(parents=True, exist_ok=True)
        self._index_path = self.path / "keys.json"

    def _load(self) -> List[KeyEntry]:
        if not self._index_path.exists():
            return []
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            return [KeyEntry.from_dict(e) for e in data]
        except (json.JSONDecodeError, KeyError):
            return []

    def _save(self, entries: List[KeyEntry]) -> None:
        self._index_path.write_text(json.dumps([e.to_dict() for e in entries], indent=2) + "\n", encoding="utf-8")

    def add_key(self, entry: KeyEntry) -> None:
        entries = self._load()
        entries = [e for e in entries if e.key_id != entry.key_id]
        entries.append(entry)
        self._save(entries)

    def get_key(self, key_id: str) -> Optional[KeyEntry]:
        for e in self._load():
            if e.key_id == key_id:
                return e
        return None

    def get_valid_keys(self, purpose: str = "signing") -> List[KeyEntry]:
        return [e for e in self._load() if e.purpose == purpose and e.is_valid()]

    def revoke_key(self, key_id: str, reason: str = "") -> bool:
        entries = self._load()
        for e in entries:
            if e.key_id == key_id:
                e.revoked = True
                e.revoked_at = utc_now().isoformat()
                e.metadata["revocation_reason"] = reason
                self._save(entries)
                return True
        return False

    def rotate(self, old_key_id: str, new_entry: KeyEntry, reason: str = "scheduled rotation") -> bool:
        self.revoke_key(old_key_id, reason=reason)
        self.add_key(new_entry)
        return True

    def list_keys(self) -> List[KeyEntry]:
        return self._load()

    def export_trust_store(self, output_dir: Path) -> int:
        """Export valid public keys as *.key files for offline trust store."""
        output_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for entry in self.get_valid_keys():
            key_file = output_dir / f"{entry.key_id}.key"
            key_file.write_text(entry.public_key_hex + "\n", encoding="utf-8")
            count += 1
        return count
