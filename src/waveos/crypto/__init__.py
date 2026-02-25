"""WaveOS Crypto — enterprise-grade signing, key management, and anti-rollback."""

from waveos.crypto.signing import (
    KeyPair,
    generate_keypair,
    sign_bundle_ed25519,
    verify_bundle_ed25519,
    sign_data,
    verify_signature,
)
from waveos.crypto.keystore import KeyStore, KeyRecord, KeyStatus
from waveos.crypto.anti_rollback import VersionEpoch, ReleaseEpochStore, check_anti_rollback

__all__ = [
    "KeyPair", "generate_keypair", "sign_bundle_ed25519", "verify_bundle_ed25519",
    "sign_data", "verify_signature",
    "KeyStore", "KeyRecord", "KeyStatus",
    "VersionEpoch", "ReleaseEpochStore", "check_anti_rollback",
]
