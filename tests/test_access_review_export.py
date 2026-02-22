"""Tests for access review export (Compliance Phase 2)."""

import json
import tempfile
from pathlib import Path

from waveos.utils.rbac import Role


def test_access_review_export_structure() -> None:
    """Export has roles, permission_clearance, token_assignments."""
    from waveos.cli import cmd_access_review_export
    import argparse
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out_path = Path(f.name)
    try:
        args = argparse.Namespace(out=str(out_path), config_obj=None)
        code = cmd_access_review_export(args)
        assert code == 0
        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert "roles" in data
        assert "permission_clearance" in data
        assert "token_assignments" in data
        assert len(data["roles"]) == len(Role)
        role_names = {r["role"] for r in data["roles"]}
        assert role_names == {e.value for e in Role}
        for r in data["roles"]:
            assert "permissions" in r
    finally:
        out_path.unlink(missing_ok=True)
