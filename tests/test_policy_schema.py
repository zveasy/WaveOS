"""Tests for policy schema validation (Policy Phase 2)."""

import tempfile
from pathlib import Path

import pytest

from waveos.policy.schema import validate_policy_document, validate_policy_file


def test_validate_policy_document_empty_rules() -> None:
    ok_errors = validate_policy_document({"rules": []})
    assert ok_errors == []


def test_validate_policy_document_valid_engine_rule() -> None:
    doc = {"rules": [{"metric": "score", "operator": "<=", "threshold": 0.5, "action": "RATE_LIMIT"}]}
    assert validate_policy_document(doc) == []


def test_validate_policy_document_valid_template_rule() -> None:
    doc = {"name": "nerc", "rules": [{"id": "x", "type": "soc_limit", "min_soc_percent": 10}]}
    assert validate_policy_document(doc) == []


def test_validate_policy_document_invalid_action() -> None:
    doc = {"rules": [{"metric": "score", "operator": "<=", "threshold": 0.5, "action": "INVALID"}]}
    errors = validate_policy_document(doc)
    assert len(errors) >= 1
    assert "action" in errors[0].lower()


def test_validate_policy_document_invalid_operator() -> None:
    doc = {"rules": [{"metric": "score", "operator": "??", "threshold": 0.5}]}
    errors = validate_policy_document(doc)
    assert any("operator" in e.lower() for e in errors)


def test_validate_policy_file_not_found() -> None:
    ok, errors = validate_policy_file(Path("/nonexistent/policy.json"))
    assert ok is False
    assert len(errors) >= 1


def test_validate_policy_file_valid() -> None:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        f.write(b'{"rules":[{"type":"health_gate"}]}')
        f.flush()
        path = Path(f.name)
    try:
        ok, errors = validate_policy_file(path)
        assert ok is True
        assert errors == []
    finally:
        path.unlink()
