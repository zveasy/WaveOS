from datetime import datetime, timezone

from waveos.models import BaselineStats, HealthStatus, RunStats
from waveos.scoring import score_links


def test_score_links_detects_spike() -> None:
    base = BaselineStats(
        entity_type="link",
        entity_id="link-1",
        metrics={"errors": 1.0, "temperature_c": 40.0},
        window_start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        window_end=datetime(2025, 1, 1, 0, 5, tzinfo=timezone.utc),
    )
    run = RunStats(
        entity_type="link",
        entity_id="link-1",
        metrics={"errors": 4.0, "temperature_c": 42.0},
        window_start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        window_end=datetime(2025, 1, 1, 0, 5, tzinfo=timezone.utc),
    )
    scores = score_links({"link-1": base}, {"link-1": run})
    assert scores[0].status in {HealthStatus.WARN, HealthStatus.FAIL}
    assert any("errors" in driver for driver in scores[0].drivers)
