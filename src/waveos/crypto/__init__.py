"""WaveOS Crypto — public-key signing, KMS interface, anti-rollback controls."""

from waveos.crypto.signing import (
    KeyPair, generate_keypair, sign_bundle, verify_bundle_signature,
    load_public_key, load_private_key,
)
from waveos.crypto.kms import KMSProvider, LocalKMS, get_kms_provider
from waveos.crypto.anti_rollback import (
    VersionEpoch, EpochStore, check_anti_rollback, record_epoch,
)

__all__ = [
    "KeyPair", "generate_keypair", "sign_bundle", "verify_bundle_signature",
    "load_public_key", "load_private_key",
    "KMSProvider", "LocalKMS", "get_kms_provider",
    "VersionEpoch", "EpochStore", "check_anti_rollback", "record_epoch",
]
