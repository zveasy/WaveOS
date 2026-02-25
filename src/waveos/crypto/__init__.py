"""WaveOS Crypto — enterprise cryptographic trust: public-key signing, KMS, anti-rollback."""

from waveos.crypto.signing import KeyPair, generate_keypair, sign_bundle, verify_bundle_signature, load_public_key, load_private_key
from waveos.crypto.kms import KMSProvider, get_kms_provider
from waveos.crypto.anti_rollback import VersionEpoch, check_anti_rollback, get_current_epoch, record_epoch

__all__ = [
    "KeyPair", "generate_keypair", "sign_bundle", "verify_bundle_signature",
    "load_public_key", "load_private_key",
    "KMSProvider", "get_kms_provider",
    "VersionEpoch", "check_anti_rollback", "get_current_epoch", "record_epoch",
]
