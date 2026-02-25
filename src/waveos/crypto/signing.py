"""Public-key signing for WaveOS bundles (Ed25519 asymmetric)."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.signing")

_HAS_CRYPTO = False
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    from cryptography.hazmat.primitives import serialization
    _HAS_CRYPTO = True
except ImportError:
    pass


@dataclass
class KeyPair:
    """Ed25519 key pair (PEM-encoded strings)."""
    private_pem: str = ""
    public_pem: str = ""
    key_id: str = ""

    def to_dict(self) -> dict:
        return {"public_pem": self.public_pem, "key_id": self.key_id}


def generate_keypair(key_id: str = "") -> KeyPair:
    """Generate a new Ed25519 key pair."""
    if not _HAS_CRYPTO:
        logger.warning("cryptography not installed; using stub keypair")
        return KeyPair(private_pem="STUB_PRIVATE", public_pem="STUB_PUBLIC", key_id=key_id or "stub")
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    public_pem = private_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    kid = key_id or hashlib.sha256(public_pem.encode()).hexdigest()[:16]
    return KeyPair(private_pem=private_pem, public_pem=public_pem, key_id=kid)


def load_private_key(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def load_public_key(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def sign_bundle_public_key(manifest_path: Path, private_pem: str) -> str:
    """Sign a bundle manifest with Ed25519 private key. Returns base64 signature."""
    payload = manifest_path.read_bytes()
    if not _HAS_CRYPTO or private_pem.startswith("STUB"):
        sig = base64.b64encode(hashlib.sha256(payload).digest()).decode()
        sig_path = manifest_path.parent / "bundle.ed25519.sig"
        sig_path.write_text(sig + "\n", encoding="utf-8")
        return sig
    private_key = serialization.load_pem_private_key(private_pem.encode(), password=None)
    signature = private_key.sign(payload)
    sig_b64 = base64.b64encode(signature).decode()
    sig_path = manifest_path.parent / "bundle.ed25519.sig"
    sig_path.write_text(sig_b64 + "\n", encoding="utf-8")
    return sig_b64


def verify_bundle_public_key(manifest_path: Path, public_pem: str) -> tuple[bool, str]:
    """Verify Ed25519 signature. Returns (ok, message)."""
    sig_path = manifest_path.parent / "bundle.ed25519.sig"
    if not sig_path.exists():
        return False, "No Ed25519 signature file found"
    sig_b64 = sig_path.read_text(encoding="utf-8").strip()
    payload = manifest_path.read_bytes()
    if not _HAS_CRYPTO or public_pem.startswith("STUB"):
        expected = base64.b64encode(hashlib.sha256(payload).digest()).decode()
        if sig_b64 == expected:
            return True, "verified (stub mode)"
        return False, "signature mismatch (stub mode)"
    try:
        signature = base64.b64decode(sig_b64)
        public_key = serialization.load_pem_public_key(public_pem.encode())
        public_key.verify(signature, payload)
        return True, "verified"
    except Exception as exc:
        return False, f"verification failed: {exc}"
