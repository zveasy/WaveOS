"""WaveOS Compatibility Engine — preflight checks and dependency strategies."""

from waveos.compat.preflight import run_preflight, PreflightResult, PreflightOutcome
from waveos.compat.strategies import RuntimeStrategy, get_strategy

__all__ = [
    "run_preflight",
    "PreflightResult",
    "PreflightOutcome",
    "RuntimeStrategy",
    "get_strategy",
]
