"""Public-key signing for WaveOS bundles — Ed25519 with HMAC fallback."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Optional, Tuple

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.signing")


def _try_ed25519():
    """Try to import Ed25519 from cryptography library."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
        from cryptography.hazmat.primitives import serialization
        return Ed25519PrivateKey, Ed25519PublicKey, serialization
    except ImportError:
        return None, None, None


def generate_keypair(output_dir: Path) -> Tuple[Path, Path]:
    """Generate Ed25519 keypair. Falls back to HMAC key file if cryptography not available."""
    output_dir.mkdir(parents=True, exist_ok=True)
    Ed25519PrivateKey, _, serialization = _try_ed25519()

    if Ed25519PrivateKey and serialization:
        private_key = Ed25519PrivateKey.generate()
        private_bytes = private_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        public_bytes = private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        priv_path = output_dir / "waveos-signing.key"
        pub_path = output_dir / "waveos-signing.pub"
        priv_path.write_bytes(private_bytes)
        pub_path.write_bytes(public_bytes)
        os.chmod(str(priv_path), 0o600)
        return priv_path, pub_path

    key = os.urandom(32).hex()
    priv_path = output_dir / "waveos-signing.key"
    pub_path = output_dir / "waveos-signing.pub"
    priv_path.write_text(key + "\n", encoding="utf-8")
    pub_path.write_text(key + "\n", encoding="utf-8")
    os.chmod(str(priv_path), 0o600)
    logger.info("Generated HMAC keypair (cryptography library not available for Ed25519)")
    return priv_path, pub_path


def load_private_key(path: Path):
    _, _, serialization = _try_ed25519()
    if serialization:
        try:
            data = path.read_bytes()
            if b"BEGIN" in data:
                return serialization.load_pem_private_key(data, password=None)
        except Exception:
            pass
    return path.read_text(encoding="utf-8").strip()


def load_public_key(path: Path):
    _, _, serialization = _try_ed25519()
    if serialization:
        try:
            data = path.read_bytes()
            if b"BEGIN" in data:
                return serialization.load_pem_public_key(data)
        except Exception:
            pass
    return path.read_text(encoding="utf-8").strip()


def sign_bundle_ed25519(bundle_dir: Path, private_key_path: Path) -> str:
    """Sign bundle manifest with Ed25519 (or HMAC fallback). Returns hex signature."""
    manifest_path = bundle_dir / "bundle.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No manifest at {manifest_path}")

    payload = manifest_path.read_bytes()
    key = load_private_key(private_key_path)

    if isinstance(key, str):
        sig = hmac.new(key.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    else:
        sig_bytes = key.sign(payload)
        sig = sig_bytes.hex()

    sig_path = bundle_dir / "bundle.sig"
    sig_data = {"algorithm": "ed25519" if not isinstance(key, str) else "hmac-sha256",
                "signature": sig, "signed_at": utc_now().isoformat()}
    sig_path.write_text(json.dumps(sig_data, indent=2) + "\n", encoding="utf-8")
    return sig


def verify_bundle_ed25519(bundle_dir: Path, public_key_path: Path) -> Tuple[bool, str]:
    """Verify bundle signature. Returns (ok, message)."""
    manifest_path = bundle_dir / "bundle.json"
    sig_path = bundle_dir / "bundle.sig"
    if not manifest_path.exists():
        return False, "no manifest"
    if not sig_path.exists():
        return False, "no signature"

    try:
        sig_data = json.loads(sig_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False, "invalid signature file"

    payload = manifest_path.read_bytes()
    sig_hex = sig_data.get("signature", "")
    algo = sig_data.get("algorithm", "hmac-sha256")
    key = load_public_key(public_key_path)

    if algo == "hmac-sha256" or isinstance(key, str):
        expected = hmac.new(key.encode("utf-8") if isinstance(key, str) else key, payload, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, sig_hex):
            return True, "hmac-sha256 verified"
        return False, "hmac signature mismatch"

    try:
        sig_bytes = bytes.fromhex(sig_hex)
        key.verify(sig_bytes, payload)
        return True, "ed25519 verified"
    except Exception as exc:
        return False, f"ed25519 verification failed: {exc}"
