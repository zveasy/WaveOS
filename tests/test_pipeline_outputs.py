from pathlib import Path

from waveos.models import ActionRecommendation, ActionType, Event, EventLevel, HealthScore, HealthStatus
from waveos.reporting import write_outputs
from waveos.utils import read_json, read_jsonl


def test_write_outputs_creates_reports(tmp_path: Path) -> None:
    scores = [
        HealthScore(
            entity_type="link",
            entity_id="link-1",
            score=90.0,
            status=HealthStatus.PASS,
            drivers=[],
            window_start="2025-01-01T00:00:00Z",
            window_end="2025-01-01T00:05:00Z",
        )
    ]
    events = [
        Event(
            timestamp="2025-01-01T00:05:00Z",
            level=EventLevel.INFO,
            message="Baseline healthy",
        )
    ]
    actions = [
        ActionRecommendation(
            action=ActionType.REROUTE,
            entity_type="link",
            entity_id="link-1",
            rationale="Test",
        )
    ]
    report_path = write_outputs(tmp_path, scores, events, actions)
    assert report_path.exists()
    assert (tmp_path / "health_summary.json").exists()
    assert (tmp_path / "events.jsonl").exists()
    assert (tmp_path / "actions.json").exists()
    assert read_json(tmp_path / "health_summary.json")[0]["entity_id"] == "link-1"
    assert read_jsonl(tmp_path / "events.jsonl")[0]["level"] == "INFO"
