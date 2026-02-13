"""V3: GitOps for hardware — desired state, diff, apply, state history."""

from waveos.gitops.state import (
    DesiredState,
    apply_desired_state,
    current_state_from_registry,
    diff_state,
    load_desired_state,
    save_state_history,
)

__all__ = [
    "DesiredState",
    "apply_desired_state",
    "load_desired_state",
    "current_state_from_registry",
    "diff_state",
    "save_state_history",
]
