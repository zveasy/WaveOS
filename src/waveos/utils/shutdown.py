from __future__ import annotations

import signal
from threading import Event
from typing import Callable


_shutdown = Event()


def install_signal_handlers(on_shutdown: Callable[[], None]) -> None:
    def _handler(signum: int, _frame) -> None:
        _shutdown.set()
        on_shutdown()

    _shutdown.clear()
    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def should_shutdown() -> bool:
    return _shutdown.is_set()


def trigger_shutdown(on_shutdown: Callable[[], None] | None = None) -> None:
    _shutdown.set()
    if on_shutdown:
        on_shutdown()
