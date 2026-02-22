"""
MQTT telemetry connector (Data plane Phase 1).
Consumes JSON messages from an MQTT topic and returns records for the pipeline.
Optional dependency: pip install paho-mqtt (or use [mqtt] extra).
"""

from __future__ import annotations

import json
import time
from queue import Empty, Queue
from typing import Any, List, Optional

from waveos.utils import get_logger

logger = get_logger("waveos.collectors.mqtt")


def load_records_from_mqtt(
    broker: str,
    topic: str,
    *,
    max_messages: int = 1000,
    timeout_sec: float = 30.0,
    client_id: Optional[str] = None,
    port: int = 1883,
    records_key: Optional[str] = "records",
) -> List[Any]:
    """
    Subscribe to an MQTT topic and collect JSON payloads as records.
    Each message payload is parsed as JSON; if it is a list, those items are added;
    if it is a dict with key records_key (default "records"), that list is used;
    otherwise the whole object is one record.
    Returns when max_messages reached or timeout_sec elapsed.
    """
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        raise ImportError("MQTT connector requires paho-mqtt: pip install paho-mqtt") from None

    collected: List[Any] = []
    q: Queue = Queue()

    def on_connect(client: Any, userdata: Any, flags: Any, rc: int) -> None:
        if rc != 0:
            logger.warning("MQTT connect result %s", rc)
            return
        client.subscribe(topic)

    def on_message(client: Any, userdata: Any, msg: Any) -> None:
        try:
            raw = msg.payload.decode("utf-8")
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.debug("MQTT message parse error: %s", e)
            return
        if isinstance(payload, list):
            collected.extend(payload)
        elif isinstance(payload, dict) and records_key and records_key in payload:
            items = payload[records_key]
            if isinstance(items, list):
                collected.extend(items)
            else:
                collected.append(payload)
        else:
            collected.append(payload)
        q.put(1)  # signal one message processed

    client = mqtt.Client(client_id=client_id or f"waveos-{int(time.time())}")
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(broker, port=port, keepalive=60)
        client.loop_start()
        deadline = time.monotonic() + timeout_sec
        while len(collected) < max_messages and time.monotonic() < deadline:
            try:
                q.get(timeout=min(1.0, max(0.1, deadline - time.monotonic())))
            except Empty:
                pass
        client.loop_stop()
        client.disconnect()
    except Exception as e:
        logger.warning("MQTT collect error: %s", e)
        raise
    return collected[:max_messages]
