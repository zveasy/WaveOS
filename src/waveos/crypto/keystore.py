"""Key management — key store with rotation, revocation, and optional HSM/KMS integration."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.crypto.signing import KeyPair
from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.keystore")


class KeyStatus(str, Enum):
    ACTIVE = "active"
    ROTATED = "rotated"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass
class KeyRecord:
    """A key with lifecycle metadata."""
    key_id: str
    status: KeyStatus = KeyStatus.ACTIVE
    algorithm: str = "ed25519"
    public_key: str = ""
    created_at: str = ""
    rotated_at: str = ""
    revoked_at: str = ""
    expires_at: str = ""
    successor_key_id: str = ""
    kms_ref: str = ""  # external KMS/HSM reference

    def to_dict(self) -> dict:
        return {
            "key_id": self.key_id, "status": self.status.value, "algorithm": self.algorithm,
            "public_key": self.public_key, "created_at": self.created_at, "rotated_at": self.rotated_at,
            "revoked_at": self.revoked_at, "expires_at": self.expires_at,
            "successor_key_id": self.successor_key_id, "kms_ref": self.kms_ref,
        }

    @classmethod
    def from_dict(cls, d: dict) -> KeyRecord:
        return cls(
            key_id=d.get("key_id", ""), status=KeyStatus(d.get("status", "active")),
            algorithm=d.get("algorithm", "ed25519"), public_key=d.get("public_key", ""),
            created_at=d.get("created_at", ""), rotated_at=d.get("rotated_at", ""),
            revoked_at=d.get("revoked_at", ""), expires_at=d.get("expires_at", ""),
            successor_key_id=d.get("successor_key_id", ""), kms_ref=d.get("kms_ref", ""),
        )


class KeyStore:
    """Manages signing keys with rotation and revocation support.

    Supports:
    - Local file-based key storage
    - Key rotation with successor chain
    - Revocation
    - Optional external KMS/HSM reference (key operations delegated)
    """

    def __init__(self, store_path: Optional[Path] = None) -> None:
        self._keys: Dict[str, KeyRecord] = {}
        self._store_path = store_path
        if store_path and store_path.exists():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._store_path.read_text(encoding="utf-8"))
            for d in data:
                rec = KeyRecord.from_dict(d)
                self._keys[rec.key_id] = rec
        except (json.JSONDecodeError, OSError):
            pass

    def save(self) -> None:
        if self._store_path:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            self._store_path.write_text(json.dumps([k.to_dict() for k in self._keys.values()], indent=2) + "\n", encoding="utf-8")

    def add(self, keypair: KeyPair, kms_ref: str = "") -> KeyRecord:
        record = KeyRecord(
            key_id=keypair.key_id, status=KeyStatus.ACTIVE, algorithm=keypair.algorithm,
            public_key=keypair.public_key, created_at=keypair.created_at or utc_now().isoformat(),
            kms_ref=kms_ref,
        )
        self._keys[keypair.key_id] = record
        self.save()
        return record

    def get(self, key_id: str) -> Optional[KeyRecord]:
        return self._keys.get(key_id)

    def get_active(self) -> Optional[KeyRecord]:
        for rec in self._keys.values():
            if rec.status == KeyStatus.ACTIVE:
                return rec
        return None

    def rotate(self, old_key_id: str, new_keypair: KeyPair) -> Optional[KeyRecord]:
        old = self._keys.get(old_key_id)
        if not old:
            return None
        old.status = KeyStatus.ROTATED
        old.rotated_at = utc_now().isoformat()
        old.successor_key_id = new_keypair.key_id
        new_record = self.add(new_keypair)
        self.save()
        return new_record

    def revoke(self, key_id: str) -> bool:
        rec = self._keys.get(key_id)
        if not rec:
            return False
        rec.status = KeyStatus.REVOKED
        rec.revoked_at = utc_now().isoformat()
        self.save()
        return True

    def is_trusted(self, key_id: str) -> bool:
        rec = self._keys.get(key_id)
        return rec is not None and rec.status == KeyStatus.ACTIVE

    def list_keys(self, status: Optional[KeyStatus] = None) -> List[KeyRecord]:
        if status:
            return [k for k in self._keys.values() if k.status == status]
        return list(self._keys.values())

    def resolve_kms(self, key_id: str) -> Optional[str]:
        """Return KMS/HSM reference for external key operations."""
        rec = self._keys.get(key_id)
        return rec.kms_ref if rec else None
