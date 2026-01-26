import json
import logging
from waveos.utils import counters, histograms, install_signal_handlers, retry, setup_logging, trigger_shutdown, should_shutdown


def test_structured_json_logging() -> None:
    setup_logging()
    logger = logging.getLogger("waveos.test")
    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(self.format(record))

    handler = _Capture()
    handler.setFormatter(logging.getLogger().handlers[0].formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.info("hello")

    assert records
    payload = json.loads(records[0])
    assert payload["message"] == "hello"
    assert payload["logger"] == "waveos.test"


def test_metrics_smoke_singleton() -> None:
    assert counters() is counters()
    assert histograms() is histograms()


def test_retry_eventually_succeeds() -> None:
    attempts = {"count": 0}

    def _fn() -> int:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("fail")
        return 42

    assert retry(_fn, retries=3, base_delay=0.01, max_delay=0.02) == 42


def test_shutdown_flag_set() -> None:
    called = {"value": False}

    def _on_shutdown() -> None:
        called["value"] = True

    install_signal_handlers(_on_shutdown)
    trigger_shutdown(_on_shutdown)
    assert called["value"] is True
    assert should_shutdown() is True
