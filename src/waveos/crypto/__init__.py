"""WaveOS Crypto — public-key signing, KMS interface, anti-rollback controls."""

from waveos.crypto.signing import KeyPair, sign_bundle, verify_bundle_signature, generate_keypair
from waveos.crypto.kms import KMSProvider, LocalKMS, get_kms_provider
from waveos.crypto.anti_rollback import VersionEpoch, check_anti_rollback, record_version_epoch

__all__ = [
    "KeyPair", "sign_bundle", "verify_bundle_signature", "generate_keypair",
    "KMSProvider", "LocalKMS", "get_kms_provider",
    "VersionEpoch", "check_anti_rollback", "record_version_epoch",
]
