from __future__ import annotations

import subprocess
import time
from typing import List

from waveos.utils import get_logger


def supervise(command: List[str], max_restarts: int = 3, backoff_seconds: float = 1.0) -> int:
    logger = get_logger("waveos.supervisor")
    restarts = 0
    while True:
        logger.info("Starting supervised process: %s", " ".join(command))
        result = subprocess.run(command, check=False)
        if result.returncode == 0:
            return 0
        restarts += 1
        logger.warning("Process exited code=%s restarts=%s/%s", result.returncode, restarts, max_restarts)
        if restarts > max_restarts:
            return result.returncode
        time.sleep(backoff_seconds)
