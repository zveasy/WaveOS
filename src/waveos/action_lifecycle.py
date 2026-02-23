"""
Action transaction model (Implementation Priorities §2): lifecycle states, idempotency, cooldown.

States: PROPOSED → DISPATCHED → ACKED → VERIFIED (terminal: FAILED, ROLLED_BACK, CANCELLED).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from waveos.models import ActionRecommendation, ActionState, ActionOutcome
from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.action_lifecycle")

# Type for store: any object with save_action_transaction, get_action_by_idempotency_key, update_action_transaction_state, get_last_dispatched_at
StoreLike = Any


def _idempotency_key(action: ActionRecommendation) -> str:
    """Stable key for same logical action (entity + type + params) to detect duplicates."""
    atype = action.action.value if hasattr(action.action, "value") else str(action.action)
    params_canon = json.dumps(action.parameters, sort_keys=True, default=str)
    raw = f"{action.entity_type}:{action.entity_id}:{atype}:{params_canon}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _action_type_str(action: ActionRecommendation) -> str:
    return action.action.value if hasattr(action.action, "value") else str(action.action)


def propose_actions(
    actions: List[ActionRecommendation],
    run_id: str,
    store: Optional[StoreLike] = None,
    idempotency_ttl_sec: float = 300.0,
    cooldown_sec: float = 0.0,
) -> Tuple[List[Tuple[ActionRecommendation, Dict[str, Any]]], List[Tuple[ActionRecommendation, str]]]:
    """
    Filter actions by idempotency and cooldown; create PROPOSED transactions for those to dispatch.
    Returns ([(action, txn_dict), ...], [(skipped_action, reason), ...]).
    """
    to_dispatch: List[Tuple[ActionRecommendation, Dict[str, Any]]] = []
    skipped: List[Tuple[ActionRecommendation, str]] = []

    now_iso = utc_now().isoformat()

    for action in actions:
        key = _idempotency_key(action)
        if store:
            existing = store.get_action_by_idempotency_key(key)
            if existing:
                state = existing.get("state")
                if state in ("ACKED", "VERIFIED") and existing.get("acked_at"):
                    skipped.append((action, "idempotent: already applied"))
                    continue
                if state in ("PROPOSED", "DISPATCHED"):
                    skipped.append((action, "idempotent: in progress"))
                    continue

            if cooldown_sec > 0:
                last = store.get_last_dispatched_at(action.entity_type, action.entity_id)
                if last:
                    try:
                        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                        if (utc_now() - last_dt).total_seconds() < cooldown_sec:
                            skipped.append((action, f"cooldown: {cooldown_sec}s"))
                            continue
                    except (ValueError, TypeError):
                        pass

        action_id = f"act-{uuid.uuid4().hex[:12]}"
        txn = {
            "action_id": action_id,
            "idempotency_key": key,
            "state": ActionState.PROPOSED.value,
            "run_id": run_id,
            "action_type": _action_type_str(action),
            "entity_type": action.entity_type,
            "entity_id": action.entity_id,
            "rationale": action.rationale,
            "parameters": action.parameters,
            "proposed_at": now_iso,
            "dispatched_at": None,
            "acked_at": None,
            "verified_at": None,
            "outcome": None,
            "verification_summary": None,
            "ack_message": None,
            "actual_state": None,
            "error_message": None,
            "details": {},
        }
        if store:
            store.save_action_transaction(txn)
        to_dispatch.append((action, txn))

    return to_dispatch, skipped


def record_dispatched(action_id: str, store: Optional[StoreLike], run_id: str = "") -> None:
    """Mark action as DISPATCHED."""
    if not store:
        return
    now = utc_now().isoformat()
    store.update_action_transaction_state(
        action_id,
        ActionState.DISPATCHED.value,
        dispatched_at=now,
    )


def record_acked(
    action_id: str,
    store: Optional[StoreLike],
    ack_message: Optional[str] = None,
    actual_state: Optional[Dict[str, Any]] = None,
) -> None:
    """Mark action as ACKED (device acknowledged)."""
    if not store:
        return
    store.update_action_transaction_state(
        action_id,
        ActionState.ACKED.value,
        acked_at=utc_now().isoformat(),
        ack_message=ack_message,
        actual_state=actual_state,
    )


def record_verified(
    action_id: str,
    store: Optional[StoreLike],
    outcome: str,
    verification_summary: Optional[str] = None,
) -> None:
    """Mark action as VERIFIED with closed-loop outcome (effective / no_effect / harmful / unknown)."""
    if not store:
        return
    store.update_action_transaction_state(
        action_id,
        ActionState.VERIFIED.value,
        verified_at=utc_now().isoformat(),
        outcome=outcome,
        verification_summary=verification_summary,
    )


def record_failed(action_id: str, store: Optional[StoreLike], error_message: str) -> None:
    """Mark action as FAILED."""
    if not store:
        return
    store.update_action_transaction_state(
        action_id,
        ActionState.FAILED.value,
        error_message=error_message,
    )


def record_rolled_back(action_id: str, store: Optional[StoreLike], message: Optional[str] = None) -> None:
    """Mark action as ROLLED_BACK."""
    if not store:
        return
    store.update_action_transaction_state(
        action_id,
        ActionState.ROLLED_BACK.value,
        error_message=message or "rollback",
    )


def record_cancelled(action_id: str, store: Optional[StoreLike], reason: Optional[str] = None) -> None:
    """Mark action as CANCELLED."""
    if not store:
        return
    store.update_action_transaction_state(
        action_id,
        ActionState.CANCELLED.value,
        error_message=reason,
    )
