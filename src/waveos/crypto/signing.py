"""Public-key bundle signing — Ed25519 (preferred) with HMAC-SHA512 fallback."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.crypto.signing")


@dataclass
class KeyPair:
    """Asymmetric key pair for signing."""
    algorithm: str  # ed25519 | hmac-sha512
    public_key: bytes
    private_key: bytes
    key_id: str = ""
    created_at: str = ""

    def save(self, directory: Path, prefix: str = "waveos") -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{prefix}.pub").write_bytes(self.public_key)
        (directory / f"{prefix}.key").write_bytes(self.private_key)
        meta = {"algorithm": self.algorithm, "key_id": self.key_id, "created_at": self.created_at}
        (directory / f"{prefix}.meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def _ed25519_available() -> bool:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        return True
    except ImportError:
        return False


def generate_keypair(algorithm: str = "auto", key_id: str = "") -> KeyPair:
    """Generate a signing key pair. Uses Ed25519 if cryptography is installed, else HMAC-SHA512."""
    ts = utc_now().isoformat()
    kid = key_id or f"key-{ts[:10]}-{os.urandom(4).hex()}"

    if algorithm == "auto":
        algorithm = "ed25519" if _ed25519_available() else "hmac-sha512"

    if algorithm == "ed25519" and _ed25519_available():
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
        priv = Ed25519PrivateKey.generate()
        pub = priv.public_key()
        return KeyPair(
            algorithm="ed25519",
            public_key=pub.public_bytes(Encoding.Raw, PublicFormat.Raw),
            private_key=priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()),
            key_id=kid, created_at=ts,
        )

    secret = os.urandom(64)
    return KeyPair(
        algorithm="hmac-sha512",
        public_key=secret, private_key=secret,
        key_id=kid, created_at=ts,
    )


def _compute_bundle_digest(bundle_dir: Path) -> str:
    """Compute deterministic digest of bundle contents (manifest + all artifacts)."""
    h = hashlib.sha512()
    manifest_path = bundle_dir / "bundle.json"
    if manifest_path.exists():
        h.update(manifest_path.read_bytes())
    for p in sorted(bundle_dir.rglob("*")):
        if p.is_file() and p.name not in ("bundle.sig", "bundle.sig.v2", "attestation.json"):
            h.update(str(p.relative_to(bundle_dir)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def sign_bundle(bundle_dir: Path, private_key: bytes, algorithm: str = "ed25519") -> Dict[str, Any]:
    """Sign a bundle and write signature file."""
    digest = _compute_bundle_digest(bundle_dir)

    if algorithm == "ed25519" and _ed25519_available():
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        priv = Ed25519PrivateKey.from_private_bytes(private_key)
        signature = priv.sign(digest.encode("utf-8"))
        sig_hex = signature.hex()
    else:
        sig_hex = hmac.new(private_key, digest.encode("utf-8"), hashlib.sha512).hexdigest()
        algorithm = "hmac-sha512"

    sig_data = {
        "algorithm": algorithm,
        "digest": digest,
        "signature": sig_hex,
        "timestamp": utc_now().isoformat(),
    }
    sig_path = bundle_dir / "bundle.sig.v2"
    sig_path.write_text(json.dumps(sig_data, indent=2) + "\n", encoding="utf-8")
    return sig_data


def verify_bundle_signature(bundle_dir: Path, public_key: bytes, algorithm: str = "ed25519") -> Tuple[bool, str]:
    """Verify a bundle's V2 signature. Returns (ok, message)."""
    sig_path = bundle_dir / "bundle.sig.v2"
    if not sig_path.exists():
        return False, "No V2 signature file found"
    try:
        sig_data = json.loads(sig_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"Cannot read signature: {exc}"

    digest = _compute_bundle_digest(bundle_dir)
    if digest != sig_data.get("digest", ""):
        return False, "Bundle content digest mismatch (bundle modified after signing)"

    stored_algo = sig_data.get("algorithm", "")
    sig_hex = sig_data.get("signature", "")

    if stored_algo == "ed25519" and _ed25519_available():
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            pub = Ed25519PublicKey.from_public_bytes(public_key)
            pub.verify(bytes.fromhex(sig_hex), digest.encode("utf-8"))
            return True, "Ed25519 signature valid"
        except Exception as exc:
            return False, f"Ed25519 verification failed: {exc}"
    elif stored_algo == "hmac-sha512":
        expected = hmac.new(public_key, digest.encode("utf-8"), hashlib.sha512).hexdigest()
        if hmac.compare_digest(expected, sig_hex):
            return True, "HMAC-SHA512 signature valid"
        return False, "HMAC-SHA512 signature mismatch"
    return False, f"Unknown algorithm: {stored_algo}"


def load_public_key(path: Path) -> bytes:
    return path.read_bytes()


def load_private_key(path: Path) -> bytes:
    return path.read_bytes()
