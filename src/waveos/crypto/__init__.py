"""WaveOS Crypto — enterprise-grade signing, key management, and anti-rollback."""

from waveos.crypto.signing import (
    KeyPair,
    generate_keypair,
    sign_bundle_ed25519,
    verify_bundle_ed25519,
    sign_bundle_hmac,
    verify_bundle_hmac,
)
from waveos.crypto.keystore import KeyStore, KeyEntry
from waveos.crypto.anti_rollback import (
    ReleaseEpoch,
    check_anti_rollback,
    get_current_epoch,
    record_epoch,
)

__all__ = [
    "KeyPair", "generate_keypair", "sign_bundle_ed25519", "verify_bundle_ed25519",
    "sign_bundle_hmac", "verify_bundle_hmac",
    "KeyStore", "KeyEntry",
    "ReleaseEpoch", "check_anti_rollback", "get_current_epoch", "record_epoch",
]
