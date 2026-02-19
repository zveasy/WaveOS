#!/usr/bin/env python3
"""
WaveOS Actuator Listener — tail *_requests.jsonl in the actuator output dir and
POST each line to a URL and/or run a command with the JSON on stdin.

Usage:
  WAVEOS_ACTUATOR_DIR=./out/actuator \\
  WAVEOS_ACTUATOR_SDN_URL=http://localhost:8080/reroute \\
  python scripts/actuator_listener.py

Or run with a command for thermal actions:
  WAVEOS_ACTUATOR_THERMAL_CMD=/opt/thermal/handle.sh \\
  python scripts/actuator_listener.py

Poll interval (default 2s): WAVEOS_ACTUATOR_POLL_INTERVAL=2
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

try:
    from urllib.request import Request, urlopen
except ImportError:
    urlopen = None


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _post_json(url: str, payload: dict, timeout: float = 5.0) -> bool:
    if not urlopen:
        return False
    try:
        req = Request(
            url,
            data=json.dumps(payload, default=str).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 201, 202)
    except Exception as e:
        print(f"POST failed: {e}", file=sys.stderr)
        return False


def _run_cmd(cmd: str, payload: dict) -> bool:
    import subprocess
    try:
        p = subprocess.Popen(
            [cmd],
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        p.stdin.write(json.dumps(payload, default=str).encode("utf-8"))
        p.stdin.close()
        p.wait(timeout=10)
        return p.returncode == 0
    except Exception as e:
        print(f"Command failed: {e}", file=sys.stderr)
        return False


def main() -> int:
    actuator_dir = Path(_env("WAVEOS_ACTUATOR_DIR", "out/actuator"))
    sdn_url = _env("WAVEOS_ACTUATOR_SDN_URL")
    thermal_cmd = _env("WAVEOS_ACTUATOR_THERMAL_CMD")
    poll_interval = float(_env("WAVEOS_ACTUATOR_POLL_INTERVAL", "2"))

    if not actuator_dir.is_dir():
        print(f"Actuator dir not found: {actuator_dir}", file=sys.stderr)
        return 1

    # Map file suffix to URL or command
    action_handlers = {}
    if sdn_url:
        action_handlers["reroute_requests.jsonl"] = ("post", sdn_url)
    if thermal_cmd:
        action_handlers["thermal_requests.jsonl"] = ("cmd", thermal_cmd)

    if not action_handlers:
        print("Set WAVEOS_ACTUATOR_SDN_URL and/or WAVEOS_ACTUATOR_THERMAL_CMD", file=sys.stderr)
        return 1

    positions: dict[Path, int] = {}

    while True:
        for path in actuator_dir.glob("*_requests.jsonl"):
            if path.name not in action_handlers:
                continue
            handler_type, target = action_handlers[path.name]
            pos = positions.get(path, 0)
            try:
                with path.open("r", encoding="utf-8") as f:
                    f.seek(pos)
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            payload = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if handler_type == "post":
                            _post_json(target, payload)
                        else:
                            _run_cmd(target, payload)
                    positions[path] = f.tell()
            except FileNotFoundError:
                pass
            except Exception as e:
                print(f"Error reading {path}: {e}", file=sys.stderr)
        time.sleep(poll_interval)


if __name__ == "__main__":
    sys.exit(main())
