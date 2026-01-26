from unittest.mock import Mock, patch

from waveos.utils import AlertRoute, route_alerts, send_webhook


def test_send_webhook_retries_until_success() -> None:
    success = Mock()
    success.__enter__ = Mock(return_value=success)
    success.__exit__ = Mock(return_value=False)
    success.read = Mock(return_value=b"ok")
    responses = [Exception("fail"), Exception("fail"), success]

    def _side_effect(*_args, **_kwargs):
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    with patch("urllib.request.urlopen", side_effect=_side_effect) as mocked:
        send_webhook("http://example.com", {"ok": True}, retries=2)
        assert mocked.call_count == 3


def test_route_alerts_calls_webhook() -> None:
    routes = [AlertRoute(name="web", destination="webhook", url="http://example.com")]
    events = [{"level": "WARN"}]
    with patch("waveos.utils.alerting.send_webhook") as mocked:
        route_alerts(events, routes, run_id="run-1")
        mocked.assert_called_once()


def test_route_alerts_calls_slack_and_email() -> None:
    routes = [
        AlertRoute(name="slack", destination="slack", url="https://hooks.slack.com/services/test"),
        AlertRoute(name="email", destination="email", url="ops@example.com"),
    ]
    with patch("waveos.utils.alerting.send_slack") as slack_mock, patch(
        "waveos.utils.alerting.send_email"
    ) as email_mock:
        route_alerts([{"level": "ERROR"}], routes, run_id="run-2")
        slack_mock.assert_called_once()
        email_mock.assert_called_once()
