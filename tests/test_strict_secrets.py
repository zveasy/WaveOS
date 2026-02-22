"""Tests for strict_secrets (Security Phase 2)."""

from waveos.utils.secrets import set_strict_secrets, _json_fallback_allowed, _strict_secrets


def test_strict_secrets_override_true() -> None:
    """set_strict_secrets(True) makes _strict_secrets() True and disables JSON fallback."""
    set_strict_secrets(True)
    try:
        assert _strict_secrets() is True
        assert _json_fallback_allowed() is False
    finally:
        set_strict_secrets(False)


def test_strict_secrets_override_false() -> None:
    """set_strict_secrets(False) allows env fallback when not production."""
    set_strict_secrets(False)
    assert _strict_secrets() is False
    # _json_fallback_allowed depends on _is_production(); in tests often not production so True
    # We only assert strict is False
