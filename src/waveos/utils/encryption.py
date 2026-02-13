"""Optional encryption at rest for run_meta and evidence artifacts. Requires cryptography + WAVEOS_ENCRYPTION_KEY (Fernet key)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from waveos.utils import get_logger, get_secret

logger = get_logger("waveos.encryption")

_FERNET = None
_MAGIC = b"WAVEOS_ENC_V1|"


def _get_fernet():
    global _FERNET
    if _FERNET is not None:
        return _FERNET
    key = get_secret("WAVEOS_ENCRYPTION_KEY") or get_secret("waveos_encryption_key")
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        _FERNET = Fernet(key.encode("utf-8"))
        return _FERNET
    except Exception as exc:
        logger.warning("Encryption not available: %s", type(exc).__name__)
        _FERNET = False
        return None


def encrypt_bytes(data: bytes) -> Optional[bytes]:
    """Return encrypted payload with magic header, or None if encryption unavailable."""
    f = _get_fernet()
    if not f:
        return None
    try:
        return _MAGIC + f.encrypt(data)
    except Exception:
        return None


def decrypt_bytes(data: bytes) -> Optional[bytes]:
    """Return decrypted payload, or None if not encrypted or decryption fails."""
    if not data.startswith(_MAGIC):
        return None
    f = _get_fernet()
    if not f:
        return None
    try:
        return f.decrypt(data[len(_MAGIC):])
    except Exception:
        return None


def write_json_encrypted(path: Path, payload: Any, *, fallback_plain: bool = True) -> bool:
    """Write JSON payload encrypted if key is set; otherwise write plain (if fallback_plain). Returns True if encrypted."""
    data = json.dumps(payload, indent=2, default=str).encode("utf-8")
    enc = encrypt_bytes(data)
    if enc is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.with_suffix(path.suffix + ".enc").write_bytes(enc)
        if path.exists():
            path.unlink()
        return True
    if fallback_plain:
        from waveos.utils.io import write_json
        write_json(path, payload)
    return False


def read_json_encrypted(path: Path) -> Optional[Any]:
    """Read JSON from path or path.enc (decrypt if encrypted)."""
    enc_path = path.with_suffix(path.suffix + ".enc")
    if enc_path.exists():
        raw = decrypt_bytes(enc_path.read_bytes())
        if raw is not None:
            return json.loads(raw.decode("utf-8"))
    from waveos.utils.io import read_json
    if path.exists():
        return read_json(path)
    return None
