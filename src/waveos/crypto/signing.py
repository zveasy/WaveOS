"""Public-key bundle signing — Ed25519 with fallback to HMAC-SHA512 for environments without cryptography."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.signing")

_HAS_CRYPTOGRAPHY = False
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    from cryptography.hazmat.primitives import serialization
    _HAS_CRYPTOGRAPHY = True
except ImportError:
    pass


@dataclass
class KeyPair:
    """Asymmetric key pair (Ed25519 preferred, HMAC-SHA512 fallback)."""
    private_key_pem: str = ""
    public_key_pem: str = ""
    algorithm: str = "ed25519"
    key_id: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "public_key_pem": self.public_key_pem,
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "created_at": self.created_at,
        }


def generate_keypair(key_id: str = "") -> KeyPair:
    """Generate a new Ed25519 keypair (or HMAC fallback key)."""
    if _HAS_CRYPTOGRAPHY:
        private_key = Ed25519PrivateKey.generate()
        private_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode("utf-8")
        public_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        return KeyPair(
            private_key_pem=private_pem,
            public_key_pem=public_pem,
            algorithm="ed25519",
            key_id=key_id or f"key-{os.urandom(8).hex()}",
            created_at=utc_now().isoformat(),
        )
    secret = os.urandom(64).hex()
    return KeyPair(
        private_key_pem=secret,
        public_key_pem=secret,
        algorithm="hmac-sha512",
        key_id=key_id or f"hmac-{os.urandom(8).hex()}",
        created_at=utc_now().isoformat(),
    )


def sign_bundle_pubkey(manifest_path: Path, private_key_pem: str, algorithm: str = "ed25519") -> str:
    """Sign bundle manifest with private key. Returns hex signature."""
    payload = manifest_path.read_bytes()
    if algorithm == "ed25519" and _HAS_CRYPTOGRAPHY:
        private_key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
        signature = private_key.sign(payload)
        sig_hex = signature.hex()
    else:
        sig_hex = hmac.new(private_key_pem.encode("utf-8"), payload, hashlib.sha512).hexdigest()
    sig_path = manifest_path.parent / "bundle.sig.v2"
    sig_data = {
        "signature": sig_hex,
        "algorithm": algorithm if (algorithm == "ed25519" and _HAS_CRYPTOGRAPHY) else "hmac-sha512",
        "signed_at": utc_now().isoformat(),
        "manifest_sha256": hashlib.sha256(payload).hexdigest(),
    }
    sig_path.write_text(json.dumps(sig_data, indent=2) + "\n", encoding="utf-8")
    return sig_hex


def verify_bundle_pubkey(manifest_path: Path, public_key_pem: str, algorithm: str = "ed25519") -> Tuple[bool, str]:
    """Verify bundle signature. Returns (ok, error_message)."""
    sig_path = manifest_path.parent / "bundle.sig.v2"
    if not sig_path.exists():
        sig_path = manifest_path.parent / "bundle.sig"
        if not sig_path.exists():
            return False, "No signature file found"
        sig_hex = sig_path.read_text(encoding="utf-8").strip()
        payload = manifest_path.read_bytes()
        expected = hmac.new(public_key_pem.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig_hex, expected):
            return True, ""
        return False, "HMAC-SHA256 (v1) signature mismatch"

    try:
        sig_data = json.loads(sig_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"Cannot read signature: {exc}"

    sig_hex = sig_data.get("signature", "")
    sig_alg = sig_data.get("algorithm", "")
    payload = manifest_path.read_bytes()
    manifest_hash = hashlib.sha256(payload).hexdigest()
    if sig_data.get("manifest_sha256") and sig_data["manifest_sha256"] != manifest_hash:
        return False, "Manifest hash mismatch (tampered after signing)"

    if sig_alg == "ed25519" and _HAS_CRYPTOGRAPHY:
        try:
            public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
            public_key.verify(bytes.fromhex(sig_hex), payload)
            return True, ""
        except Exception as exc:
            return False, f"Ed25519 verification failed: {exc}"
    else:
        expected = hmac.new(public_key_pem.encode("utf-8"), payload, hashlib.sha512).hexdigest()
        if hmac.compare_digest(sig_hex, expected):
            return True, ""
        return False, "HMAC-SHA512 signature mismatch"


def load_public_key(path: Path) -> str:
    """Load public key from file."""
    return path.read_text(encoding="utf-8").strip()


def load_private_key(path: Path) -> str:
    """Load private key from file."""
    return path.read_text(encoding="utf-8").strip()
