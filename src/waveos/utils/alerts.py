from __future__ import annotations

import ipaddress
import json
import urllib.request
from typing import Any, Dict
from urllib.parse import urlparse

from waveos.utils.retry import retry


# Timeout for outbound webhook/Slack requests (seconds)
WEBHOOK_REQUEST_TIMEOUT = 10

# Allowed URL schemes for webhooks (SSRF protection: no file:// or internal services)
_ALLOWED_WEBHOOK_SCHEMES = ("https",)


def _is_private_or_reserved(host: str) -> bool:
    """True if host is an IP in private, loopback, or reserved range."""
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_private or addr.is_loopback or addr.is_reserved
    except ValueError:
        return False


def _validate_webhook_url(url: str) -> None:
    """Raise ValueError if URL is not allowed (SSRF: only https, no private IPs)."""
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_WEBHOOK_SCHEMES:
        raise ValueError(f"Webhook URL scheme must be one of {_ALLOWED_WEBHOOK_SCHEMES}, got {scheme!r}")
    host = (parsed.hostname or "").strip()
    if not host:
        raise ValueError("Webhook URL has no host")
    if _is_private_or_reserved(host):
        raise ValueError("Webhook URL must not point to private or loopback IP")


def send_webhook(url: str, payload: Dict[str, Any], retries: int = 2) -> None:
    _validate_webhook_url(url)

    def _send() -> None:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=WEBHOOK_REQUEST_TIMEOUT) as response:
            response.read()

    retry(_send, retries=retries, base_delay=0.2, max_delay=1.0)
