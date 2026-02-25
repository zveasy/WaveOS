"""WaveOS Registry Auth — device identity, certificate management, and authorization."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.auth")


@dataclass
class DeviceCredential:
    """Credential for a device/node accessing the registry."""
    device_id: str
    site_id: str = ""
    clearance: str = "unclassified"
    channels: List[str] = field(default_factory=lambda: ["dev"])
    cert_fingerprint: str = ""
    token_hash: str = ""
    created_at: str = ""
    expires_at: str = ""
    revoked: bool = False

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "site_id": self.site_id,
            "clearance": self.clearance,
            "channels": self.channels,
            "cert_fingerprint": self.cert_fingerprint,
            "token_hash": self.token_hash,
            "created_at": self.created_at or utc_now().isoformat(),
            "expires_at": self.expires_at,
            "revoked": self.revoked,
        }

    @classmethod
    def from_dict(cls, d: dict) -> DeviceCredential:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


class DeviceAuthStore:
    """Manages device credentials and authorization."""

    def __init__(self, store_path: Path) -> None:
        self.store_path = store_path
        self.store_path.mkdir(parents=True, exist_ok=True)
        self._creds_path = self.store_path / "device_credentials.json"

    def _load(self) -> List[DeviceCredential]:
        if not self._creds_path.exists():
            return []
        try:
            data = json.loads(self._creds_path.read_text(encoding="utf-8"))
            return [DeviceCredential.from_dict(d) for d in data]
        except (json.JSONDecodeError, KeyError):
            return []

    def _save(self, creds: List[DeviceCredential]) -> None:
        self._creds_path.write_text(
            json.dumps([c.to_dict() for c in creds], indent=2) + "\n", encoding="utf-8"
        )

    def register_device(self, device_id: str, site_id: str = "", clearance: str = "unclassified", channels: Optional[List[str]] = None) -> DeviceCredential:
        token = hashlib.sha256(f"{device_id}:{utc_now().isoformat()}:{os.urandom(16).hex()}".encode()).hexdigest()
        cred = DeviceCredential(
            device_id=device_id,
            site_id=site_id,
            clearance=clearance,
            channels=channels or ["dev"],
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            created_at=utc_now().isoformat(),
        )
        creds = self._load()
        creds = [c for c in creds if c.device_id != device_id]
        creds.append(cred)
        self._save(creds)
        cred.token_hash = token
        return cred

    def authenticate(self, token: str) -> Optional[DeviceCredential]:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        for cred in self._load():
            if cred.token_hash == token_hash and not cred.revoked:
                if cred.expires_at:
                    try:
                        from datetime import datetime, timezone
                        exp = datetime.fromisoformat(cred.expires_at.replace("Z", "+00:00"))
                        if exp < datetime.now(timezone.utc):
                            return None
                    except (ValueError, TypeError):
                        pass
                return cred
        return None

    def authorize_channel(self, cred: DeviceCredential, channel: str) -> bool:
        if cred.revoked:
            return False
        return channel in cred.channels or "all" in cred.channels

    def revoke_device(self, device_id: str) -> bool:
        creds = self._load()
        found = False
        for c in creds:
            if c.device_id == device_id:
                c.revoked = True
                found = True
        if found:
            self._save(creds)
        return found

    def list_devices(self) -> List[DeviceCredential]:
        return self._load()

    def rotate_token(self, device_id: str) -> Optional[DeviceCredential]:
        creds = self._load()
        for c in creds:
            if c.device_id == device_id and not c.revoked:
                new_token = hashlib.sha256(f"{device_id}:{utc_now().isoformat()}:{os.urandom(16).hex()}".encode()).hexdigest()
                c.token_hash = hashlib.sha256(new_token.encode()).hexdigest()
                self._save(creds)
                result = DeviceCredential.from_dict(c.to_dict())
                result.token_hash = new_token
                return result
        return None
