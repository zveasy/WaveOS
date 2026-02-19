# WaveOS Hardware Integration Kit

WaveOS is production-ready **as a software control-plane**. To make it real in the physical world (microgrid, chargers, DoD embedded systems), you need **hardware integration + live data ingestion + real actuator execution + a test environment**. This document is the **product manual** for that: what you must build, what to buy, and how it all connects.

---

## What’s Missing Before Hardware Purchase Matters

| Gap | Today | What you need |
|-----|--------|----------------|
| **Edge node** | WaveOS runs on your laptop | A real device on-site: industrial PC / NUC / Jetson that runs the pipeline, stores evidence, survives reboots. |
| **Telemetry** | Sim data + file-based ingest only | **Telemetry collector/adapter layer** that pulls from chargers (OCPP), inverters, BESS, meters (Modbus), thermal sensors, SDN. |
| **Actuators** | JSONL files + optional HTTP/command hooks | **Physical execution**: SDN switch (real reroute), thermal/power controller, relays so actions change real behavior. |
| **Testbed** | Demo data only | A **physical microgrid testbed** (even minimal): DC source, load, meter, sensor so you can show sense → decide → enforce → verify. |
| **Keys & resilience** | Fernet/HMAC, watchdog file | **TPM-backed secrets**, **WaveOS Supervisor** (systemd, reset reason, health-check, auto-restart). |
| **Fleet** | Single-node bundle install | **Fleet model**: bundle distribution to many sites, version tracking, canary rollout, node inventory. |

Without the items in the “What you need” column, buying hardware won’t prove WaveOS in the real world. The sections below specify each piece.

---

## 1. WaveOS Edge Node (core hardware target)

The **Edge Node** is the device where WaveOS runs in the field. It must:

- **Collect telemetry** (via adapters; see §2) or receive forwarded data from collectors.
- **Run `waveos run`** locally (or forward data to a central node that runs it).
- **Push actuator actions** out to switches, controllers, relays (§3).
- **Store encrypted artifacts and evidence packs** (config: `encrypt_artifacts`, `WAVEOS_ENCRYPTION_KEY`).
- **Survive reboots and loss of network** (supervisor §6, offline bundle cache, watchdog).

### Typical hardware

- **Industrial PC (fanless)** — e.g. 4–8 GB RAM, x86 or ARM, Ethernet, serial/RS-485 expansion.
- **Rugged mini server / NUC-style** — same; often with TPM 2.0 for DoD.
- **Jetson / embedded SBC** — for lower power or edge AI later; ensure enough RAM and storage for WaveOS + evidence.

### Requirements summary

| Requirement | Notes |
|-------------|--------|
| OS | Linux (systemd for supervisor). |
| Storage | Enough for WaveOS, config, audit log, evidence packs, bundle cache (e.g. 16 GB+ free). |
| Network | Ethernet (and optionally Wi‑Fi / LTE for backhaul or management). |
| Optional | TPM 2.0 (key storage), secure boot (DoD path). |
| Ports for collectors/actuators | See §2 and §3; often RS-485, Ethernet, sometimes CAN, GPIO. |

See [HARDWARE_SHOPPING_LIST.md](HARDWARE_SHOPPING_LIST.md) for tiered purchase options.

---

## 2. Telemetry collectors (ingestion gap)

**Current state:** WaveOS has **file-based ingestion** (JSON/JSONL/CSV via `load_records`). Sim data and config-driven mTLS exist; there is **no built-in collector that talks to real devices**.

### What you need: WaveOS Telemetry Collector / Adapter Layer

A software layer that:

- **Pulls or receives** data from:
  - EV chargers (OCPP or vendor REST/API)
  - Inverters (Modbus, vendor API)
  - BESS controllers (Modbus, CAN, vendor API)
  - Meters (Modbus TCP/RTU)
  - Thermal sensors (Modbus, 1-Wire, vendor API)
  - SDN switches (SNMP, REST)
  - Compute nodes (existing APIs or agents)
- **Normalizes** payloads into the [WaveOS telemetry schema](TELEMETRY_SCHEMA.md) (e.g. `link_id`, `power_kw`, `voltage_v`, `current_a`, `temperature_c`, `charger_status`, etc.).
- **Outputs** JSON/JSONL (or pushes to a path/directory) that `waveos run --in <dir>` consumes, or streams into a run pipeline.

