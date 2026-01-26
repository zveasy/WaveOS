from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")


def retry(
    fn: Callable[[], T],
    retries: int = 3,
    base_delay: float = 0.2,
    max_delay: float = 2.0,
) -> T:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt >= retries:
                break
            delay = min(max_delay, base_delay * (2**attempt))
            delay = delay * (0.8 + random.random() * 0.4)
            time.sleep(delay)
    if last_exc:
        raise last_exc
    raise RuntimeError("Retry failed without exception")
