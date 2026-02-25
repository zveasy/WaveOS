"""Key Management Service (KMS) provider interface for WaveOS."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from waveos.utils import get_logger

logger = get_logger("waveos.crypto.kms")


class KMSProvider(ABC):
    """Abstract KMS provider for key storage and retrieval."""

    @abstractmethod
    def get_signing_key(self, key_id: str) -> Optional[str]:
        ...

    @abstractmethod
    def get_verification_key(self, key_id: str) -> Optional[str]:
        ...

    @abstractmethod
    def rotate_key(self, key_id: str) -> str:
        ...

    @abstractmethod
    def list_keys(self) -> list:
        ...


class EnvKMSProvider(KMSProvider):
    """KMS backed by environment variables (dev/test)."""

    def __init__(self, prefix: str = "WAVEOS_KEY_") -> None:
        self.prefix = prefix

    def get_signing_key(self, key_id: str) -> Optional[str]:
        return os.getenv(f"{self.prefix}{key_id}_PRIVATE", os.getenv(f"{self.prefix}{key_id}"))

    def get_verification_key(self, key_id: str) -> Optional[str]:
        return os.getenv(f"{self.prefix}{key_id}_PUBLIC", os.getenv(f"{self.prefix}{key_id}"))

    def rotate_key(self, key_id: str) -> str:
        new_key = os.urandom(32).hex()
        logger.warning("EnvKMSProvider.rotate_key: manual env update required for %s%s", self.prefix, key_id)
        return new_key

    def list_keys(self) -> list:
        return [k.replace(self.prefix, "").replace("_PRIVATE", "").replace("_PUBLIC", "")
                for k in os.environ if k.startswith(self.prefix)]


class FileKMSProvider(KMSProvider):
    """KMS backed by filesystem key store (offline/air-gapped)."""

    def __init__(self, key_dir: Path) -> None:
        self.key_dir = key_dir
        self.key_dir.mkdir(parents=True, exist_ok=True)

    def get_signing_key(self, key_id: str) -> Optional[str]:
        path = self.key_dir / f"{key_id}.key"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        return None

    def get_verification_key(self, key_id: str) -> Optional[str]:
        path = self.key_dir / f"{key_id}.pub"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        path = self.key_dir / f"{key_id}.key"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        return None

    def rotate_key(self, key_id: str) -> str:
        new_key = os.urandom(32).hex()
        old_path = self.key_dir / f"{key_id}.key"
        if old_path.exists():
            backup = self.key_dir / f"{key_id}.key.{int(os.path.getmtime(str(old_path)))}.bak"
            old_path.rename(backup)
        old_path.write_text(new_key + "\n", encoding="utf-8")
        os.chmod(str(old_path), 0o600)
        return new_key

    def list_keys(self) -> list:
        return sorted({p.stem for p in self.key_dir.glob("*.key")} | {p.stem for p in self.key_dir.glob("*.pub")})
