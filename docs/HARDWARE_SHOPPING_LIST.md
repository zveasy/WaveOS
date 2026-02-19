# WaveOS Hardware Shopping List (3 Tiers)

This list is optimized to **prove WaveOS** (and optionally Harmony Bridge) in a **real demo**: sense → decide → enforce → verify. It avoids buying full BESS, utility inverters, or real EV chargers until the control loop is validated on a smaller testbed.

**Reference:** [HARDWARE_INTEGRATION_KIT.md](HARDWARE_INTEGRATION_KIT.md) — protocols, ports, collectors, actuators, supervisor, fleet.

---

## Tier 1: ~$2k — Minimal closed-loop demo

**Goal:** One Edge Node, one real actuator path (e.g. SDN or load), one telemetry source. Prove the pipeline end-to-end on real hardware.

| Item | Purpose | Example / notes | Est. $ |
|------|---------|------------------|--------|
| **Edge compute** | Run WaveOS + supervisor | Raspberry Pi 4 (4–8 GB) or used Intel NUC; Ethernet, USB. | 100–250 |
| **SD card / SSD** | OS + WaveOS + evidence | 32–64 GB. | 20–50 |
| **SDN-capable switch** | Real REROUTE action | Used managed switch with OpenFlow or API (e.g. used HP/Aruba, or Open vSwitch on a second Pi). | 50–150 |
| **Smart plug or energy meter** | Telemetry (power, optional voltage) | TP-Link Kasa / Shelly / similar with local API or Modbus; or one Modbus energy meter. | 30–80 |
| **Programmable DC load or relay** | Thermal/power actuator | Small DC electronic load (e.g. 30–100 W) or 1‑channel relay module (5–20). | 30–80 |
| **DC power supply (bench)** | Testbed power source | 0–30 V, 0–5 A (or similar). | 80–150 |
| **Cables, enclosure, misc** | Wiring, case, cooling | Ethernet, USB‑serial if needed, small enclosure. | 50–100 |
| **Optional: USB‑RS485 adapter** | Modbus RTU later | One adapter for future meter/inverter. | 15–30 |

**Total (approx.):** **$400–900** for bare minimum; **~$1.5–2k** with a bit of headroom and a nicer NUC/switch.

**What you can prove:** WaveOS runs on the edge device; telemetry comes from a real meter or smart plug (adapter required); one action type (e.g. REROUTE or thermal) drives real hardware; evidence pack and report are generated. No TPM, no fleet.

---

## Tier 2: ~$10k — Solid testbed + resilience + one real protocol

**Goal:** Rugged Edge Node (optionally TPM), real Modbus or OCPP telemetry, SDN + load/relay actuators, microgrid-style testbed, supervisor and reset-reason story.

| Item | Purpose | Example / notes | Est. $ |
|------|---------|------------------|--------|
| **Edge gateway (industrial / NUC)** | WaveOS + supervisor; optional TPM | Industrial fanless PC (e.g. 4–8 GB RAM, x86) or Intel NUC with TPM 2.0; 2+ Ethernet, serial/RS‑485. | 400–800 |
| **Storage** | OS + WaveOS + audit + evidence | 128 GB SSD (or eMMC on gateway). | 40–80 |
| **SDN switch** | Real REROUTE | Managed switch with OpenFlow or REST API (e.g. used Cisco 2960, Aruba, or small Netgear managed). | 150–400 |
| **Modbus TCP or RTU meter** | Real power/energy telemetry | Single- or three-phase Modbus meter (Ethernet or RS‑485). | 150–400 |
| **USB‑RS485 adapter** | Modbus RTU | Industrial-grade adapter. | 25–50 |
| **Programmable DC load** | Thermal/power actuator | 100–300 W DC load with setpoint (e.g. BK Precision, Array). | 200–500 |
| **Relay module or GPIO board** | On/off actuator | 4–8 channel relay (e.g. industrial DIN); or Raspberry Pi / Arduino + relays. | 30–100 |
| **DC power supply** | Testbed source | 0–60 V, 0–10 A (or dual output). | 150–300 |
| **Battery module (small)** | Simulated storage | 12–24 V LiFePO4 or lead‑acid (e.g. 20–50 Ah) for “source + storage” demo. | 100–250 |
| **Enclosure, wiring, cooling** | Lab safety, cable management | Small cabinet or bench enclosure, breakers, fuses. | 150–300 |
| **Optional: TPM 2.0 gateway** | DoD key story | Same as edge gateway but with TPM and secure boot. | +100–200 |
| **Optional: second edge node** | Fleet / canary test | Second NUC or Pi for “two nodes, one bundle rollout.” | 150–400 |

