"""Unit tests for SdnRestAdapter with mock HTTP."""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest

from waveos.actuators.adapters.base import AdapterOutcome
from waveos.actuators.adapters.sdn_rest import SdnRestAdapter
from waveos.models import ActionRecommendation, ActionType


def _action(
    entity_id: str = "link-1",
    action_type: ActionType = ActionType.REROUTE,
    params: dict | None = None,
) -> ActionRecommendation:
    return ActionRecommendation(
        action=action_type,
        entity_type="link",
        entity_id=entity_id,
        rationale="test",
        parameters=params or {},
    )


class TestSdnRestAdapter:
    def test_no_url_returns_not_applicable(self) -> None:
        adapter = SdnRestAdapter(base_url="", timeout_seconds=5.0)
        result = adapter.apply_one(_action("link-1", ActionType.REROUTE), timeout_seconds=2.0)
        assert result.outcome == AdapterOutcome.NOT_APPLICABLE
        assert "No SDN URL" in (result.message or "")

    def test_http_200_returns_succeeded(self) -> None:
        adapter = SdnRestAdapter(base_url="http://localhost:9999/sdn", timeout_seconds=5.0)
        mock_resp = Mock()
        mock_resp.status = 200
        mock_resp.length = 0
        mock_resp.read = Mock(return_value=b"ok")
        mock_resp.__enter__ = Mock(return_value=mock_resp)
        mock_resp.__exit__ = Mock(return_value=False)
        with patch("waveos.actuators.adapters.sdn_rest.urllib.request.urlopen", return_value=mock_resp) as urlopen:
            result = adapter.apply_one(_action("link-1", ActionType.REROUTE), timeout_seconds=2.0)
        assert result.outcome == AdapterOutcome.SUCCEEDED
        assert result.ack is True
        urlopen.assert_called_once()
        call_args = urlopen.call_args
        req = call_args[0][0]
        assert req.get_full_url() == "http://localhost:9999/sdn"
        assert json.loads(req.data)["entity_id"] == "link-1"
        assert json.loads(req.data)["action"] == "REROUTE"

    def test_http_4xx_returns_no_effect(self) -> None:
        adapter = SdnRestAdapter(base_url="http://localhost:9999/sdn", timeout_seconds=5.0)
        mock_resp = Mock()
        mock_resp.status = 400
        mock_resp.length = 0
        mock_resp.read = Mock(return_value=b"bad request")
        mock_resp.__enter__ = Mock(return_value=mock_resp)
        mock_resp.__exit__ = Mock(return_value=False)
        with patch("waveos.actuators.adapters.sdn_rest.urllib.request.urlopen", return_value=mock_resp):
            result = adapter.apply_one(_action("link-1", ActionType.RATE_LIMIT), timeout_seconds=2.0)
        assert result.outcome == AdapterOutcome.NO_EFFECT
        assert result.ack is True

    def test_http_error_returns_unknown(self) -> None:
        import urllib.error
        adapter = SdnRestAdapter(base_url="http://localhost:9999/sdn", timeout_seconds=5.0)
        with patch("waveos.actuators.adapters.sdn_rest.urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
            result = adapter.apply_one(_action("link-1", ActionType.QOS_PRIORITIZATION), timeout_seconds=2.0)
        assert result.outcome == AdapterOutcome.UNKNOWN
        assert result.ack is False
        assert result.message is not None

    def test_applies_to_supported_types_only(self) -> None:
        adapter = SdnRestAdapter(base_url="http://x")
        assert adapter.applies_to(_action("link-1", ActionType.REROUTE)) is True
        assert adapter.applies_to(_action("link-1", ActionType.RATE_LIMIT)) is True
        assert adapter.applies_to(_action("link-1", ActionType.QOS_PRIORITIZATION)) is True
        assert adapter.applies_to(_action("link-1", ActionType.POWER_THERMAL_CONSTRAINT)) is False

    def test_urls_by_action_override_base(self) -> None:
        adapter = SdnRestAdapter(
            base_url="http://default/sdn",
            urls_by_action={"REROUTE": "http://reroute/sdn"},
            timeout_seconds=5.0,
        )
        mock_resp = Mock()
        mock_resp.status = 200
        mock_resp.length = 0
        mock_resp.read = Mock(return_value=b"")
        mock_resp.__enter__ = Mock(return_value=mock_resp)
        mock_resp.__exit__ = Mock(return_value=False)
        with patch("waveos.actuators.adapters.sdn_rest.urllib.request.urlopen", return_value=mock_resp) as urlopen:
            adapter.apply_one(_action("link-1", ActionType.REROUTE), timeout_seconds=2.0)
        assert urlopen.call_args[0][0].get_full_url() == "http://reroute/sdn"
