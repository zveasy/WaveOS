"""WaveOS Crypto — public-key signing, KMS interface, anti-rollback controls."""

from waveos.crypto.signing import (
    generate_keypair,
    sign_bundle_ed25519,
    verify_bundle_ed25519,
    load_public_key,
    load_private_key,
)
from waveos.crypto.kms import KMSProvider, EnvKMSProvider, FileKMSProvider
from waveos.crypto.anti_rollback import (
    VersionEpoch,
    check_anti_rollback,
    get_current_epoch,
    record_epoch,
)

__all__ = [
    "generate_keypair", "sign_bundle_ed25519", "verify_bundle_ed25519",
    "load_public_key", "load_private_key",
    "KMSProvider", "EnvKMSProvider", "FileKMSProvider",
    "VersionEpoch", "check_anti_rollback", "get_current_epoch", "record_epoch",
]
