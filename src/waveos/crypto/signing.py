"""Bundle signing — Ed25519 (with fallback) and HMAC-SHA256."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.signing")


@dataclass
class KeyPair:
    private_key_hex: str
    public_key_hex: str
    algorithm: str = "ed25519"
    key_id: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "private_key_hex": self.private_key_hex,
            "public_key_hex": self.public_key_hex,
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "created_at": self.created_at or utc_now().isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> KeyPair:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


def generate_keypair(algorithm: str = "ed25519") -> KeyPair:
    """Generate a signing key pair.
    Uses cryptography lib if available, falls back to HMAC shared secret.
    """
    key_id = f"key-{secrets.token_hex(8)}"
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat
        private_key = Ed25519PrivateKey.generate()
        priv_bytes = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        pub_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return KeyPair(
            private_key_hex=priv_bytes.hex(),
            public_key_hex=pub_bytes.hex(),
            algorithm="ed25519",
            key_id=key_id,
            created_at=utc_now().isoformat(),
        )
    except ImportError:
        logger.info("cryptography not available, generating HMAC key pair (symmetric)")
        shared = secrets.token_hex(32)
        return KeyPair(
            private_key_hex=shared,
            public_key_hex=shared,
            algorithm="hmac-sha256",
            key_id=key_id,
            created_at=utc_now().isoformat(),
        )


def _manifest_digest(bundle_dir: Path) -> str:
    manifest_path = bundle_dir / "bundle.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No bundle.json in {bundle_dir}")
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def sign_bundle_ed25519(bundle_dir: Path, private_key_hex: str) -> str:
    """Sign bundle manifest with Ed25519. Falls back to HMAC if cryptography unavailable."""
    digest = _manifest_digest(bundle_dir)
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
        sig = priv.sign(digest.encode("utf-8"))
        sig_hex = sig.hex()
    except ImportError:
        sig_hex = hmac.new(bytes.fromhex(private_key_hex), digest.encode("utf-8"), hashlib.sha256).hexdigest()

    sig_data = {
        "algorithm": "ed25519",
        "digest": digest,
        "signature": sig_hex,
        "signed_at": utc_now().isoformat(),
    }
    sig_path = bundle_dir / "bundle.sig.json"
    sig_path.write_text(json.dumps(sig_data, indent=2) + "\n", encoding="utf-8")
    return sig_hex


def verify_bundle_ed25519(bundle_dir: Path, public_key_hex: str) -> bool:
    """Verify Ed25519 signature. Falls back to HMAC verification."""
    sig_path = bundle_dir / "bundle.sig.json"
    if not sig_path.exists():
        old_sig = bundle_dir / "bundle.sig"
        if old_sig.exists():
            from waveos.bundle import verify_manifest
            return verify_manifest(bundle_dir, public_key_hex)
        return False

    try:
        sig_data = json.loads(sig_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False

    digest = _manifest_digest(bundle_dir)
    if digest != sig_data.get("digest", ""):
        return False

    sig_hex = sig_data.get("signature", "")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        pub.verify(bytes.fromhex(sig_hex), digest.encode("utf-8"))
        return True
    except ImportError:
        expected = hmac.new(bytes.fromhex(public_key_hex), digest.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig_hex)
    except Exception:
        return False


def sign_bundle_hmac(bundle_dir: Path, hmac_key: str) -> str:
    """Sign with HMAC-SHA256 (backward compatible)."""
    from waveos.bundle import sign_manifest
    manifest_path = bundle_dir / "bundle.json"
    return sign_manifest(manifest_path, hmac_key)


def verify_bundle_hmac(bundle_dir: Path, hmac_key: str) -> bool:
    """Verify HMAC-SHA256 signature."""
    from waveos.bundle import verify_manifest
    return verify_manifest(bundle_dir, hmac_key)
