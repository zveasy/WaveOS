"""KMS provider abstraction — HSM, AWS KMS, Vault Transit, or local keys."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from waveos.utils import get_logger

logger = get_logger("waveos.crypto.kms")


class KMSProviderType(str, Enum):
    LOCAL = "local"
    VAULT_TRANSIT = "vault_transit"
    AWS_KMS = "aws_kms"
    HSM = "hsm"


@dataclass
class KMSProvider:
    provider_type: KMSProviderType = KMSProviderType.LOCAL
    key_dir: str = ""
    vault_addr: str = ""
    vault_key_name: str = ""
    aws_region: str = ""
    aws_key_id: str = ""
    hsm_slot: str = ""

    def get_signing_key_path(self) -> Optional[Path]:
        if self.provider_type == KMSProviderType.LOCAL and self.key_dir:
            key_dir = Path(self.key_dir)
            for ext in (".secret", ".private.pem"):
                for f in key_dir.glob(f"*{ext}"):
                    return f
        return None

    def get_verification_key_path(self) -> Optional[Path]:
        if self.provider_type == KMSProviderType.LOCAL and self.key_dir:
            key_dir = Path(self.key_dir)
            for ext in (".key", ".public.pem"):
                for f in key_dir.glob(f"*{ext}"):
                    return f
        return None

    def to_dict(self) -> dict:
        return {
            "provider_type": self.provider_type.value,
            "key_dir": self.key_dir,
            "vault_addr": self.vault_addr,
            "aws_region": self.aws_region,
        }


def get_kms_provider() -> KMSProvider:
    provider_type = os.getenv("WAVEOS_KMS_PROVIDER", "local")
    return KMSProvider(
        provider_type=KMSProviderType(provider_type),
        key_dir=os.getenv("WAVEOS_KMS_KEY_DIR", ""),
        vault_addr=os.getenv("WAVEOS_VAULT_ADDR", ""),
        vault_key_name=os.getenv("WAVEOS_VAULT_KEY_NAME", "waveos-signing"),
        aws_region=os.getenv("WAVEOS_AWS_KMS_REGION", ""),
        aws_key_id=os.getenv("WAVEOS_AWS_KMS_KEY_ID", ""),
    )
