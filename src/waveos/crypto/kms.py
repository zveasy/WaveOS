"""KMS provider interface — optional integration with HSM/KMS for key management."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.kms")


@dataclass
class KeyMetadata:
    key_id: str
    algorithm: str = "ed25519"
    created_at: str = ""
    rotated_at: str = ""
    revoked: bool = False
    revoked_at: str = ""
    purpose: str = "signing"

    def to_dict(self) -> dict:
        return {
            "key_id": self.key_id, "algorithm": self.algorithm,
            "created_at": self.created_at, "rotated_at": self.rotated_at,
            "revoked": self.revoked, "revoked_at": self.revoked_at,
            "purpose": self.purpose,
        }

    @classmethod
    def from_dict(cls, d: dict) -> KeyMetadata:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


class KMSProvider:
    """Key management provider (file-based default; can be extended for HSM/Vault/AWS KMS)."""

    def __init__(self, store_path: Path = Path("out/kms")) -> None:
        self.store_path = store_path
        self.store_path.mkdir(parents=True, exist_ok=True)
        self._index_path = self.store_path / "keys.json"

    def _load_index(self) -> List[KeyMetadata]:
        if not self._index_path.exists():
            return []
        try:
            return [KeyMetadata.from_dict(k) for k in json.loads(self._index_path.read_text(encoding="utf-8"))]
        except (json.JSONDecodeError, KeyError):
            return []

    def _save_index(self, keys: List[KeyMetadata]) -> None:
        self._index_path.write_text(json.dumps([k.to_dict() for k in keys], indent=2) + "\n", encoding="utf-8")

    def create_key(self, key_id: str = "", purpose: str = "signing") -> KeyMetadata:
        from waveos.crypto.signing import generate_keypair
        kp = generate_keypair(key_id=key_id)
        (self.store_path / f"{kp.key_id}.private.pem").write_text(kp.private_key_pem, encoding="utf-8")
        (self.store_path / f"{kp.key_id}.public.pem").write_text(kp.public_key_pem, encoding="utf-8")
        meta = KeyMetadata(key_id=kp.key_id, algorithm=kp.algorithm, created_at=utc_now().isoformat(), purpose=purpose)
        keys = self._load_index()
        keys.append(meta)
        self._save_index(keys)
        logger.info("Created key %s (%s)", kp.key_id, kp.algorithm)
        return meta

    def get_key(self, key_id: str) -> Optional[KeyMetadata]:
        for k in self._load_index():
            if k.key_id == key_id:
                return k
        return None

    def list_keys(self, include_revoked: bool = False) -> List[KeyMetadata]:
        keys = self._load_index()
        if not include_revoked:
            keys = [k for k in keys if not k.revoked]
        return keys

    def revoke_key(self, key_id: str) -> bool:
        keys = self._load_index()
        for k in keys:
            if k.key_id == key_id:
                k.revoked = True
                k.revoked_at = utc_now().isoformat()
                self._save_index(keys)
                logger.info("Revoked key %s", key_id)
                return True
        return False

    def rotate_key(self, old_key_id: str, purpose: str = "signing") -> Optional[KeyMetadata]:
        self.revoke_key(old_key_id)
        return self.create_key(purpose=purpose)

    def get_private_key(self, key_id: str) -> str:
        path = self.store_path / f"{key_id}.private.pem"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        return ""

    def get_public_key(self, key_id: str) -> str:
        path = self.store_path / f"{key_id}.public.pem"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        return ""


def get_kms_provider(provider: str = "file", store_path: Optional[Path] = None) -> KMSProvider:
    """Get a KMS provider instance."""
    return KMSProvider(store_path=store_path or Path("out/kms"))