This is where hardware matters: you need **ports and buses** the adapter can use.

### Supported / planned protocols

| Protocol | Typical use | Port / bus | Status in WaveOS |
|----------|-------------|-------------|-------------------|
| **Modbus TCP** | Meters, inverters, BESS, thermal | Ethernet | Adapter to build; schema mapping defined. |
| **Modbus RTU** | Same over serial | RS-485 / serial | Adapter to build. |
| **OCPP (1.6 / 2.0)** | EV chargers | Ethernet (HTTP/WebSocket) | Adapter to build; map to `charger_status`, `power_kw`, etc. |
| **REST / JSON** | Vendor APIs, cloud gateways | Ethernet | File ingest today; HTTP pull adapter to build. |
| **SNMP** | Switches, PDUs, some meters | Ethernet | Adapter to build. |
| **CAN** | BESS, vehicle, some chargers | CAN bus | Adapter to build; hardware with CAN interface. |

### Required ports on the Edge Node (for collectors)

| Port / bus | Purpose |
|------------|--------|
| **Ethernet** | Modbus TCP, OCPP, REST, SNMP, management, optional backhaul. |
| **RS-485** | Modbus RTU meters, inverters, legacy devices. |
| **Serial (UART)** | Console, some sensors, custom protocols. |
| **CAN** (optional) | BESS, automotive-style chargers. |
| **GPIO** (optional) | Local digital I/O, alarms, simple interlocks. |

### Adapter contract (for implementers)

- **Input:** Device- or protocol-specific API (e.g. Modbus read, OCPP status, REST GET).
- **Output:** Records that match [TELEMETRY_SCHEMA.md](TELEMETRY_SCHEMA.md) (e.g. one record per link/device/sample with `timestamp`, `link_id`, and normalized fields). Write to a directory as JSONL or stream to the run pipeline.
- **Config:** Per-device or per-protocol config (IP, port, register maps, OCPP station ID, etc.); keep secrets out of repo (env or vault).
- **Resilience:** Retries, circuit breaker, and backpressure so a bad device doesn’t stall the pipeline.

If you don’t build this layer, buying hardware won’t give WaveOS real telemetry.

**Built-in HTTP pull:** WaveOS includes **`load_records_from_url()`** and supports **`--in http(s)://...`** on `waveos run`. So a gateway or adapter that exposes telemetry as JSON/JSONL at a URL can feed the pipeline without writing files. Use this for a quick live-data path while you add Modbus/OCPP adapters.

---

## 3. Real actuators (beyond JSONL files)

The built-in **SdnThermalActuator** writes:

- `reroute_requests.jsonl`
- `thermal_requests.jsonl`
- `rate_limit_requests.jsonl`
- `qos_requests.jsonl`

and optionally calls `WAVEOS_ACTUATOR_SDN_URL` (POST) or `WAVEOS_ACTUATOR_THERMAL_CMD` (stdin JSON). That is the **brain**. The **body** is hardware that turns those requests into physical behavior.

### Actuator → physical mapping

| WaveOS action | File / hook | Physical target | What to buy / integrate |
|---------------|-------------|-----------------|--------------------------|
| **REROUTE** | `reroute_requests.jsonl`, optional POST | SDN controller / switch | **SDN-capable switch** (OpenFlow or vendor API); controller that applies flow rules. |
| **POWER_THERMAL_CONSTRAINT** | `thermal_requests.jsonl`, optional cmd | Thermal/power controller | **Programmable load**, **relay box**, or **power controller** that accepts setpoints or on/off. |
| **RATE_LIMIT** | `rate_limit_requests.jsonl` | Charger, inverter, or gateway | Device API (OCPP, Modbus write) or gateway that throttles; **charger/inverter with API** or **relay to disable circuit**. |
| **QOS_PRIORITIZATION** | `qos_requests.jsonl` | Network or load priority | SDN QoS or load scheduler; can combine with switch + controller. |

### Minimum hardware for “real” actuator demo

- **One SDN-capable switch** — so a REROUTE request actually changes forwarding (or a software SDN controller + switch that supports it).
- **One controllable load or relay** — so a thermal/power action actually changes power or turns something on/off (e.g. programmable DC load, relay module, smart plug with API).
- Optionally a **microcontroller (e.g. Arduino/ESP32 + relay)** so WaveOS (via `WAVEOS_ACTUATOR_THERMAL_CMD` script) can physically open/close a circuit.

