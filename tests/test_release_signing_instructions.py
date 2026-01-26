from pathlib import Path


def test_release_workflow_includes_signing_steps() -> None:
    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"
    text = workflow.read_text(encoding="utf-8")
    assert "Sign artifacts (keyless OIDC)" in text
    assert "Sign SBOM (keyless OIDC)" in text
    assert "cosign sign-blob" in text
