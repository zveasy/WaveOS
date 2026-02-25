"""Tests for crypto signing, KMS, anti-rollback, keystore (§3)."""
from __future__ import annotations
import json
from pathlib import Path
from waveos.crypto.signing import generate_keypair, sign_bundle, verify_bundle_signature, save_keypair, load_keypair, KeyPair
from waveos.crypto.kms import LocalKMS, get_kms_provider
from waveos.crypto.anti_rollback import VersionEpoch, check_anti_rollback, record_version_epoch, load_version_epoch
from waveos.crypto.keystore import KeyStore, KeyEntry

def _bundle(tmp: Path) -> Path:
    d = tmp / "bundle"; d.mkdir()
    (d / "bundle.json").write_text(json.dumps({"bundle_id": "test", "version": "1.0"}))
    return d

def test_generate_hmac_keypair():
    kp = generate_keypair(key_id="k1", algorithm="hmac-sha256")
    assert kp.key_id == "k1" and kp.algorithm in ("hmac-sha256", "ed25519")

def test_sign_and_verify_hmac(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)
    kp = generate_keypair(key_id="k1")
    sig = sign_bundle(bundle_dir, kp)
    assert sig["algorithm"] in ("hmac-sha256", "ed25519")
    ok, err = verify_bundle_signature(bundle_dir, key=kp)
    assert ok and err == ""

def test_verify_wrong_key(tmp_path: Path):
    bundle_dir = _bundle(tmp_path)
    kp = generate_keypair(key_id="k1")
    sign_bundle(bundle_dir, kp)
    bad = generate_keypair(key_id="k2")
    ok, err = verify_bundle_signature(bundle_dir, key=bad)
    assert not ok

def test_keypair_save_load(tmp_path: Path):
    kp = generate_keypair(key_id="persist")
    p = tmp_path / "key.json"
    save_keypair(kp, p)
    loaded = load_keypair(p)
    assert loaded.key_id == "persist"

def test_local_kms(tmp_path: Path):
    kms = LocalKMS(tmp_path / "keys")
    key = kms.create_key(key_id="test-key")
    assert kms.get_signing_key("test-key") is not None
    assert "test-key" in kms.list_keys()
    kms.revoke_key("test-key")
    assert kms.get_signing_key("test-key") is None

def test_kms_rotate(tmp_path: Path):
    kms = LocalKMS(tmp_path / "keys")
    kms.create_key(key_id="old")
    new = kms.rotate_key("old")
    assert new is not None and new.key_id != "old"
    assert kms.get_signing_key("old") is None

def test_anti_rollback_pass():
    epoch = VersionEpoch(app_name="app", channel="prod", epoch=1, min_version="1.0.0")
    ok, _ = check_anti_rollback("2.0.0", epoch)
    assert ok

def test_anti_rollback_block():
    epoch = VersionEpoch(app_name="app", channel="prod", epoch=1, min_version="2.0.0")
    ok, msg = check_anti_rollback("1.5.0", epoch)
    assert not ok and "Anti-rollback" in msg

def test_anti_rollback_override():
    epoch = VersionEpoch(app_name="app", channel="prod", epoch=1, min_version="2.0.0")
    ok, msg = check_anti_rollback("1.0.0", epoch, allow_override=True)
    assert ok and "override" in msg.lower()

def test_version_epoch_persistence(tmp_path: Path):
    p = tmp_path / "epochs.json"
    record_version_epoch(p, "myapp", "prod", "3.0.0", updater="ci")
    ve = load_version_epoch(p, "myapp", "prod")
    assert ve.min_version == "3.0.0" and ve.epoch == 1

def test_keystore(tmp_path: Path):
    ks = KeyStore(tmp_path / "store")
    ks.add_key(KeyEntry(key_id="k1", public_key_hex="abc123", created_at="2025-01-01"))
    assert ks.get_key("k1").key_id == "k1"
    assert len(ks.get_valid_keys()) == 1
    ks.revoke_key("k1")
    assert len(ks.get_valid_keys()) == 0

def test_keystore_export(tmp_path: Path):
    ks = KeyStore(tmp_path / "store")
    ks.add_key(KeyEntry(key_id="k1", public_key_hex="pubkey1"))
    count = ks.export_trust_store(tmp_path / "trust")
    assert count == 1 and (tmp_path / "trust" / "k1.key").exists()