That gives you a **closed loop**: sense → decide → enforce → verify. See [ACTUATOR_INTEGRATION_KIT.md](ACTUATOR_INTEGRATION_KIT.md) for implementing custom actuators (e.g. charger-specific).

**Actuator consumer (software):** Use **`scripts/actuator_listener.py`** to tail `*_requests.jsonl` in the actuator dir and POST each line to a URL (`WAVEOS_ACTUATOR_SDN_URL`) or run a command with JSON on stdin (`WAVEOS_ACTUATOR_THERMAL_CMD`). Run it as a daemon alongside WaveOS so requests are forwarded to your SDN or thermal controller.

---

## 4. Physical microgrid testbed (even if miniature)

You don’t need a full BESS or utility-scale inverter yet. You do need a **testbed** where:

- WaveOS **detects drift** (e.g. power or temperature vs baseline).
- WaveOS **recommends an action** (reroute, thermal, rate limit).
- The action is **enforced** (switch or load/relay changes).
- You **measure** that the system recovered (meter or sensor reading).
- WaveOS produces an **evidence pack** (run_meta, report, audit).

### Minimal testbed components

| Component | Role |
|-----------|------|
| **DC power source** | Bench supply or small solar sim. |
| **Battery module or simulated battery** | Or resistor/cap as load; enough to represent “source + storage.” |
| **Load** | Programmable DC load or fixed load switched by relay. |
| **Meter** | Modbus meter or smart plug so telemetry has real voltage/current/power. |
| **Thermal sensor** (optional) | So thermal policy and thermal actuator have real input. |

Scale can be small (e.g. 12–48 V DC, hundreds of watts). The goal is to **prove the loop** so that when you later add a real BESS or charger, WaveOS is already validated. See [HARDWARE_SHOPPING_LIST.md](HARDWARE_SHOPPING_LIST.md) for tiered options.

---

## 5. Secure key management (DoD-grade)

**Current state:** Fernet (`WAVEOS_ENCRYPTION_KEY`) and HMAC (bundle sign, report sign) from env or secrets provider. Fine for v1.

**Production / DoD:** You need:

- **TPM-backed secrets** (or HSM) so keys aren’t in plain env on disk.
- **Hardware key storage** where supported (e.g. Edge Node with TPM 2.0).
- **Rotation procedures** (see [SECRETS_ROTATION.md](SECRETS_ROTATION.md)); document “what happens if device is stolen.”

**Hardware:** Prefer an Edge Node with **TPM 2.0** and **secure boot** so the chain from boot to WaveOS is attested and keys can be bound to the device.

---

## 6. WaveOS Supervisor (systemd + reset reason + health-check)

WaveOS today provides:

- **Watchdog:** Writes a timestamp file each run (`watchdog_path`); see [RECOVERY_INTEGRATION_KIT.md](RECOVERY_INTEGRATION_KIT.md).
- **Recovery:** Can run restart/degrade/reboot commands with operator approval.

The **missing piece** is the **other side**: a **supervisor** that runs on the Edge Node and enforces resilience.

### Supervisor contract

| Responsibility | Description |
|----------------|-------------|
| **Run WaveOS** | Start `waveos run` (or your pipeline script) on a schedule or trigger; restart on exit. |
| **Watchdog monitor** | Check `watchdog_path`; if timestamp is older than threshold (e.g. 2× run interval), treat as unhealthy and restart or reboot. |
| **Reset reason** | On any restart/reboot, write reason (e.g. `watchdog_timeout`, `waveos_exit`, `manual`) to a well-known path (e.g. `/var/run/waveos-reset-reason`) for audit. |
| **Health-check endpoint** | Optional HTTP (e.g. `/health`) or script that runs `waveos health-check` for orchestrators. |
| **Safe boot** | On boot, ensure config and secrets are present before starting WaveOS; optionally verify bundle signature. |

### Example: systemd service

```ini
# /etc/systemd/system/waveos.service
[Unit]
Description=WaveOS control-plane run
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/waveos run --in /var/lib/waveos/input --baseline /var/lib/waveos/baseline --out /var/lib/waveos/out
Environment=WAVEOS_CONFIG=/etc/waveos/config.toml
EnvironmentFile=-/etc/waveos/secrets.env

[Install]
WantedBy=multi-user.target
```

