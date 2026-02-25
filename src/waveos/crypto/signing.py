"""Public-key bundle signing using Ed25519 (via hashlib/hmac for environments without cryptography, with optional real Ed25519)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.signing")


@dataclass
class KeyPair:
    """Asymmetric key pair representation."""
    private_key: bytes
    public_key: bytes
    algorithm: str = "ed25519"
    key_id: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "created_at": self.created_at,
            "public_key_hex": self.public_key.hex(),
        }


def _try_ed25519():
    """Try to import real Ed25519 from cryptography library."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        return Ed25519PrivateKey
    except ImportError:
        return None


def generate_keypair(key_id: str = "") -> KeyPair:
    """Generate a new signing key pair. Uses Ed25519 if cryptography is available, else HMAC-SHA512 fallback."""
    Ed25519 = _try_ed25519()
    if Ed25519:
        from cryptography.hazmat.primitives import serialization
        private = Ed25519.generate()
        priv_bytes = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        pub_bytes = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return KeyPair(
            private_key=priv_bytes,
            public_key=pub_bytes,
            algorithm="ed25519",
            key_id=key_id or hashlib.sha256(pub_bytes).hexdigest()[:16],
            created_at=utc_now().isoformat(),
        )
    secret = os.urandom(64)
    pub = hashlib.sha512(secret).digest()
    return KeyPair(
        private_key=secret,
        public_key=pub,
        algorithm="hmac-sha512",
        key_id=key_id or hashlib.sha256(pub).hexdigest()[:16],
        created_at=utc_now().isoformat(),
    )


def sign_bundle(bundle_dir: Path, private_key: bytes, algorithm: str = "ed25519") -> str:
    """Sign a bundle manifest and write the signature. Returns signature hex."""
    manifest_path = bundle_dir / "bundle.json"
    if not manifest_path.exists():
        raise ValueError("No bundle.json to sign")
    payload = manifest_path.read_bytes()

    Ed25519 = _try_ed25519()
    if algorithm == "ed25519" and Ed25519:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key = Ed25519PrivateKey.from_private_bytes(private_key)
        sig = key.sign(payload)
        sig_hex = sig.hex()
    else:
        sig_hex = hmac.new(private_key, payload, hashlib.sha512).hexdigest()
        algorithm = "hmac-sha512"

    sig_data = {
        "algorithm": algorithm,
        "signature": sig_hex,
        "signed_at": utc_now().isoformat(),
        "manifest_sha256": hashlib.sha256(payload).hexdigest(),
    }
    sig_path = bundle_dir / "bundle.sig.json"
    sig_path.write_text(json.dumps(sig_data, indent=2) + "\n", encoding="utf-8")
    sig_path_legacy = bundle_dir / "bundle.sig"
    sig_path_legacy.write_text(sig_hex + "\n", encoding="utf-8")
    return sig_hex


def verify_bundle_signature(bundle_dir: Path, public_key: bytes, algorithm: str = "ed25519") -> tuple[bool, str]:
    """Verify bundle signature. Returns (ok, error_message)."""
    manifest_path = bundle_dir / "bundle.json"
    sig_json_path = bundle_dir / "bundle.sig.json"
    sig_legacy_path = bundle_dir / "bundle.sig"

    if not manifest_path.exists():
        return False, "No manifest"

    payload = manifest_path.read_bytes()

    if sig_json_path.exists():
        try:
            sig_data = json.loads(sig_json_path.read_text(encoding="utf-8"))
            sig_hex = sig_data.get("signature", "")
            algo = sig_data.get("algorithm", algorithm)
        except (json.JSONDecodeError, KeyError):
            return False, "Invalid signature file"
    elif sig_legacy_path.exists():
        sig_hex = sig_legacy_path.read_text(encoding="utf-8").strip()
        algo = algorithm
    else:
        return False, "No signature found"

    Ed25519 = _try_ed25519()
    if algo == "ed25519" and Ed25519:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            key = Ed25519PublicKey.from_public_bytes(public_key)
            key.verify(bytes.fromhex(sig_hex), payload)
            return True, ""
        except Exception as exc:
            return False, f"Ed25519 verification failed: {exc}"
    elif algo == "hmac-sha512":
        expected = hmac.new(public_key, payload, hashlib.sha512).hexdigest()
        if hmac.compare_digest(expected, sig_hex):
            return True, ""
        return False, "HMAC-SHA512 verification failed"
    return False, f"Unsupported algorithm: {algo}"


def load_public_key(path: Path) -> bytes:
    """Load public key from file (hex or raw bytes)."""
    data = path.read_text(encoding="utf-8").strip()
    try:
        return bytes.fromhex(data)
    except ValueError:
        return path.read_bytes()


def load_private_key(path: Path) -> bytes:
    """Load private key from file (hex or raw bytes)."""
    data = path.read_text(encoding="utf-8").strip()
    try:
        return bytes.fromhex(data)
    except ValueError:
        return path.read_bytes()
