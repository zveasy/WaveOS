"""
Command integrity (control-plane hardened): coordinator signs action batches, agent verifies.
Nonce + timestamp prevent replay; evidence pack includes signature + verified-by-agent record.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from waveos.utils import get_logger, get_secret

logger = get_logger("waveos.action_signing")

# Replay window: reject if timestamp older than this (seconds)
DEFAULT_MAX_AGE_SEC = 300
# Max nonces to remember per scope (simple replay cache)
MAX_NONCES = 10_000

_seen_nonces: Dict[str, int] = {}  # (scope, nonce) -> expiry time (we use scope as key prefix)


def _canonical(payload: Dict[str, Any]) -> bytes:
    """Canonical JSON for signing (sort keys)."""
    return json.dumps(payload, sort_keys=True, default=str).encode("utf-8")


def _get_key() -> Optional[bytes]:
    key = get_secret("WAVEOS_ACTION_SIGNING_KEY") or get_secret("waveos_action_signing_key")
    if not key:
        key = os.getenv("WAVEOS_ACTION_SIGNING_KEY", "").strip()
    return key.encode("utf-8") if key else None


def sign_action_batch(
    actions: List[Dict[str, Any]],
    scope: str = "default",
    nonce: Optional[str] = None,
    timestamp: Optional[float] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Build signed action batch: { actions, nonce, timestamp, scope, signature }.
    Returns (signed_payload_dict, error_message). signature is HMAC-SHA256 of canonical(actions+nonce+timestamp+scope).
    """
    key = _get_key()
    if not key:
        return None, "WAVEOS_ACTION_SIGNING_KEY not set"
    nonce = nonce or str(uuid.uuid4())
    ts = timestamp or time.time()
    payload = {
        "actions": actions,
        "nonce": nonce,
        "timestamp": ts,
        "scope": scope,
    }
    to_sign = _canonical(payload)
    sig = hmac.new(key, to_sign, hashlib.sha256).hexdigest()
    payload["signature"] = sig
    return payload, None


def verify_action_batch(
    signed: Dict[str, Any],
    max_age_sec: float = DEFAULT_MAX_AGE_SEC,
    replay_scope: Optional[str] = None,
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """
    Verify signature and replay (nonce + timestamp). Returns (actions_list, error_message).
    If replay_scope is set, nonces are checked to prevent reuse.
    """
    key = _get_key()
    if not key:
        return None, "WAVEOS_ACTION_SIGNING_KEY not set"
    sig = signed.get("signature")
    if not sig:
        return None, "missing signature"
    payload = {k: v for k, v in signed.items() if k != "signature"}
    to_verify = _canonical(payload)
    expected = hmac.new(key, to_verify, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None, "signature verification failed"
    ts = signed.get("timestamp")
    if ts is None:
        return None, "missing timestamp"
    try:
        ts_f = float(ts)
    except (TypeError, ValueError):
        return None, "invalid timestamp"
    if time.time() - ts_f > max_age_sec:
        return None, "timestamp too old (replay?)"
    if ts_f > time.time() + 60:
        return None, "timestamp in future"
    nonce = signed.get("nonce")
    if not nonce:
        return None, "missing nonce"
    scope = replay_scope or signed.get("scope", "default")
    cache_key = f"{scope}:{nonce}"
    if cache_key in _seen_nonces and _seen_nonces[cache_key] > time.time():
        return None, "nonce already used (replay)"
    # Prune old entries
    now = time.time()
    _seen_nonces[cache_key] = now + max_age_sec
    to_del = [k for k, v in _seen_nonces.items() if v <= now]
    for k in to_del:
        del _seen_nonces[k]
    if len(_seen_nonces) > MAX_NONCES:
        for k in sorted(_seen_nonces.keys(), key=lambda x: _seen_nonces[x])[: len(_seen_nonces) // 2]:
            del _seen_nonces[k]
    actions = signed.get("actions")
    if not isinstance(actions, list):
        return None, "invalid actions"
    return actions, None


def verified_by_agent_record(
    signed_batch_id: str,
    node_id: str,
    verified_at: str,
    nonce: str,
    action_count: int,
    success: bool,
) -> Dict[str, Any]:
    """Record for evidence pack: agent verified this signed batch."""
    return {
        "signed_batch_id": signed_batch_id,
        "node_id": node_id,
        "verified_at": verified_at,
        "nonce": nonce,
        "action_count": action_count,
        "verification_success": success,
    }
