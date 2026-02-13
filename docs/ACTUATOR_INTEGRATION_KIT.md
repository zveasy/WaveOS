# Actuator Integration Kit

How to implement a **real** actuator so WaveOS can control hardware (chargers, inverters, relays) instead of only logging recommendations.

## Built-in real actuator (SDN + thermal)

When **`enforce_actions=true`**, the pipeline uses **`SdnThermalActuator`** instead of the mock. It:

- Writes **REROUTE** requests to `<actuator_dir>/reroute_requests.jsonl` (for your SDN controller)
- Writes **POWER_THERMAL_CONSTRAINT** to `thermal_requests.jsonl` (only if the policy recommended thermal actions)
- Writes **RATE_LIMIT** to `rate_limit_requests.jsonl`, **QOS_PRIORITIZATION** to `qos_requests.jsonl`
- Also writes **`enforced_actions.jsonl`** in the **output root** (e.g. `./out/enforced_actions.jsonl`) for inspection

Each `*_requests.jsonl` file is created only when there is at least one action of that type; e.g. `thermal_requests.jsonl` is missing if no POWER_THERMAL_CONSTRAINT was recommended.

Each line is JSON: `timestamp`, `run_id`, `entity_type`, `entity_id`, `action`, `rationale`, `parameters`. Your SDN or device API can tail these files or poll them.

**Optional hooks (env):**

- **`WAVEOS_ACTUATOR_SDN_URL`** — POST each REROUTE request to this URL (JSON body).
- **`WAVEOS_ACTUATOR_THERMAL_CMD`** — Run this command for each POWER_THERMAL_CONSTRAINT; record is passed as JSON on stdin.

**Config:** `actuator_output_dir` (or env `WAVEOS_ACTUATOR_OUTPUT_DIR`) — where the `*_requests.jsonl` files go. Default: `<run out>/actuator`.

**Try it:** (run each command separately; do not paste comments as shell commands)
```bash
export WAVEOS_LICENSE_SKIP=1
export WAVEOS_ENFORCE_ACTIONS=true
waveos run --in ./demo_data/run --baseline ./demo_data/baseline --out ./out
cat ./out/actuator/reroute_requests.jsonl
cat ./out/actuator/rate_limit_requests.jsonl
cat ./out/enforced_actions.jsonl
```
`enforced_actions.jsonl` is always under the output root (`./out/`), not inside `./out/run-*/`. `thermal_requests.jsonl` appears only when the run recommended POWER_THERMAL_CONSTRAINT actions.

## Base class

Use `waveos.actuators.RealActuator`:

```python
from waveos.actuators import RealActuator
from waveos.models import ActionRecommendation

class MyChargerActuator(RealActuator):
    def __init__(self):
        super().__init__(name="charger-vendor-x")

    def validate(self, action: ActionRecommendation) -> bool:
        # Safety envelope: e.g. reject power above limit
        if action.action == "POWER_THERMAL_CONSTRAINT":
            return True
        return False  # only allow certain action types

    def apply(self, actions):
        for a in actions:
            # Call vendor API or protocol (Modbus, REST, etc.)
            self._send_command(a.entity_id, a.action, a.details)
```

## Integration steps

1. **Subclass `RealActuator`** and implement `apply(actions)`.
2. **Override `validate(action)`** to enforce safety (max power, allowed action types, cooldowns).
3. **Use `apply_safe(actions)`** in your pipeline so only validated actions are executed.
4. **Wire your actuator in the pipeline** by replacing `MockActuator()` where the CLI or runner builds the pipeline (e.g. config-driven actuator class or plugin).
5. **Set `enforce_actions=true`** only when the real actuator is configured and tested.

## Safety

- Keep **fail-safe defaults**: e.g. loss of connection should not assume “last command succeeded.”
- **Validate every action** (rate, magnitude, type) before sending to hardware.
- Use the **watchdog** and **recovery** hooks so a stuck process can be reset by the device supervisor.
- Log actions to the **audit log** for compliance.

## Example: config-driven actuator

In config or env, set the actuator class (e.g. via plugin or entry point):

```toml
# config
enforce_actions = true
actuator_class = "my_package.waveos_actuator:ChargerActuator"
```

The CLI uses **`SdnThermalActuator`** when `enforce_actions=true` and **`MockActuator`** otherwise. To use a custom actuator class instead, extend the CLI or add a plugin to instantiate it when `enforce_actions=true`.

## See also

- [PRD / capability matrix](PRD_DOD_REQUIREMENTS.md) — hardware abstraction and device API
- [Deployment Readiness](DEPLOYMENT_READINESS_REPORT.md) — safety integration requirements
