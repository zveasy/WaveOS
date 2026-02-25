"""Public-key signing for release bundles (Ed25519 via hashlib/hmac fallback, or cryptography if available)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.signing")


@dataclass
class KeyPair:
    """Asymmetric key pair (or HMAC key in fallback mode)."""
    key_id: str
    public_key: str    # base64-encoded
    private_key: str = ""  # base64-encoded (empty for verify-only)
    algorithm: str = "ed25519"  # ed25519 | hmac-sha256
    created_at: str = ""

    def to_dict(self, include_private: bool = False) -> dict:
        d = {"key_id": self.key_id, "public_key": self.public_key, "algorithm": self.algorithm, "created_at": self.created_at or utc_now().isoformat()}
        if include_private and self.private_key:
            d["private_key"] = self.private_key
        return d

    @classmethod
    def from_dict(cls, d: dict) -> KeyPair:
        return cls(key_id=d.get("key_id", ""), public_key=d.get("public_key", ""), private_key=d.get("private_key", ""), algorithm=d.get("algorithm", "ed25519"), created_at=d.get("created_at", ""))


def _try_ed25519():
    """Try to import Ed25519 from cryptography library."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
        from cryptography.hazmat.primitives import serialization
        return Ed25519PrivateKey, Ed25519PublicKey, serialization, True
    except ImportError:
        return None, None, None, False


def generate_keypair(key_id: str = "") -> KeyPair:
    """Generate a new signing key pair. Uses Ed25519 if cryptography is available, else HMAC fallback."""
    Ed25519PrivateKey, _, serialization, available = _try_ed25519()
    if available:
        private_key = Ed25519PrivateKey.generate()
        private_bytes = private_key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        public_bytes = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return KeyPair(
            key_id=key_id or f"key-{hashlib.sha256(public_bytes).hexdigest()[:12]}",
            public_key=base64.b64encode(public_bytes).decode(),
            private_key=base64.b64encode(private_bytes).decode(),
            algorithm="ed25519",
            created_at=utc_now().isoformat(),
        )
    import secrets
    shared = secrets.token_bytes(32)
    return KeyPair(
        key_id=key_id or f"key-{hashlib.sha256(shared).hexdigest()[:12]}",
        public_key=base64.b64encode(shared).decode(),
        private_key=base64.b64encode(shared).decode(),
        algorithm="hmac-sha256",
        created_at=utc_now().isoformat(),
    )


def sign_data(data: bytes, keypair: KeyPair) -> str:
    """Sign data and return base64-encoded signature."""
    if keypair.algorithm == "ed25519":
        Ed25519PrivateKey, _, serialization, available = _try_ed25519()
        if available and keypair.private_key:
            priv_bytes = base64.b64decode(keypair.private_key)
            private_key = Ed25519PrivateKey.from_private_bytes(priv_bytes)
            sig = private_key.sign(data)
            return base64.b64encode(sig).decode()
    raw_key = base64.b64decode(keypair.private_key)
    sig = hmac.new(raw_key, data, hashlib.sha256).digest()
    return base64.b64encode(sig).decode()


def verify_signature(data: bytes, signature_b64: str, keypair: KeyPair) -> bool:
    """Verify a signature."""
    try:
        sig = base64.b64decode(signature_b64)
        if keypair.algorithm == "ed25519":
            _, Ed25519PublicKey, serialization, available = _try_ed25519()
            if available:
                pub_bytes = base64.b64decode(keypair.public_key)
                public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
                public_key.verify(sig, data)
                return True
        raw_key = base64.b64decode(keypair.public_key)
        expected = hmac.new(raw_key, data, hashlib.sha256).digest()
        return hmac.compare_digest(sig, expected)
    except Exception as exc:
        logger.debug("Signature verification failed: %s", exc)
        return False


def sign_bundle_ed25519(bundle_dir: Path, keypair: KeyPair) -> str:
    """Sign bundle manifest with public-key crypto. Returns signature."""
    manifest_path = bundle_dir / "bundle.json"
    data = manifest_path.read_bytes()
    sig = sign_data(data, keypair)
    sig_path = bundle_dir / "bundle.ed25519.sig"
    sig_data = {"signature": sig, "key_id": keypair.key_id, "algorithm": keypair.algorithm, "signed_at": utc_now().isoformat()}
    sig_path.write_text(json.dumps(sig_data, indent=2) + "\n", encoding="utf-8")
    return sig


def verify_bundle_ed25519(bundle_dir: Path, keypair: KeyPair) -> Tuple[bool, str]:
    """Verify bundle Ed25519/HMAC signature. Returns (ok, message)."""
    manifest_path = bundle_dir / "bundle.json"
    sig_path = bundle_dir / "bundle.ed25519.sig"
    if not manifest_path.exists():
        return False, "No manifest"
    if not sig_path.exists():
        return False, "No Ed25519 signature file"
    try:
        sig_data = json.loads(sig_path.read_text(encoding="utf-8"))
        sig = sig_data.get("signature", "")
        data = manifest_path.read_bytes()
        if verify_signature(data, sig, keypair):
            return True, f"Verified with key {keypair.key_id}"
        return False, "Signature mismatch"
    except (json.JSONDecodeError, OSError) as exc:
        return False, str(exc)
