"""KMS provider interface for WaveOS key management."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.kms")


class KMSProvider(ABC):
    """Abstract KMS provider interface."""

    @abstractmethod
    def get_signing_key(self, key_id: str) -> str:
        """Retrieve signing key material."""

    @abstractmethod
    def get_verification_key(self, key_id: str) -> str:
        """Retrieve verification key material."""

    @abstractmethod
    def list_keys(self) -> List[Dict[str, Any]]:
        """List available keys."""

    @abstractmethod
    def rotate_key(self, key_id: str) -> Dict[str, Any]:
        """Rotate a key."""

    @abstractmethod
    def revoke_key(self, key_id: str) -> bool:
        """Revoke a key."""


@dataclass
class KeyRecord:
    key_id: str
    public_pem: str = ""
    private_pem: str = ""
    created_at: str = ""
    revoked: bool = False
    revoked_at: str = ""
    rotated_to: str = ""

    def to_dict(self) -> dict:
        return {
            "key_id": self.key_id, "public_pem": self.public_pem,
            "created_at": self.created_at, "revoked": self.revoked,
            "revoked_at": self.revoked_at, "rotated_to": self.rotated_to,
        }


class LocalKMS(KMSProvider):
    """File-system-based local KMS for development and air-gapped environments."""

    def __init__(self, store_path: Path) -> None:
        self.store_path = store_path
        self._keys: Dict[str, KeyRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.store_path.exists():
            return
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            for d in data:
                rec = KeyRecord(**{k: d[k] for k in d if k in KeyRecord.__dataclass_fields__})
                self._keys[rec.key_id] = rec
        except (json.JSONDecodeError, KeyError):
            pass

    def _save(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        data = [r.to_dict() for r in self._keys.values()]
        data_with_private = []
        for r in self._keys.values():
            d = r.to_dict()
            d["private_pem"] = r.private_pem
            data_with_private.append(d)
        self.store_path.write_text(json.dumps(data_with_private, indent=2) + "\n", encoding="utf-8")

    def store_key(self, key_id: str, public_pem: str, private_pem: str = "") -> None:
        self._keys[key_id] = KeyRecord(key_id=key_id, public_pem=public_pem, private_pem=private_pem, created_at=utc_now().isoformat())
        self._save()

    def get_signing_key(self, key_id: str) -> str:
        rec = self._keys.get(key_id)
        if not rec or rec.revoked:
            return ""
        return rec.private_pem

    def get_verification_key(self, key_id: str) -> str:
        rec = self._keys.get(key_id)
        if not rec:
            return ""
        return rec.public_pem

    def list_keys(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._keys.values()]

    def rotate_key(self, key_id: str) -> Dict[str, Any]:
        old = self._keys.get(key_id)
        if not old:
            return {"ok": False, "error": "key not found"}
        from waveos.crypto.signing import generate_keypair
        new_pair = generate_keypair(key_id=f"{key_id}-r{len(self._keys)}")
        self.store_key(new_pair.key_id, new_pair.public_pem, new_pair.private_pem)
        old.rotated_to = new_pair.key_id
        self._save()
        return {"ok": True, "old_key_id": key_id, "new_key_id": new_pair.key_id}

    def revoke_key(self, key_id: str) -> bool:
        rec = self._keys.get(key_id)
        if not rec:
            return False
        rec.revoked = True
        rec.revoked_at = utc_now().isoformat()
        self._save()
        return True


def get_kms_provider(provider: str = "local", **kwargs) -> KMSProvider:
    """Factory for KMS providers."""
    if provider == "local":
        path = Path(kwargs.get("store_path", "out/kms/keys.json"))
        return LocalKMS(path)
    raise ValueError(f"Unknown KMS provider: {provider}")
