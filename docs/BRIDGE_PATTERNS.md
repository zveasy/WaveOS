# WaveOS Bridge Patterns

## Overview

The bridge layer enables deployment of new systems alongside legacy systems without requiring rewrites. It is a first-class feature in the bundle manifest.

## Patterns

### 1. Adapter/Facade

An adapter process mediates between legacy and new system APIs.

```
[Legacy System] ←→ [Adapter/Facade] ←→ [New WaveOS Module]
```

### 2. Protocol/File Translation

Translate protocols or file formats between systems in real-time.

### 3. Mirror → Canary → Cutover

Three-phase rollout with validation at each step:

1. **Mirror**: Both systems run; new mirrors legacy output
2. **Canary**: Partial traffic routed to new system
3. **Cutover**: Full traffic to new system (legacy stopped)

## Manifest Fields

```json
{
  "bridge": {
    "mode": "mirror",
    "legacy_service": "legacy-api",
    "adapter_service": "bridge-adapter",
    "routing_rules": {"split_percent": 10},
    "validation_checks": ["response_match", "latency_ok"]
  }
}
```

## Orchestration Sequence

The bridge orchestrator guarantees safe startup order:

1. Start legacy service
2. Start adapter service
3. Start new module
4. Run validation/health gates
5. Apply routing switch (only after health gates pass)

## CLI

Bridge configuration is part of the bundle manifest and executed during `waveos agent-v2 activate`.
