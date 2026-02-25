"""Public-key signing for release bundles (beyond HMAC shared-secret)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.signing")


@dataclass
class KeyPair:
    """Represents a signing key pair. For production use Ed25519 or RSA via cryptography lib.
    This implementation uses HMAC-SHA512 as a portable fallback when no crypto library is available,
    plus real Ed25519 when the 'cryptography' package is installed.
    """
    key_id: str
    private_key_path: str = ""
    public_key_path: str = ""
    algorithm: str = "hmac-sha512"
    created_at: str = ""
    expires_at: str = ""
    revoked: bool = False

    def to_dict(self) -> dict:
        return {
            "key_id": self.key_id,
            "public_key_path": self.public_key_path,
            "algorithm": self.algorithm,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "revoked": self.revoked,
        }


def generate_keypair(key_dir: Path, key_id: str = "", algorithm: str = "hmac-sha512") -> KeyPair:
    """Generate a signing key pair."""
    key_dir.mkdir(parents=True, exist_ok=True)
    kid = key_id or f"key-{os.urandom(8).hex()}"

    if algorithm == "ed25519":
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives import serialization
            private_key = Ed25519PrivateKey.generate()
            priv_bytes = private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
            pub_bytes = private_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
            priv_path = key_dir / f"{kid}.private.pem"
            pub_path = key_dir / f"{kid}.public.pem"
            priv_path.write_bytes(priv_bytes)
            pub_path.write_bytes(pub_bytes)
            return KeyPair(key_id=kid, private_key_path=str(priv_path), public_key_path=str(pub_path), algorithm="ed25519", created_at=utc_now().isoformat())
        except ImportError:
            logger.warning("cryptography not installed; falling back to hmac-sha512")
            algorithm = "hmac-sha512"

    secret = os.urandom(64).hex()
    priv_path = key_dir / f"{kid}.secret"
    pub_path = key_dir / f"{kid}.key"
    priv_path.write_text(secret, encoding="utf-8")
    pub_path.write_text(secret, encoding="utf-8")
    return KeyPair(key_id=kid, private_key_path=str(priv_path), public_key_path=str(pub_path), algorithm="hmac-sha512", created_at=utc_now().isoformat())


def _compute_manifest_digest(bundle_dir: Path) -> str:
    manifest_path = bundle_dir / "bundle.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No manifest at {manifest_path}")
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def sign_bundle_rsa(bundle_dir: Path, key: KeyPair) -> str:
    """Sign bundle manifest. Returns signature hex string. Writes to bundle.sig."""
    digest = _compute_manifest_digest(bundle_dir)
    manifest_bytes = (bundle_dir / "bundle.json").read_bytes()

    if key.algorithm == "ed25519":
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives import serialization
            priv_bytes = Path(key.private_key_path).read_bytes()
            private_key = serialization.load_pem_private_key(priv_bytes, password=None)
            signature = private_key.sign(manifest_bytes)
            sig_hex = signature.hex()
            sig_data = {"algorithm": "ed25519", "key_id": key.key_id, "signature": sig_hex, "digest": digest, "timestamp": utc_now().isoformat()}
            (bundle_dir / "bundle.sig").write_text(json.dumps(sig_data, indent=2) + "\n", encoding="utf-8")
            return sig_hex
        except ImportError:
            logger.warning("cryptography not installed; falling back to hmac-sha512")

    secret = Path(key.private_key_path).read_text(encoding="utf-8").strip()
    sig = hmac.new(secret.encode(), manifest_bytes, hashlib.sha512).hexdigest()
    sig_data = {"algorithm": "hmac-sha512", "key_id": key.key_id, "signature": sig, "digest": digest, "timestamp": utc_now().isoformat()}
    (bundle_dir / "bundle.sig").write_text(json.dumps(sig_data, indent=2) + "\n", encoding="utf-8")
    return sig


def verify_bundle_rsa(bundle_dir: Path, key: KeyPair) -> Tuple[bool, str]:
    """Verify bundle signature. Returns (valid, message)."""
    sig_path = bundle_dir / "bundle.sig"
    manifest_path = bundle_dir / "bundle.json"
    if not sig_path.exists():
        return False, "No signature file"
    if not manifest_path.exists():
        return False, "No manifest"

    try:
        sig_data = json.loads(sig_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"Cannot read signature: {exc}"

    algorithm = sig_data.get("algorithm", "hmac-sha512")
    manifest_bytes = manifest_path.read_bytes()
    actual_digest = hashlib.sha256(manifest_bytes).hexdigest()

    if sig_data.get("digest") and sig_data["digest"] != actual_digest:
        return False, "Manifest digest mismatch (tampered)"

    if algorithm == "ed25519":
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            from cryptography.hazmat.primitives import serialization
            pub_bytes = Path(key.public_key_path).read_bytes()
            public_key = serialization.load_pem_public_key(pub_bytes)
            signature = bytes.fromhex(sig_data["signature"])
            public_key.verify(signature, manifest_bytes)
            return True, "Ed25519 signature valid"
        except ImportError:
            return False, "cryptography not installed for Ed25519 verification"
        except Exception as exc:
            return False, f"Ed25519 verification failed: {exc}"

    secret = Path(key.public_key_path).read_text(encoding="utf-8").strip()
    expected = hmac.new(secret.encode(), manifest_bytes, hashlib.sha512).hexdigest()
    if hmac.compare_digest(expected, sig_data.get("signature", "")):
        return True, "HMAC-SHA512 signature valid"
    return False, "Signature mismatch"


def verify_provenance_policy(
    bundle_dir: Path,
    required_ci_identity: str = "",
    required_branch: str = "",
    required_key_id: str = "",
) -> Tuple[bool, list]:
    """Enforce provenance policy: only accept artifacts from specific CI/branch/key."""
    violations = []
    sig_path = bundle_dir / "bundle.sig"
    att_path = bundle_dir / "attestation.json"

    if required_key_id and sig_path.exists():
        try:
            sig_data = json.loads(sig_path.read_text(encoding="utf-8"))
            if sig_data.get("key_id") != required_key_id:
                violations.append(f"Key ID mismatch: expected {required_key_id}, got {sig_data.get('key_id')}")
        except (json.JSONDecodeError, OSError):
            violations.append("Cannot read signature for key_id check")

    if (required_ci_identity or required_branch) and att_path.exists():
        try:
            att = json.loads(att_path.read_text(encoding="utf-8"))
            prov = att.get("provenance", {})
            if required_ci_identity and prov.get("builder_identity") != required_ci_identity:
                violations.append(f"Builder identity mismatch: expected {required_ci_identity}")
            if required_branch and prov.get("branch") != required_branch:
                violations.append(f"Branch mismatch: expected {required_branch}, got {prov.get('branch')}")
        except (json.JSONDecodeError, OSError):
            violations.append("Cannot read attestation for provenance check")
    elif required_ci_identity or required_branch:
        violations.append("No attestation file for provenance check")

    return len(violations) == 0, violations