Run this from a **timer** or a wrapper script that loops; the **supervisor** (separate service or script) should:

- Monitor the watchdog file.
- Restart the timer/service if the watchdog is stale.
- On restart, write reset reason to `/var/run/waveos-reset-reason`.

DoD/industrial systems must not depend on “someone manually restarting”; this supervisor layer is critical.

**Provided in repo:** **`scripts/waveos-watchdog-monitor.sh`** checks the watchdog file mtime and, if stale, writes reset reason and restarts the WaveOS service. Example systemd units: **`docs/systemd/`** (waveos.service, waveos.timer, waveos-watchdog.service, waveos-watchdog.timer). Copy and adjust paths and env.

---

## 7. Fleet update and deployment model

**Current state:** Bundle install works **locally** (`waveos bundle install --from-cache`, canary, rollback). Single-node.

**What you need for scale:** A **WaveOS Fleet Manager** (even minimal):

- **Bundle distribution** to many sites (e.g. from your DevSecOps pipeline or distribution server; see [DEVSECOPS_DELIVERY.md](DEVSECOPS_DELIVERY.md)).
- **Tracking** of which bundle/version is installed per node (e.g. state file on node + optional central inventory).
- **Canary rollout** across fleet (e.g. install to 10% of nodes, then promote; WaveOS already supports canary install per node).
- **Node inventory** (node ID, version, last run, health) so you can target updates and audits.

This can start as: “list of nodes + SSH or pull-based install script + state file per node,” and grow into a proper fleet API. Without it, you can’t prove multi-site or multi-node operation.

**Provided in repo:** **`scripts/fleet_deploy.py`** deploys a bundle to multiple hosts via SSH. Use `--hosts node1,node2` or `--nodes-file out/nodes.json` (uses `node_id` or `meta.ssh_host` as host) with `--cache` and `--bundle-id` (or `--bundle-dir`). Run it from your CI or release process to push a bundle to a list of edge nodes.

---

## 8. Edge install and offline run

- **Install WaveOS on the Edge Node:** Use the distribution zip from the DevSecOps pipeline; install via pip (or container) as in INSTALL.md. Configure `WAVEOS_CONFIG`, secrets (env or file), and paths for input/baseline/output.
- **Offline run:** Baseline and run input can be produced **on the node** by your telemetry adapters (writing JSONL into `--in` and `--baseline` dirs), or copied from elsewhere. For **air-gapped** updates, use the signed bundle zip and `waveos bundle install --from-cache <path> --bundle-id <id>`; set `WAVEOS_ENCRYPTION_KEY` if the bundle is encrypted. See [DEVSECOPS_DELIVERY.md](DEVSECOPS_DELIVERY.md) air-gap section.
- **Evidence packs:** Stored under the run output dir (e.g. `out/`). Optionally encrypt with `encrypt_artifacts=true`. Export by copying the output dir or uploading to a secure store (script or integration you add).

---

## 9. Summary: what to build before hardware spend pays off

| # | Deliverable | Purpose |
|---|-------------|--------|
| 1 | **Edge gateway runtime** | WaveOS + config + supervisor on a real device; watchdog + reset reason. |
| 2 | **Real telemetry collectors** | Adapters for Modbus, OCPP, SNMP, REST (as needed) → normalized schema → JSONL for `waveos run`. |
| 3 | **Real actuator drivers** | Code or scripts that consume `*_requests.jsonl` (or HTTP/cmd hooks) and drive SDN switch, load, relay. |
| 4 | **Microgrid testbed (minimal)** | DC source, load, meter, (optional) sensor so the closed loop is measurable. |
| 5 | **Supervisor + resilience** | systemd (or equivalent), watchdog monitor, reset reason, health-check. |
| 6 | **Fleet rollout model** | Distribution of bundles, version tracking, canary, inventory (even minimal). |

Once these are in place, hardware spend (Edge Node, switch, meter, load, TPM) turns WaveOS into something you can **demonstrate and sell** in the physical world. See [HARDWARE_SHOPPING_LIST.md](HARDWARE_SHOPPING_LIST.md) for a tiered shopping list ($2k / $10k / $50k) optimized for proving WaveOS (and optionally Harmony Bridge) in a real demo.
