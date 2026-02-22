"""
Actuation reliability layer: ACK/timeout/retry, idempotency keys, outcome recording, optional rollback.

Wraps any RealActuator to add:
- Retry with configurable timeout and count
- Idempotency: skip or dedupe by key (hash of action + entity + params) within TTL
- Record outcome per action: succeeded | no_effect | degraded | unknown
- Optional rollback/compensation when partial apply is detected
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from waveos.models import ActionRecommendation
from waveos.utils import get_logger, utc_now, write_jsonl


class ActionOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    NO_EFFECT = "no_effect"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    SKIPPED_IDEMPOTENT = "skipped_idempotent"
    FAILED = "failed"


@dataclass
class ActionExecutionRecord:
    """Single action execution with idempotency key and outcome."""
    idempotency_key: str
    action: str
    entity_type: str
    entity_id: str
    rationale: str
    parameters: Dict[str, Any]
    started_at: str
    completed_at: str
    outcome: ActionOutcome
    attempt_count: int = 1
    message: Optional[str] = None
    run_id: Optional[str] = None


def _idempotency_key(action: ActionRecommendation) -> str:
    """Stable key for deduplication: hash of action type, entity, and params."""
    payload = {
        "action": action.action.value if hasattr(action.action, "value") else str(action.action),
        "entity_type": action.entity_type,
        "entity_id": action.entity_id,
        "params": dict(sorted((str(k), v) for k, v in action.parameters.items())),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:32]


class IdempotencyStore:
    """In-memory store of recent idempotency keys with TTL (seconds)."""

    def __init__(self, ttl_seconds: float = 300.0, max_keys: int = 10_000) -> None:
        self._ttl = ttl_seconds
        self._max_keys = max_keys
        self._keys: Dict[str, float] = {}  # key -> expiry time (epoch)

    def seen(self, key: str, now: float | None = None) -> bool:
        import time
        now = now or time.time()
        self._evict_expired(now)
        return key in self._keys and self._keys[key] > now

    def add(self, key: str, now: float | None = None) -> None:
        import time
        now = now or time.time()
        self._evict_expired(now)
        if len(self._keys) >= self._max_keys:
            # Remove oldest
            for k in sorted(self._keys, key=lambda k: self._keys[k])[: len(self._keys) // 4]:
                del self._keys[k]
        self._keys[key] = now + self._ttl

    def _evict_expired(self, now: float) -> None:
        expired = [k for k, t in self._keys.items() if t <= now]
        for k in expired:
            del self._keys[k]


class ActuationReliabilityLayer:
    """
    Wraps an inner RealActuator with:
    - Retry (with timeout per attempt)
    - Idempotency (skip if key seen within TTL)
    - Outcome recording (succeeded / no_effect / degraded / unknown / failed)
    - Optional rollback actions when a failure occurs after partial apply
    """

    def __init__(
        self,
        inner: Any,  # RealActuator
        run_id: Optional[str] = None,
        timeout_seconds: float = 10.0,
        retry_count: int = 2,
        idempotency_ttl_seconds: float = 300.0,
        outcomes_path: Optional[Path] = None,
        rollback_actions: Optional[List[ActionRecommendation]] = None,
    ) -> None:
        self.inner = inner
        self.run_id = run_id or ""
        self.timeout_seconds = timeout_seconds
        self.retry_count = retry_count
        self.idempotency = IdempotencyStore(ttl_seconds=idempotency_ttl_seconds)
        self.outcomes_path = outcomes_path
        self.rollback_actions = rollback_actions or []
        self.logger = get_logger("waveos.actuators.reliability")
        self._records: List[ActionExecutionRecord] = []

    def validate(self, action: ActionRecommendation) -> bool:
        return self.inner.validate(action)

    def apply(self, actions: Iterable[ActionRecommendation]) -> None:
        import time
        actions_list = list(actions)
        applied: List[ActionRecommendation] = []
        for action in actions_list:
            key = _idempotency_key(action)
            if self.idempotency.seen(key):
                self._record_outcome(action, key, ActionOutcome.SKIPPED_IDEMPOTENT, 0)
                continue
            started = utc_now().isoformat()
            outcome = ActionOutcome.UNKNOWN
            attempt = 0
            last_exc: Optional[Exception] = None
            for attempt in range(1, self.retry_count + 2):
                try:
                    self._apply_one_with_timeout(action)
                    outcome = ActionOutcome.SUCCEEDED
                    self.idempotency.add(key)
                    applied.append(action)
                    break
                except Exception as exc:
                    last_exc = exc
                    self.logger.warning("Actuation attempt %s failed for %s: %s", attempt, action.entity_id, type(exc).__name__)
                    if attempt <= self.retry_count + 1:
                        time.sleep(0.5 * attempt)
            if outcome == ActionOutcome.UNKNOWN and last_exc:
                outcome = ActionOutcome.FAILED
            self._record_outcome(action, key, outcome, attempt, message=str(last_exc) if last_exc else None)
        if self.rollback_actions and last_exc and applied:
            self.logger.warning("Partial apply detected; running %s rollback actions", len(self.rollback_actions))
            try:
                self.inner.apply(iter(self.rollback_actions))
            except Exception as exc:
                self.logger.warning("Rollback apply failed: %s", type(exc).__name__)
        self._flush_outcomes()

    def _apply_one_with_timeout(self, action: ActionRecommendation) -> None:
        import concurrent.futures
        def _run() -> None:
            self.inner.apply(iter([action]))
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_run)
            try:
                fut.result(timeout=self.timeout_seconds)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(f"Actuation timed out after {self.timeout_seconds}s")

    def _record_outcome(
        self,
        action: ActionRecommendation,
        idempotency_key: str,
        outcome: ActionOutcome,
        attempt_count: int = 1,
        message: Optional[str] = None,
    ) -> None:
        now = utc_now().isoformat()
        rec = ActionExecutionRecord(
            idempotency_key=idempotency_key,
            action=action.action.value if hasattr(action.action, "value") else str(action.action),
            entity_type=action.entity_type,
            entity_id=action.entity_id,
            rationale=action.rationale,
            parameters=dict(action.parameters),
            started_at=now,
            completed_at=now,
            outcome=outcome,
            attempt_count=attempt_count,
            message=message,
            run_id=self.run_id or None,
        )
        self._records.append(rec)

    def _flush_outcomes(self) -> None:
        if not self.outcomes_path or not self._records:
            return
        self.outcomes_path.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "idempotency_key": r.idempotency_key,
                "action": r.action,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "outcome": r.outcome.value,
                "attempt_count": r.attempt_count,
                "message": r.message,
                "run_id": r.run_id,
                "completed_at": r.completed_at,
            }
            for r in self._records
        ]
        write_jsonl(self.outcomes_path, rows)
        self._records.clear()

    def apply_safe(self, actions: Iterable[ActionRecommendation]) -> None:
        actions_list = list(actions)
        allowed = [a for a in actions_list if self.validate(a)]
        if len(allowed) != len(actions_list):
            self.logger.warning("Reliability layer: filtered %s actions by safety", len(list(actions)) - len(allowed))
        self.apply(iter(allowed))
