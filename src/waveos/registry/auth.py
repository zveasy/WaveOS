"""Registry authentication, authorization, and rate limiting."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import ssl
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.auth")


@dataclass
class DeviceCredential:
    """Device identity for registry access."""
    device_id: str
    site_id: str = ""
    clearance: str = "unclassified"
    allowed_channels: List[str] = field(default_factory=lambda: ["dev"])
    token_hash: str = ""
    cert_fingerprint: str = ""
    revoked: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id, "site_id": self.site_id,
            "clearance": self.clearance, "allowed_channels": self.allowed_channels,
            "token_hash": self.token_hash, "cert_fingerprint": self.cert_fingerprint,
            "revoked": self.revoked, "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> DeviceCredential:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


class CredentialStore:
    """Persistent credential store for device/node authentication."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._creds: Dict[str, DeviceCredential] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._creds = {d["device_id"]: DeviceCredential.from_dict(d) for d in data}
            except (json.JSONDecodeError, KeyError):
                pass

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps([c.to_dict() for c in self._creds.values()], indent=2) + "\n",
            encoding="utf-8",
        )

    def register(self, cred: DeviceCredential) -> None:
        self._creds[cred.device_id] = cred
        self._save()

    def get(self, device_id: str) -> Optional[DeviceCredential]:
        return self._creds.get(device_id)

    def revoke(self, device_id: str) -> bool:
        if device_id in self._creds:
            self._creds[device_id].revoked = True
            self._save()
            return True
        return False

    def list_all(self) -> List[DeviceCredential]:
        return list(self._creds.values())

    def authenticate_token(self, device_id: str, token: str) -> Optional[DeviceCredential]:
        cred = self._creds.get(device_id)
        if not cred or cred.revoked:
            return None
        expected = cred.token_hash
        actual = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if hmac.compare_digest(expected, actual):
            return cred
        return None

    def authenticate_cert(self, cert_fingerprint: str) -> Optional[DeviceCredential]:
        for cred in self._creds.values():
            if cred.revoked:
                continue
            if cred.cert_fingerprint and hmac.compare_digest(cred.cert_fingerprint, cert_fingerprint):
                return cred
        return None

    def authorize_channel(self, device_id: str, channel: str) -> bool:
        cred = self._creds.get(device_id)
        if not cred or cred.revoked:
            return False
        return channel in cred.allowed_channels


class RateLimiter:
    """Token-bucket rate limiter per device/site."""

    def __init__(self, max_requests: int = 60, window_sec: int = 60) -> None:
        self._max = max_requests
        self._window = window_sec
        self._buckets: Dict[str, List[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._buckets.setdefault(key, [])
        bucket[:] = [t for t in bucket if now - t < self._window]
        if len(bucket) >= self._max:
            return False
        bucket.append(now)
        return True

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)


def build_ssl_context(
    cert_path: Optional[str] = None,
    key_path: Optional[str] = None,
    ca_path: Optional[str] = None,
    require_client_cert: bool = False,
) -> Optional[ssl.SSLContext]:
    """Build SSL context for mTLS registry server/client."""
    if not cert_path or not key_path:
        return None
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if require_client_cert else ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cert_path, key_path)
        if ca_path:
            ctx.load_verify_locations(ca_path)
        if require_client_cert:
            ctx.verify_mode = ssl.CERT_REQUIRED
        else:
            ctx.verify_mode = ssl.CERT_OPTIONAL
        return ctx
    except (ssl.SSLError, OSError) as exc:
        logger.warning("SSL context creation failed: %s", exc)
        return None


def build_client_ssl_context(
    cert_path: Optional[str] = None,
    key_path: Optional[str] = None,
    ca_path: Optional[str] = None,
) -> Optional[ssl.SSLContext]:
    """Build SSL context for mTLS client connections."""
    if not cert_path:
        return None
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        if cert_path and key_path:
            ctx.load_cert_chain(cert_path, key_path)
        if ca_path:
            ctx.load_verify_locations(ca_path)
        else:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx
    except (ssl.SSLError, OSError) as exc:
        logger.warning("Client SSL context failed: %s", exc)
        return None


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
