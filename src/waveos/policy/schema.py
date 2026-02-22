"""
Policy schema and validation (Policy Phase 2).
Validates policy template JSON: rules with metric/operator/threshold or type-specific fields.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from waveos.models import ActionType
from waveos.utils import get_logger

logger = get_logger("waveos.policy.schema")

VALID_OPERATORS = {"<", "<=", ">", ">=", "==", "!=", "contains", "not_contains"}


def validate_policy_document(data: Dict[str, Any] | List[Any]) -> List[str]:
    """
    Validate a policy document (object with optional name, version, rules or a list of rules).
    Returns a list of error messages; empty if valid.
    """
    errors: List[str] = []
    if isinstance(data, list):
        rules = data
    elif isinstance(data, dict):
        rules = data.get("rules", [])
        if not isinstance(rules, list):
            errors.append("'rules' must be an array")
            return errors
    else:
        errors.append("Policy must be a JSON object or array of rules")
        return errors

    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            errors.append(f"rule[{i}]: must be an object")
            continue
        errs = _validate_rule(rule, i)
        errors.extend(errs)
    return errors


def _validate_rule(rule: Dict[str, Any], index: int) -> List[str]:
    errors: List[str] = []
    prefix = f"rule[{index}]"

    # Engine-style: metric, operator, threshold
    metric = rule.get("metric")
    operator = rule.get("operator")
    threshold = rule.get("threshold")
    action = rule.get("action")
    rule_id = rule.get("id")

    if metric is not None and not isinstance(metric, str):
        errors.append(f"{prefix}: 'metric' must be a string")
    if operator is not None:
        if not isinstance(operator, str):
            errors.append(f"{prefix}: 'operator' must be a string")
        elif operator not in VALID_OPERATORS:
            errors.append(f"{prefix}: 'operator' must be one of {sorted(VALID_OPERATORS)}")
    if action is not None:
        if isinstance(action, str):
            try:
                ActionType(action)
            except ValueError:
                errors.append(f"{prefix}: 'action' must be one of {[e.value for e in ActionType]}")
        elif not isinstance(action, str):
            errors.append(f"{prefix}: 'action' must be a string (ActionType)")
    if rule_id is not None and not isinstance(rule_id, str):
        errors.append(f"{prefix}: 'id' must be a string")
    if rule.get("parameters") is not None and not isinstance(rule.get("parameters"), dict):
        errors.append(f"{prefix}: 'parameters' must be an object")

    # Either (metric + threshold) or type-specific template
    has_engine = (metric is not None or operator is not None or threshold is not None)
    rule_type = rule.get("type")
    has_template = isinstance(rule_type, str)
    if not has_engine and not has_template:
        errors.append(f"{prefix}: rule must have (metric/operator/threshold) or 'type' with type-specific fields")
    if has_engine and threshold is None and operator is not None:
        errors.append(f"{prefix}: 'threshold' required when 'operator' is set")

    return errors


def validate_policy_file(path: Path) -> Tuple[bool, List[str]]:
    """
    Load and validate a policy JSON file. Returns (ok, list of error messages).
    """
    if not path.is_file():
        return False, [f"File not found: {path}"]
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON: {e}"]
    except OSError as e:
        return False, [f"Read error: {e}"]
    errors = validate_policy_document(data)
    return len(errors) == 0, errors
