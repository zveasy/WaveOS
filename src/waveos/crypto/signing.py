"""Public-key signing for release bundles (Ed25519 via hashlib/hmac fallback, or real Ed25519 when available)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.signing")


@dataclass
class KeyPair:
    """Asymmetric key pair (or HMAC shared secret as fallback)."""
    key_id: str
    algorithm: str = "hmac-sha256"
    private_key: str = ""
    public_key: str = ""
    created_at: str = ""
    expires_at: str = ""

    def to_dict(self, include_private: bool = False) -> dict:
        d: Dict[str, Any] = {"key_id": self.key_id, "algorithm": self.algorithm,
                              "public_key": self.public_key, "created_at": self.created_at,
                              "expires_at": self.expires_at}
        if include_private:
            d["private_key"] = self.private_key
        return d

    @classmethod
    def from_dict(cls, d: dict) -> KeyPair:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


def generate_keypair(key_id: str = "", algorithm: str = "hmac-sha256") -> KeyPair:
    """Generate a new key pair. Uses Ed25519 if cryptography is available, otherwise HMAC-SHA256."""
    if not key_id:
        key_id = f"key-{os.urandom(8).hex()}"
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat
        private_key = Ed25519PrivateKey.generate()
        private_bytes = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
        public_bytes = private_key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
        return KeyPair(key_id=key_id, algorithm="ed25519", private_key=private_bytes,
                       public_key=public_bytes, created_at=utc_now().isoformat())
    except ImportError:
        secret = os.urandom(32).hex()
        return KeyPair(key_id=key_id, algorithm="hmac-sha256", private_key=secret,
                       public_key=secret, created_at=utc_now().isoformat())


def _compute_bundle_digest(bundle_dir: Path) -> str:
    """Compute canonical digest of bundle contents (excluding signature files)."""
    manifest_path = bundle_dir / "bundle.json"
    if not manifest_path.exists():
        return ""
    h = hashlib.sha256()
    h.update(manifest_path.read_bytes())
    return h.hexdigest()


def sign_bundle(bundle_dir: Path, key: KeyPair) -> Dict[str, Any]:
    """Sign a bundle manifest and write signature file. Returns signature record."""
    digest = _compute_bundle_digest(bundle_dir)
    if not digest:
        raise ValueError("No bundle.json found")
    manifest_bytes = (bundle_dir / "bundle.json").read_bytes()
    if key.algorithm == "ed25519":
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            private_key = load_pem_private_key(key.private_key.encode(), password=None)
            sig_bytes = private_key.sign(manifest_bytes)
            signature = sig_bytes.hex()
        except (ImportError, Exception) as exc:
            logger.warning("Ed25519 signing failed, falling back to HMAC: %s", exc)
            signature = hmac.new(key.private_key.encode(), manifest_bytes, hashlib.sha256).hexdigest()
            key = KeyPair(key_id=key.key_id, algorithm="hmac-sha256", private_key=key.private_key,
                          public_key=key.public_key)
    else:
        signature = hmac.new(key.private_key.encode(), manifest_bytes, hashlib.sha256).hexdigest()
    sig_record = {
        "signature": signature, "algorithm": key.algorithm, "key_id": key.key_id,
        "digest": digest, "signed_at": utc_now().isoformat(),
    }
    sig_path = bundle_dir / "bundle.sig.json"
    sig_path.write_text(json.dumps(sig_record, indent=2) + "\n", encoding="utf-8")
    old_sig = bundle_dir / "bundle.sig"
    old_sig.write_text(signature + "\n", encoding="utf-8")
    return sig_record


def verify_bundle_signature(bundle_dir: Path, public_key: str = "", key: Optional[KeyPair] = None) -> tuple[bool, str]:
    """Verify bundle signature. Returns (ok, error_message)."""
    sig_json_path = bundle_dir / "bundle.sig.json"
    sig_path = bundle_dir / "bundle.sig"
    manifest_path = bundle_dir / "bundle.json"
    if not manifest_path.exists():
        return False, "No bundle.json"
    manifest_bytes = manifest_path.read_bytes()
    if sig_json_path.exists():
        try:
            sig_record = json.loads(sig_json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False, "Cannot read signature record"
        algorithm = sig_record.get("algorithm", "hmac-sha256")
        signature = sig_record.get("signature", "")
        if algorithm == "ed25519":
            pk = public_key or (key.public_key if key else "")
            if not pk:
                return False, "No public key for Ed25519 verification"
            try:
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                from cryptography.hazmat.primitives.serialization import load_pem_public_key
                pub_key = load_pem_public_key(pk.encode())
                pub_key.verify(bytes.fromhex(signature), manifest_bytes)
                return True, ""
            except ImportError:
                return False, "cryptography library not available for Ed25519"
            except Exception as exc:
                return False, f"Ed25519 verification failed: {exc}"
        else:
            pk = public_key or (key.public_key if key else "") or (key.private_key if key else "")
            if not pk:
                return False, "No key for HMAC verification"
            expected = hmac.new(pk.encode(), manifest_bytes, hashlib.sha256).hexdigest()
            if hmac.compare_digest(expected, signature):
                return True, ""
            return False, "HMAC signature mismatch"
    elif sig_path.exists():
        signature = sig_path.read_text(encoding="utf-8").strip()
        pk = public_key or (key.public_key if key else "") or (key.private_key if key else "")
        if not pk:
            return False, "No key"
        expected = hmac.new(pk.encode(), manifest_bytes, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, signature):
            return True, ""
        return False, "HMAC signature mismatch"
    return False, "No signature file found"


def save_keypair(key: KeyPair, path: Path, include_private: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(key.to_dict(include_private=include_private), indent=2) + "\n", encoding="utf-8")


def load_keypair(path: Path) -> Optional[KeyPair]:
    if not path.exists():
        return None
    try:
        return KeyPair.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return None
