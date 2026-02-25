"""KMS (Key Management Service) provider interface — local, HSM, AWS KMS, Vault integration points."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.crypto.signing import KeyPair, generate_keypair, load_keypair, save_keypair
from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.kms")


class KMSProvider(ABC):
    """Abstract KMS provider interface."""

    @abstractmethod
    def get_signing_key(self, key_id: str) -> Optional[KeyPair]:
        ...

    @abstractmethod
    def get_verification_key(self, key_id: str) -> Optional[KeyPair]:
        ...

    @abstractmethod
    def list_keys(self) -> List[str]:
        ...

    @abstractmethod
    def create_key(self, key_id: str = "", algorithm: str = "hmac-sha256") -> KeyPair:
        ...

    @abstractmethod
    def rotate_key(self, key_id: str) -> Optional[KeyPair]:
        ...

    @abstractmethod
    def revoke_key(self, key_id: str) -> bool:
        ...


class LocalKMS(KMSProvider):
    """File-system-based KMS for development and air-gapped environments."""

    def __init__(self, keys_dir: Path) -> None:
        self.keys_dir = keys_dir
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        self._revoked: set = set()
        self._load_revoked()

    def _load_revoked(self) -> None:
        revoked_path = self.keys_dir / "revoked.json"
        if revoked_path.exists():
            try:
                self._revoked = set(json.loads(revoked_path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass

    def _save_revoked(self) -> None:
        path = self.keys_dir / "revoked.json"
        path.write_text(json.dumps(sorted(self._revoked), indent=2) + "\n", encoding="utf-8")

    def get_signing_key(self, key_id: str) -> Optional[KeyPair]:
        if key_id in self._revoked:
            return None
        return load_keypair(self.keys_dir / f"{key_id}.json")

    def get_verification_key(self, key_id: str) -> Optional[KeyPair]:
        key = load_keypair(self.keys_dir / f"{key_id}.json")
        if key:
            return KeyPair(key_id=key.key_id, algorithm=key.algorithm, public_key=key.public_key,
                           created_at=key.created_at, expires_at=key.expires_at)
        pub_path = self.keys_dir / f"{key_id}.pub.json"
        return load_keypair(pub_path)

    def list_keys(self) -> List[str]:
        keys = []
        for p in sorted(self.keys_dir.glob("*.json")):
            if p.stem not in ("revoked",) and not p.stem.endswith(".pub"):
                keys.append(p.stem)
        return keys

    def create_key(self, key_id: str = "", algorithm: str = "hmac-sha256") -> KeyPair:
        key = generate_keypair(key_id=key_id, algorithm=algorithm)
        save_keypair(key, self.keys_dir / f"{key.key_id}.json", include_private=True)
        pub_key = KeyPair(key_id=key.key_id, algorithm=key.algorithm, public_key=key.public_key,
                          created_at=key.created_at)
        save_keypair(pub_key, self.keys_dir / f"{key.key_id}.pub.json", include_private=False)
        return key

    def rotate_key(self, key_id: str) -> Optional[KeyPair]:
        old_key = self.get_signing_key(key_id)
        if not old_key:
            return None
        self.revoke_key(key_id)
        new_id = f"{key_id}-r{utc_now().strftime('%Y%m%d%H%M%S')}"
        return self.create_key(key_id=new_id, algorithm=old_key.algorithm)

    def revoke_key(self, key_id: str) -> bool:
        self._revoked.add(key_id)
        self._save_revoked()
        return True


def get_kms_provider(provider: str = "local", **kwargs) -> KMSProvider:
    """Factory for KMS providers."""
    if provider == "local":
        keys_dir = Path(kwargs.get("keys_dir", "out/keys"))
        return LocalKMS(keys_dir)
    logger.warning("Unknown KMS provider %s, using local", provider)
    return LocalKMS(Path(kwargs.get("keys_dir", "out/keys")))
