from unittest.mock import Mock, patch

from waveos.utils import AlertRoute, route_alerts, send_webhook
from waveos.utils.alert_integrations import send_slack, send_email_smtp, send_email_ses


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


def test_send_slack_formats_message() -> None:
    with patch("waveos.utils.alert_integrations.send_webhook") as mocked:
        send_slack("http://example.com", {"run_id": "run-1"})
        args, _ = mocked.call_args
        assert args[0] == "http://example.com"
        assert "text" in args[1]


def test_send_email_smtp_invokes_smtp() -> None:
    with patch("smtplib.SMTP") as smtp_mock:
        instance = smtp_mock.return_value.__enter__.return_value
        send_email_smtp(
            "ops@example.com",
            "subject",
            "body",
            {
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "smtp_user": "user",
                "smtp_password": "pass",
                "smtp_from": "waveos@example.com",
            },
        )
        instance.starttls.assert_called_once()
        instance.login.assert_called_once()
        instance.send_message.assert_called_once()


def test_send_email_ses_uses_boto3() -> None:
    with patch("waveos.utils.alert_integrations._boto3") as boto_mock:
        client = boto_mock.client.return_value
        send_email_ses(
            "ops@example.com",
            "subject",
            "body",
            {"ses_region": "us-east-1", "ses_from": "waveos@example.com"},
        )
        client.send_email.assert_called_once()
