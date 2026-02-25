"""WaveOS Registry — secure artifact repository for bundles."""

from waveos.registry.store import RegistryStore, RegistryEntry
from waveos.registry.auth import (
    DeviceCredential, CredentialStore, RateLimiter,
    build_ssl_context, build_client_ssl_context, hash_token,
)
from waveos.registry.client import RegistryClient
from waveos.registry.mirror import RegistryMirror, SyncDirection, SyncResult, TransferReceipt

__all__ = [
    "RegistryStore", "RegistryEntry",
    "DeviceCredential", "CredentialStore", "RateLimiter",
    "build_ssl_context", "build_client_ssl_context", "hash_token",
    "RegistryClient",
    "RegistryMirror", "SyncDirection", "SyncResult", "TransferReceipt",
]