**Total (approx.):** **$1.6–3.5k** without battery/second node; **~$6–10k** with battery, second node, and TPM-capable gateway.

**What you can prove:** WaveOS on an industrial-style node; **real Modbus telemetry** (you must implement the Modbus→schema adapter); REROUTE on a real switch; thermal/power/relay actions on load and relays; microgrid-style loop (source + battery + load + meter); supervisor with watchdog and reset reason; optional TPM and two-node fleet test.

---

## Tier 3: ~$50k — Demo-ready + multi-node + “near production”

**Goal:** Multiple rugged Edge Nodes, redundant or multi-site feel, real inverter or charger simulator (or small real hardware), BESS simulator or small BESS, fleet tooling, DoD-grade key and resilience.

| Item | Purpose | Example / notes | Est. $ |
|------|---------|------------------|--------|
| **2–3 rugged Edge gateways (TPM)** | Multi-node, canary, failover | Industrial PCs with TPM 2.0, secure boot, 8 GB RAM, RS‑485 + Ethernet. | 2–4k |
| **Storage per node** | Evidence, audit, bundles | 256 GB SSD per node. | 50–80 × nodes |
| **SDN switch(es)** | Production-like reroute | 1–2 managed switches (e.g. 24‑port) with OpenFlow or API. | 500–1.5k |
| **Modbus meters (2–3)** | Multi-point telemetry | 2–3 Modbus TCP/RTU meters (grid, load, DER). | 500–1.2k |
| **Small inverter or inverter sim** | “DER” in the loop | Small hybrid inverter (e.g. 3–6 kW) or inverter test rig / sim. | 1–3k |
| **EV charger (AC Level 2) or sim** | OCPP / charger telemetry | One AC charger (e.g. 7 kW) with OCPP or API, or hardware-in-the-loop sim. | 0.5–2k |
| **BESS simulator or small rack** | Storage in the loop | Simulator (e.g. software + Modbus) or small 2–5 kWh rack. | 1–5k |
| **Programmable loads + relays** | Multiple actuator paths | 2+ DC loads, relay panel (8–16 channels). | 500–1.5k |
| **DC bus + breakers** | Safe testbed | 48 V or 400 V DC bus, breakers, fuses, enclosure. | 1–3k |
| **Fleet / inventory tooling** | Distribution, versions, canary | Server or SaaS for bundle distribution + simple node registry (build or buy). | 0–2k (DIY) / 2–10k (vendor) |
| **Spare parts, cables, labor** | Integration, wiring, software | Allow 20–30% for integration and unknowns. | 3–8k |

**Total (approx.):** **$12–25k** for “serious testbed” without full BESS/charger; **~$35–50k** with inverter, charger or sim, BESS sim or small BESS, and fleet tooling.

**What you can prove:** Multi-node WaveOS; real OCPP or Modbus (and optional CAN) telemetry; REROUTE + thermal + rate-limit on real hardware; microgrid with inverter and storage; fleet rollout (canary, version tracking); TPM and secure boot; evidence and audit suitable for DoD/utility demos.

---

## What NOT to buy yet (save money)

Avoid until the control loop is proven on Tier 1–2:

- **Full BESS container or utility-scale battery** — $50k–$500k+; use simulator or small rack first.
- **Utility-scale or large hybrid inverter** — $10k–$100k+; use small inverter or sim.
- **Real DC fast chargers (DCFC)** — $50k–$150k+; use AC Level 2 or sim first.
- **Redundant grid tie and switchgear** — prove software and one site first.

---

## Suggested path

1. **Start with Tier 1** — One edge device, one meter or smart plug, one actuator (switch or load). Build the **telemetry adapter** (e.g. smart plug → JSONL) and **one actuator driver** (e.g. script that reads `reroute_requests.jsonl` and calls switch API). Prove sense → decide → enforce → verify.
2. **Move to Tier 2** — Add Modbus meter, programmable load, relay, supervisor (systemd + watchdog + reset reason). Optionally TPM gateway and second node for canary.
3. **Scale to Tier 3** — When you need to show multi-node, inverter, charger, or BESS in the loop, add hardware and fleet tooling per the table.

Use [HARDWARE_INTEGRATION_KIT.md](HARDWARE_INTEGRATION_KIT.md) as the product manual for protocols, ports, and integration steps at each tier.
