"""WaveOS Crypto — enterprise trust model with public-key signing, KMS, and anti-rollback."""

from waveos.crypto.signing import KeyPair, sign_bundle_rsa, verify_bundle_rsa, generate_keypair
from waveos.crypto.kms import KMSProvider, get_kms_provider
from waveos.crypto.anti_rollback import VersionEpoch, check_anti_rollback, record_epoch

__all__ = [
    "KeyPair", "sign_bundle_rsa", "verify_bundle_rsa", "generate_keypair",
    "KMSProvider", "get_kms_provider",
    "VersionEpoch", "check_anti_rollback", "record_epoch",
]
