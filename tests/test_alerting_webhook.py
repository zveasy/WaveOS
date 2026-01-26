from unittest.mock import Mock, patch

from waveos.utils import send_webhook


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
