"""Tests for registry server, auth, client, mirror (§1)."""
from __future__ import annotations
import json
from pathlib import Path
from waveos.registry.store import RegistryStore, RegistryEntry
from waveos.registry.auth import RegistryAuthenticator, DeviceIdentity, ChannelACL, RateLimiter, CLEARANCE_LEVELS
from waveos.registry.mirror import RegistryMirror, MirrorSyncResult, TransferReceipt

def _make_bundle(tmp_path: Path, bid: str = "b1") -> Path:
    d = tmp_path / f"bundle_{bid}"; d.mkdir()
    (d / "bundle.json").write_text(json.dumps({"bundle_id": bid, "version": "1.0"}))
    (d / "app.py").write_text("# app\n")
    return d

def test_auth_device_identity():
    di = DeviceIdentity(device_id="dev-1", clearance="prod", roles=["ci"])
    d = di.to_dict()
    r = DeviceIdentity.from_dict(d)
    assert r.device_id == "dev-1" and r.clearance == "prod"

def test_auth_token():
    auth = RegistryAuthenticator()
    auth.register_device(DeviceIdentity(device_id="node-1", clearance="prod"))
    token = auth.generate_token("node-1")
    assert auth.authenticate_token(token).device_id == "node-1"
    assert auth.authenticate_token("bad") is None

def test_auth_publish_acl():
    auth = RegistryAuthenticator()
    dev = DeviceIdentity(device_id="ci-bot", clearance="prod", roles=["ci"])
    ok, _ = auth.authorize_publish(dev, "prod")
    assert ok
    human = DeviceIdentity(device_id="human", clearance="prod", roles=[])
    ok2, reason = auth.authorize_publish(human, "prod")
    assert not ok2 and "CI" in reason

def test_auth_download_clearance():
    auth = RegistryAuthenticator()
    low = DeviceIdentity(device_id="d1", clearance="dev")
    ok, _ = auth.authorize_download(low, "prod")
    assert not ok

def test_rate_limiter():
    rl = RateLimiter(max_requests=3, window_sec=60)
    assert rl.allow("x") and rl.allow("x") and rl.allow("x")
    assert not rl.allow("x")
    rl.reset("x")
    assert rl.allow("x")

def test_mirror_sync(tmp_path: Path):
    src = RegistryStore(tmp_path / "source")
    dst = RegistryStore(tmp_path / "dest")
    src.publish(_make_bundle(tmp_path, "b1"), channel="prod")
    mirror = RegistryMirror(src, dst)
    result = mirror.sync()
    assert "b1" in result.synced
    assert len(result.transfer_receipts) == 1

def test_mirror_skip_existing(tmp_path: Path):
    src = RegistryStore(tmp_path / "src")
    dst = RegistryStore(tmp_path / "dst")
    b = _make_bundle(tmp_path, "b1")
    src.publish(b, channel="dev")
    dst.publish(b, channel="dev")
    result = RegistryMirror(src, dst).sync()
    assert "b1" in result.skipped

def test_mirror_scan_hook_reject(tmp_path: Path):
    src = RegistryStore(tmp_path / "src")
    dst = RegistryStore(tmp_path / "dst")
    src.publish(_make_bundle(tmp_path, "b1"))
    result = RegistryMirror(src, dst, scan_hook=lambda p: False).sync()
    assert "b1" in result.failed

def test_transfer_receipt():
    r = TransferReceipt(bundle_id="b1", source_registry="/src", dest_registry="/dst", transfer_time="now")
    assert r.to_dict()["bundle_id"] == "b1"
