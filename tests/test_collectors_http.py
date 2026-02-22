"""Tests for HTTP pull collector."""

from unittest.mock import patch

import pytest

from waveos.collectors.http import load_records_from_url


def test_load_records_from_url_json_array() -> None:
    # Collector reads in chunks; first read returns data, second returns b"" to stop.
    with patch("waveos.collectors.http.urlopen") as m:
        resp = m.return_value.__enter__.return_value
        resp.read.side_effect = [b'[{"link_id":"L1"},{"link_id":"L2"}]', b""]
        records = load_records_from_url("http://localhost/telemetry")
    assert len(records) == 2
    assert records[0]["link_id"] == "L1"
    assert records[1]["link_id"] == "L2"


def test_load_records_from_url_records_key() -> None:
    with patch("waveos.collectors.http.urlopen") as m:
        resp = m.return_value.__enter__.return_value
        resp.read.side_effect = [b'{"records":[{"link_id":"L1"}]}', b""]
        records = load_records_from_url("http://localhost/telemetry")
    assert len(records) == 1
    assert records[0]["link_id"] == "L1"


def test_load_records_from_url_empty() -> None:
    with patch("waveos.collectors.http.urlopen") as m:
        resp = m.return_value.__enter__.return_value
        resp.read.side_effect = [b"", b""]
        records = load_records_from_url("http://localhost/telemetry")
    assert records == []
