"""Key Management Service provider interface."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.kms")


class KMSProvider(ABC):
    """Abstract KMS provider for key storage, rotation, and revocation."""

    @abstractmethod
    def get_signing_key(self, key_id: str) -> Optional[bytes]:
        ...

    @abstractmethod
    def get_verification_key(self, key_id: str) -> Optional[bytes]:
        ...

    @abstractmethod
    def list_keys(self) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def rotate_key(self, key_id: str) -> Optional[str]:
        ...

    @abstractmethod
    def revoke_key(self, key_id: str) -> bool:
        ...


@dataclass
class KeyRecord:
    key_id: str
    algorithm: str = "hmac-sha512"
    created_at: str = ""
    revoked: bool = False
    rotated_to: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "key_id": self.key_id, "algorithm": self.algorithm,
            "created_at": self.created_at, "revoked": self.revoked,
            "rotated_to": self.rotated_to, "metadata": self.metadata,
        }


class LocalKMS(KMSProvider):
    """File-system-based KMS for development and air-gapped environments."""

    def __init__(self, keys_dir: Path) -> None:
        self.keys_dir = keys_dir
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = keys_dir / "key_index.json"
        self._records: Dict[str, KeyRecord] = {}
        self._load()

    def _load(self) -> None:
        if self._index_path.exists():
            try:
                data = json.loads(self._index_path.read_text(encoding="utf-8"))
                for d in data:
                    r = KeyRecord(**{k: v for k, v in d.items() if k in KeyRecord.__dataclass_fields__})
                    self._records[r.key_id] = r
            except (json.JSONDecodeError, KeyError):
                pass

    def _save(self) -> None:
        self._index_path.write_text(
            json.dumps([r.to_dict() for r in self._records.values()], indent=2) + "\n",
            encoding="utf-8",
        )

    def store_key(self, key_id: str, private_key: bytes, public_key: bytes, algorithm: str = "hmac-sha512") -> None:
        (self.keys_dir / f"{key_id}.key").write_bytes(private_key)
        (self.keys_dir / f"{key_id}.pub").write_bytes(public_key)
        self._records[key_id] = KeyRecord(key_id=key_id, algorithm=algorithm, created_at=utc_now().isoformat())
        self._save()

    def get_signing_key(self, key_id: str) -> Optional[bytes]:
        rec = self._records.get(key_id)
        if not rec or rec.revoked:
            return None
        path = self.keys_dir / f"{key_id}.key"
        return path.read_bytes() if path.exists() else None

    def get_verification_key(self, key_id: str) -> Optional[bytes]:
        rec = self._records.get(key_id)
        if not rec:
            return None
        path = self.keys_dir / f"{key_id}.pub"
        return path.read_bytes() if path.exists() else None

    def list_keys(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._records.values()]

    def rotate_key(self, key_id: str) -> Optional[str]:
        old = self._records.get(key_id)
        if not old or old.revoked:
            return None
        from waveos.crypto.signing import generate_keypair
        new_kp = generate_keypair(algorithm=old.algorithm)
        new_id = new_kp.key_id
        self.store_key(new_id, new_kp.private_key, new_kp.public_key, new_kp.algorithm)
        old.rotated_to = new_id
        self._save()
        logger.info("Rotated key %s -> %s", key_id, new_id)
        return new_id

    def revoke_key(self, key_id: str) -> bool:
        rec = self._records.get(key_id)
        if not rec:
            return False
        rec.revoked = True
        self._save()
        logger.info("Revoked key %s", key_id)
        return True


def get_kms_provider(provider: str = "local", **kwargs) -> KMSProvider:
    """Factory for KMS providers. Extensible for HSM/AWS/Vault."""
    if provider == "local":
        keys_dir = Path(kwargs.get("keys_dir", "out/keys"))
        return LocalKMS(keys_dir)
    raise ValueError(f"Unknown KMS provider: {provider}")
