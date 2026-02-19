"""Tests for HTTP pull collector."""

from unittest.mock import patch

import pytest

from waveos.collectors.http import load_records_from_url


def test_load_records_from_url_json_array() -> None:
    with patch("waveos.collectors.http.urlopen") as m:
        m.return_value.__enter__.return_value.read.return_value = b'[{"link_id":"L1"},{"link_id":"L2"}]'
        records = load_records_from_url("http://localhost/telemetry")
    assert len(records) == 2
    assert records[0]["link_id"] == "L1"
    assert records[1]["link_id"] == "L2"


def test_load_records_from_url_records_key() -> None:
    with patch("waveos.collectors.http.urlopen") as m:
        m.return_value.__enter__.return_value.read.return_value = b'{"records":[{"link_id":"L1"}]}'
        records = load_records_from_url("http://localhost/telemetry")
    assert len(records) == 1
    assert records[0]["link_id"] == "L1"


def test_load_records_from_url_empty() -> None:
    with patch("waveos.collectors.http.urlopen") as m:
        m.return_value.__enter__.return_value.read.return_value = b""
        records = load_records_from_url("http://localhost/telemetry")
    assert records == []
