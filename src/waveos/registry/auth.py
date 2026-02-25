"""Registry authentication and authorization — mTLS + device identity + channel clearance."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.registry.auth")


@dataclass
class DeviceIdentity:
    """Authenticated device/node identity."""
    device_id: str
    site_id: str = ""
    clearance: str = "dev"
    roles: List[str] = field(default_factory=list)
    cert_fingerprint: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"device_id": self.device_id, "site_id": self.site_id, "clearance": self.clearance,
                "roles": self.roles, "cert_fingerprint": self.cert_fingerprint, "metadata": self.metadata}

    @classmethod
    def from_dict(cls, d: dict) -> DeviceIdentity:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


@dataclass
class ChannelACL:
    """Access control for registry channels."""
    channel: str
    allowed_publishers: List[str] = field(default_factory=list)
    allowed_consumers: List[str] = field(default_factory=list)
    require_ci_publisher: bool = False
    min_clearance: str = "dev"

    def to_dict(self) -> dict:
        return {"channel": self.channel, "allowed_publishers": self.allowed_publishers,
                "allowed_consumers": self.allowed_consumers, "require_ci_publisher": self.require_ci_publisher,
                "min_clearance": self.min_clearance}

    @classmethod
    def from_dict(cls, d: dict) -> ChannelACL:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


CLEARANCE_LEVELS = {"dev": 0, "staging": 1, "prod": 2, "mission-critical": 3}

DEFAULT_CHANNEL_ACLS: Dict[str, ChannelACL] = {
    "dev": ChannelACL(channel="dev", min_clearance="dev"),
    "staging": ChannelACL(channel="staging", min_clearance="staging", require_ci_publisher=True),
    "prod": ChannelACL(channel="prod", min_clearance="prod", require_ci_publisher=True),
    "mission-critical": ChannelACL(channel="mission-critical", min_clearance="mission-critical", require_ci_publisher=True),
}


@dataclass
class RateLimiter:
    """Token-bucket rate limiter per device/site."""
    max_requests: int = 100
    window_sec: int = 60
    _buckets: Dict[str, List[float]] = field(default_factory=dict)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._buckets.setdefault(key, [])
        bucket[:] = [t for t in bucket if now - t < self.window_sec]
        if len(bucket) >= self.max_requests:
            return False
        bucket.append(now)
        return True

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)


class RegistryAuthenticator:
    """Authenticates devices and enforces channel access control."""

    def __init__(self, device_store_path: Optional[Path] = None, acls: Optional[Dict[str, ChannelACL]] = None) -> None:
        self._devices: Dict[str, DeviceIdentity] = {}
        self._acls = acls or dict(DEFAULT_CHANNEL_ACLS)
        self._rate_limiter = RateLimiter()
        self._tokens: Dict[str, str] = {}
        if device_store_path and device_store_path.exists():
            self._load_devices(device_store_path)
        self._load_tokens_from_env()

    def _load_devices(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for d in data:
                dev = DeviceIdentity.from_dict(d)
                self._devices[dev.device_id] = dev
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load device store: %s", exc)

    def _load_tokens_from_env(self) -> None:
        raw = os.getenv("WAVEOS_REGISTRY_TOKENS", "")
        for pair in raw.split(","):
            pair = pair.strip()
            if "=" in pair:
                token, device_id = pair.split("=", 1)
                self._tokens[token.strip()] = device_id.strip()

    def register_device(self, device: DeviceIdentity) -> None:
        self._devices[device.device_id] = device

    def authenticate_token(self, token: str) -> Optional[DeviceIdentity]:
        device_id = self._tokens.get(token)
        if device_id:
            return self._devices.get(device_id, DeviceIdentity(device_id=device_id))
        return None

    def authenticate_cert(self, cert_fingerprint: str) -> Optional[DeviceIdentity]:
        for dev in self._devices.values():
            if dev.cert_fingerprint and dev.cert_fingerprint == cert_fingerprint:
                return dev
        return None

    def authorize_publish(self, device: DeviceIdentity, channel: str) -> tuple[bool, str]:
        acl = self._acls.get(channel, self._acls.get("dev"))
        if not acl:
            return True, ""
        if acl.require_ci_publisher and "ci" not in device.roles:
            return False, f"Channel {channel} requires CI publisher role"
        if acl.allowed_publishers and device.device_id not in acl.allowed_publishers:
            return False, f"Device {device.device_id} not in allowed publishers for {channel}"
        dev_clearance = CLEARANCE_LEVELS.get(device.clearance, 0)
        min_clearance = CLEARANCE_LEVELS.get(acl.min_clearance, 0)
        if dev_clearance < min_clearance:
            return False, f"Device clearance {device.clearance} below minimum {acl.min_clearance}"
        return True, ""

    def authorize_download(self, device: DeviceIdentity, channel: str) -> tuple[bool, str]:
        acl = self._acls.get(channel, self._acls.get("dev"))
        if not acl:
            return True, ""
        if acl.allowed_consumers and device.device_id not in acl.allowed_consumers:
            return False, f"Device {device.device_id} not in allowed consumers for {channel}"
        dev_clearance = CLEARANCE_LEVELS.get(device.clearance, 0)
        min_clearance = CLEARANCE_LEVELS.get(acl.min_clearance, 0)
        if dev_clearance < min_clearance:
            return False, f"Device clearance {device.clearance} below minimum {acl.min_clearance}"
        return True, ""

    def check_rate_limit(self, device_id: str) -> bool:
        return self._rate_limiter.allow(device_id)

    def save_devices(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [d.to_dict() for d in self._devices.values()]
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def generate_token(self, device_id: str) -> str:
        token = hashlib.sha256(f"{device_id}:{utc_now().isoformat()}:{os.urandom(16).hex()}".encode()).hexdigest()[:48]
        self._tokens[token] = device_id
        return token
