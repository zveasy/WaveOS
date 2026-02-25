"""WaveOS Crypto — public-key signing, KMS interface, anti-rollback controls."""

from waveos.crypto.signing import (
    KeyPair, generate_keypair, sign_bundle_public_key, verify_bundle_public_key,
    load_public_key, load_private_key,
)
from waveos.crypto.kms import KMSProvider, LocalKMS, get_kms_provider
from waveos.crypto.anti_rollback import (
    VersionEpoch, check_anti_rollback, record_installed_epoch,
    get_current_epoch, ReleaseEpochStore,
)

__all__ = [
    "KeyPair", "generate_keypair", "sign_bundle_public_key", "verify_bundle_public_key",
    "load_public_key", "load_private_key",
    "KMSProvider", "LocalKMS", "get_kms_provider",
    "VersionEpoch", "check_anti_rollback", "record_installed_epoch",
    "get_current_epoch", "ReleaseEpochStore",
]
