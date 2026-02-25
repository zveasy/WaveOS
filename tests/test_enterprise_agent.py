"""Tests for agent packaging, atomic install, platform detection (§4-5)."""
from __future__ import annotations
import json, os
from pathlib import Path
from waveos.agent.packaging import detect_platform, generate_systemd_unit, generate_install_script, PlatformFamily, get_device_identity_from_tpm, generate_hardening_profile
from waveos.agent.atomic import atomic_activate, recover_from_power_loss, StoragePolicy, enforce_storage_policy, verify_download_integrity, ChunkedDownloadState

def test_detect_platform():
    info = detect_platform()
    assert info.arch != "" and info.python_version != ""
    assert info.family != PlatformFamily.UNKNOWN or os.name == "nt"

def test_systemd_unit():
    unit = generate_systemd_unit()
    assert "[Service]" in unit and "waveos" in unit

def test_install_script():
    script = generate_install_script()
    assert "#!/bin/bash" in script and "waveos" in script

def test_device_identity():
    ident = get_device_identity_from_tpm()
    assert "device_id" in ident and ident["device_id"] != ""

def test_hardening_profile():
    info = detect_platform()
    profile = generate_hardening_profile(info)
    assert "recommendations" in profile

def test_atomic_activate(tmp_path: Path):
    apps = tmp_path / "apps"
    app_dir = apps / "myapp" / "v1.0"; app_dir.mkdir(parents=True)
    (app_dir / "app.py").write_text("# v1\n")
    result = atomic_activate(apps, "myapp", "v1.0")
    assert result.ok
    assert (apps / "myapp" / "current").is_symlink()
    assert os.readlink(str(apps / "myapp" / "current")) == "v1.0"

def test_atomic_activate_swap(tmp_path: Path):
    apps = tmp_path / "apps"
    for v in ("v1.0", "v2.0"):
        (apps / "myapp" / v).mkdir(parents=True)
    atomic_activate(apps, "myapp", "v1.0")
    result = atomic_activate(apps, "myapp", "v2.0")
    assert result.ok and result.previous_target == "v1.0"
    assert os.readlink(str(apps / "myapp" / "current")) == "v2.0"

def test_power_loss_recovery(tmp_path: Path):
    apps = tmp_path / "apps"
    for v in ("v1.0", "v2.0"):
        (apps / "myapp" / v).mkdir(parents=True)
    atomic_activate(apps, "myapp", "v1.0")
    marker = apps / "myapp" / ".recovery_marker.json"
    marker.write_text(json.dumps({"app_name": "myapp", "new_version": "v2.0", "previous": "v1.0", "status": "activating"}))
    actions = recover_from_power_loss(apps)
    assert len(actions) == 1 and actions[0]["action"] == "reverted"

def test_storage_policy(tmp_path: Path):
    apps = tmp_path / "apps"
    for v in ("v1", "v2", "v3", "v4", "v5", "v6", "v7"):
        (apps / "myapp" / v).mkdir(parents=True)
    result = enforce_storage_policy(apps, "myapp", StoragePolicy(max_versions=3))
    assert len(result["pruned"]) > 0 and len(result["kept"]) <= 3

def test_download_integrity(tmp_path: Path):
    import hashlib
    f = tmp_path / "file.bin"; f.write_bytes(b"hello")
    h = hashlib.sha256(b"hello").hexdigest()
    ok, _ = verify_download_integrity(f, h)
    assert ok
    ok2, err = verify_download_integrity(f, "wrong")
    assert not ok2

def test_chunked_state_roundtrip():
    s = ChunkedDownloadState(bundle_id="b1", total_size=1000, downloaded=500)
    d = s.to_dict()
    r = ChunkedDownloadState.from_dict(d)
    assert r.bundle_id == "b1" and r.downloaded == 500
