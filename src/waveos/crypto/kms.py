"""KMS provider interface — abstract key management for HSM, Vault, AWS KMS, local file."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from waveos.utils import get_logger

logger = get_logger("waveos.crypto.kms")


@dataclass
class KeyMetadata:
    key_id: str
    algorithm: str
    created_at: str = ""
    rotated_at: str = ""
    revoked: bool = False
    provider: str = "local"

    def to_dict(self) -> dict:
        return {
            "key_id": self.key_id, "algorithm": self.algorithm,
            "created_at": self.created_at, "rotated_at": self.rotated_at,
            "revoked": self.revoked, "provider": self.provider,
        }


class KMSProvider:
    """Abstract KMS provider interface."""

    def get_signing_key(self, key_id: str = "") -> Optional[bytes]:
        raise NotImplementedError

    def get_verification_key(self, key_id: str = "") -> Optional[bytes]:
        raise NotImplementedError

    def list_keys(self) -> list:
        return []

    def rotate_key(self, key_id: str) -> Optional[str]:
        return None

    def revoke_key(self, key_id: str) -> bool:
        return False


class LocalFileKMS(KMSProvider):
    """Local file-based KMS for development and air-gapped environments."""

    def __init__(self, keys_dir: Path = Path("out/keys")) -> None:
        self.keys_dir = keys_dir
        self.keys_dir.mkdir(parents=True, exist_ok=True)

    def get_signing_key(self, key_id: str = "default") -> Optional[bytes]:
        path = self.keys_dir / f"{key_id}.private"
        if path.exists():
            data = path.read_text(encoding="utf-8").strip()
            try:
                return bytes.fromhex(data)
            except ValueError:
                return path.read_bytes()
        return None

    def get_verification_key(self, key_id: str = "default") -> Optional[bytes]:
        path = self.keys_dir / f"{key_id}.public"
        if path.exists():
            data = path.read_text(encoding="utf-8").strip()
            try:
                return bytes.fromhex(data)
            except ValueError:
                return path.read_bytes()
        return None

    def list_keys(self) -> list:
        keys = []
        for p in sorted(self.keys_dir.glob("*.public")):
            key_id = p.stem
            meta_path = self.keys_dir / f"{key_id}.meta.json"
            meta = KeyMetadata(key_id=key_id, algorithm="unknown", provider="local")
            if meta_path.exists():
                try:
                    d = json.loads(meta_path.read_text(encoding="utf-8"))
                    meta = KeyMetadata(**{k: d[k] for k in d if k in KeyMetadata.__dataclass_fields__})
                except (json.JSONDecodeError, KeyError):
                    pass
            keys.append(meta)
        return keys

    def save_keypair(self, key_id: str, private_key: bytes, public_key: bytes, algorithm: str = "ed25519") -> None:
        from waveos.utils import utc_now
        (self.keys_dir / f"{key_id}.private").write_text(private_key.hex() + "\n", encoding="utf-8")
        (self.keys_dir / f"{key_id}.public").write_text(public_key.hex() + "\n", encoding="utf-8")
        meta = KeyMetadata(key_id=key_id, algorithm=algorithm, created_at=utc_now().isoformat(), provider="local")
        (self.keys_dir / f"{key_id}.meta.json").write_text(json.dumps(meta.to_dict(), indent=2) + "\n", encoding="utf-8")

    def rotate_key(self, key_id: str) -> Optional[str]:
        from waveos.crypto.signing import generate_keypair
        from waveos.utils import utc_now
        old_pub = self.keys_dir / f"{key_id}.public"
        if old_pub.exists():
            archive = self.keys_dir / f"{key_id}.public.old"
            old_pub.rename(archive)
            old_priv = self.keys_dir / f"{key_id}.private"
            if old_priv.exists():
                old_priv.rename(self.keys_dir / f"{key_id}.private.old")
        kp = generate_keypair(key_id=key_id)
        self.save_keypair(key_id, kp.private_key, kp.public_key, kp.algorithm)
        meta_path = self.keys_dir / f"{key_id}.meta.json"
        if meta_path.exists():
            d = json.loads(meta_path.read_text(encoding="utf-8"))
            d["rotated_at"] = utc_now().isoformat()
            meta_path.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
        return key_id

    def revoke_key(self, key_id: str) -> bool:
        meta_path = self.keys_dir / f"{key_id}.meta.json"
        if meta_path.exists():
            d = json.loads(meta_path.read_text(encoding="utf-8"))
            d["revoked"] = True
            meta_path.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
            priv = self.keys_dir / f"{key_id}.private"
            if priv.exists():
                priv.unlink()
            return True
        return False


def get_kms_provider(provider: str = "local", **kwargs) -> KMSProvider:
    """Factory for KMS providers."""
    if provider == "local":
        return LocalFileKMS(keys_dir=Path(kwargs.get("keys_dir", "out/keys")))
    logger.warning("Unknown KMS provider %s, falling back to local", provider)
    return LocalFileKMS()
