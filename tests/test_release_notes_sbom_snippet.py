from pathlib import Path


def test_release_notes_include_sbom_verify_snippet() -> None:
    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"
    text = workflow.read_text(encoding="utf-8")
    assert "Verify SBOM" in text
    assert "cosign verify-blob" in text
    assert "sbom.spdx.json.sig" in text
