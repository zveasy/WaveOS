from pathlib import Path

from waveos.utils import CircuitBreaker, write_json, write_jsonl


def test_circuit_breaker_opens_after_failures() -> None:
    breaker = CircuitBreaker(max_failures=2, reset_after=0.01)
    assert breaker.allow() is True
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.allow() is False


def test_write_json_atomic(tmp_path: Path) -> None:
    path = tmp_path / "output" / "data.json"
    write_json(path, {"value": 1})
    assert path.exists()
    assert path.read_text(encoding="utf-8").strip().startswith("{")


def test_write_jsonl_atomic(tmp_path: Path) -> None:
    path = tmp_path / "output" / "data.jsonl"
    write_jsonl(path, [{"value": 1}, {"value": 2}])
    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
