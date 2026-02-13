# Dynamic Fixes and Cross-Version (VxWorks / Any Application)

## 1. Can WaveOS dynamically fix those issues?

**Today: advisory by default.** The pipeline recommends actions (REROUTE, RATE_LIMIT, POWER_THERMAL_CONSTRAINT), but the **default actuator only logs** them; it does not talk to your network or hardware, so nothing is “fixed” automatically.

**Ways to see or use it:**

| Mode | What happens |
|------|----------------|
| **Default** | `MockActuator` logs each action; you see them in the terminal and in the report. No real reroute or thermal change. |
| **Enforce + log** | Set `WAVEOS_ENFORCE_ACTIONS=true` (or in config). The same actions are still applied via the mock, but the run also writes **`out/enforced_actions.jsonl`** (and an event) so you can see “what would have been enforced.” |
| **Real fix** | With **`enforce_actions=true`** the pipeline uses the built-in **`SdnThermalActuator`**: it writes REROUTE to `actuator/reroute_requests.jsonl`, POWER_THERMAL_CONSTRAINT to `thermal_requests.jsonl`, and RATE_LIMIT / QOS to their request files. Your SDN or device API can consume these files (or use optional `WAVEOS_ACTUATOR_SDN_URL` / `WAVEOS_ACTUATOR_THERMAL_CMD`). See [ACTUATOR_INTEGRATION_KIT.md](ACTUATOR_INTEGRATION_KIT.md). |

**See “enforced” actions on your run:**

```bash
export WAVEOS_ENFORCE_ACTIONS=true
export WAVEOS_LICENSE_SKIP=1
waveos run --in ./demo_data/run --baseline ./demo_data/baseline --out ./out
cat ./out/enforced_actions.jsonl
# or, if idempotent run created a subdir:
cat ./out/run-*/enforced_actions.jsonl
```

So: **dynamic fix in code** = real actuator + `enforce_actions`. **See that the pipeline “would” enforce** = use `enforce_actions` and check `enforced_actions.jsonl`.

---

## 2. VxWorks versioning / cross-version for any application — how to see it work

WaveOS doesn’t run **on** VxWorks; it has a **compatibility layer** that accepts telemetry in **different shapes** (e.g. different field names or formats from VxWorks 6 vs 7, Linux, or vendor protocols) and **translates** them into one canonical schema. So “cross-version” means: different runtimes or applications can send different JSON; WaveOS normalizes them so the rest of the pipeline (scoring, policy) sees a single format.

**How to see it:**

- **Run the unit test** (translator + cross-version behavior):
  ```bash
  pytest tests/test_v3.py::test_runtime_translator -v
  ```
- **Run the cross-version demo script** (different “runtime” payloads → same normalized output):
  ```bash
  python scripts/demo_cross_version_translation.py
  ```

The demo script feeds two “applications” with different field names (e.g. `ts` vs `timestamp`, `link` vs `entity_id`, `temp_c` vs `temperature_c`, `soc_pct` vs `battery_soc_pct`) and shows they both become the same `TelemetrySample` shape. That’s how you see “VxWorks versioning or cross-version for any application” working: same pipeline, different input shapes, one normalized model.

**In your own app:** Send telemetry (from any runtime) as JSON with one of the supported field names; the pipeline’s normalization (and, if you use it, `RuntimeTranslator` / `translate_telemetry`) will map it to the canonical schema so scoring and policy work regardless of version or vendor.
