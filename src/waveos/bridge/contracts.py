"""Bridge contracts — interface schemas, adapter validation, routing enforcement, compat testing, rollback."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.bridge.contracts")


@dataclass
class InterfaceContract:
    """Versioned interface contract between legacy and new system."""
    contract_id: str
    version: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    invariants: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"contract_id": self.contract_id, "version": self.version,
                "input_schema": self.input_schema, "output_schema": self.output_schema,
                "invariants": self.invariants}

    @classmethod
    def from_dict(cls, d: dict) -> InterfaceContract:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


def validate_against_contract(data: Dict[str, Any], contract: InterfaceContract,
                               direction: str = "input") -> Tuple[bool, List[str]]:
    """Validate data against contract schema (simplified type/required check)."""
    schema = contract.input_schema if direction == "input" else contract.output_schema
    errors: List[str] = []
    required = schema.get("required", [])
    for field_name in required:
        if field_name not in data:
            errors.append(f"Missing required field: {field_name}")
    properties = schema.get("properties", {})
    for field_name, field_spec in properties.items():
        if field_name in data:
            expected_type = field_spec.get("type", "")
            value = data[field_name]
            type_map = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}
            if expected_type in type_map and not isinstance(value, type_map[expected_type]):
                errors.append(f"Field {field_name}: expected {expected_type}, got {type(value).__name__}")
    return len(errors) == 0, errors


@dataclass
class AdapterValidationResult:
    """Result of validating an adapter transformation."""
    adapter_name: str
    passed: bool
    input_valid: bool = True
    output_valid: bool = True
    transformation_correct: bool = True
    errors: List[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {"adapter_name": self.adapter_name, "passed": self.passed,
                "input_valid": self.input_valid, "output_valid": self.output_valid,
                "transformation_correct": self.transformation_correct,
                "errors": self.errors, "timestamp": self.timestamp or utc_now().isoformat()}


def validate_adapter(adapter_fn: Callable, test_input: Dict[str, Any],
                     contract: InterfaceContract, expected_output: Optional[Dict[str, Any]] = None) -> AdapterValidationResult:
    """Validate an adapter function against its contract."""
    result = AdapterValidationResult(adapter_name=getattr(adapter_fn, "__name__", "unknown"), passed=True, timestamp=utc_now().isoformat())
    in_ok, in_errors = validate_against_contract(test_input, contract, "input")
    result.input_valid = in_ok
    if not in_ok:
        result.errors.extend(in_errors)
        result.passed = False
    try:
        output = adapter_fn(test_input)
    except Exception as exc:
        result.passed = False
        result.transformation_correct = False
        result.errors.append(f"Adapter raised: {exc}")
        return result
    if not isinstance(output, dict):
        result.passed = False
        result.errors.append("Adapter must return dict")
        return result
    out_ok, out_errors = validate_against_contract(output, contract, "output")
    result.output_valid = out_ok
    if not out_ok:
        result.errors.extend(out_errors)
        result.passed = False
    if expected_output:
        for key, expected_val in expected_output.items():
            if output.get(key) != expected_val:
                result.errors.append(f"Output mismatch on '{key}': expected {expected_val}, got {output.get(key)}")
                result.transformation_correct = False
                result.passed = False
    return result


@dataclass
class RoutingState:
    """Enforced routing state for bridge traffic."""
    mode: str = "mirror"
    canary_percent: int = 0
    legacy_active: bool = True
    new_active: bool = False
    locked: bool = False
    locked_reason: str = ""

    def to_dict(self) -> dict:
        return {"mode": self.mode, "canary_percent": self.canary_percent,
                "legacy_active": self.legacy_active, "new_active": self.new_active,
                "locked": self.locked, "locked_reason": self.locked_reason}


class RoutingEnforcer:
    """Enforces routing rules for bridge traffic."""

    def __init__(self) -> None:
        self._state = RoutingState()
        self._log: List[Dict[str, Any]] = []

    @property
    def state(self) -> RoutingState:
        return self._state

    def set_mode(self, mode: str, canary_percent: int = 0, health_check_fn: Optional[Callable] = None,
                 health_threshold: float = 70.0) -> Tuple[bool, str]:
        if self._state.locked:
            return False, f"Routing locked: {self._state.locked_reason}"
        if health_check_fn:
            score = health_check_fn()
            if score < health_threshold:
                return False, f"Health {score} below threshold {health_threshold}"
        old_mode = self._state.mode
        self._state.mode = mode
        self._state.canary_percent = canary_percent
        if mode == "mirror":
            self._state.legacy_active = True
            self._state.new_active = True
        elif mode == "canary":
            self._state.legacy_active = True
            self._state.new_active = True
        elif mode == "cutover":
            self._state.legacy_active = False
            self._state.new_active = True
        self._log.append({"event": "mode_change", "from": old_mode, "to": mode,
                          "canary_percent": canary_percent, "timestamp": utc_now().isoformat()})
        return True, ""

    def lock(self, reason: str = "") -> None:
        self._state.locked = True
        self._state.locked_reason = reason
        self._log.append({"event": "lock", "reason": reason, "timestamp": utc_now().isoformat()})

    def unlock(self) -> None:
        self._state.locked = False
        self._state.locked_reason = ""
        self._log.append({"event": "unlock", "timestamp": utc_now().isoformat()})

    def emergency_revert_to_legacy(self, reason: str = "emergency") -> None:
        self._state.mode = "legacy_only"
        self._state.legacy_active = True
        self._state.new_active = False
        self._state.canary_percent = 0
        self._log.append({"event": "emergency_revert", "reason": reason, "timestamp": utc_now().isoformat()})

    def get_log(self) -> List[Dict[str, Any]]:
        return list(self._log)


@dataclass
class CompatTestCase:
    """A test case for legacy-adapter-new compatibility."""
    name: str
    input_data: Dict[str, Any]
    expected_output: Optional[Dict[str, Any]] = None
    description: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "input_data": self.input_data,
                "expected_output": self.expected_output, "description": self.description}


@dataclass
class CompatTestResult:
    """Result of running a compatibility test suite."""
    passed: int = 0
    failed: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    details: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "failed": self.failed, "errors": self.errors, "details": self.details}


def run_compat_tests(adapter_fn: Callable, contract: InterfaceContract,
                     test_cases: List[CompatTestCase]) -> CompatTestResult:
    """Run compatibility test suite against an adapter."""
    result = CompatTestResult()
    for tc in test_cases:
        vr = validate_adapter(adapter_fn, tc.input_data, contract, expected_output=tc.expected_output)
        detail = {"test": tc.name, "passed": vr.passed, "errors": vr.errors}
        result.details.append(detail)
        if vr.passed:
            result.passed += 1
        else:
            result.failed += 1
            result.errors.append({"test": tc.name, "errors": vr.errors})
    return result
