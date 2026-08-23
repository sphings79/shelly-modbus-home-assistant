<div align="center">

<img src="assets/banner.svg" alt="Shelly Modbus for Home Assistant — local Modbus-TCP integration" width="100%">

# Shelly Modbus for Home Assistant

**Read Shelly energy meters and relays over local Modbus-TCP — no cloud, no polling the RPC API.**

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=flat-square)](https://hacs.xyz)
[![Validate](https://img.shields.io/github/actions/workflow/status/sphings79/shelly-modbus-home-assistant/validate.yml?branch=main&label=validate&style=flat-square)](https://github.com/sphings79/shelly-modbus-home-assistant/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-3DDC97.svg?style=flat-square)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.9%2B-41BDF5.svg?style=flat-square)](https://www.home-assistant.io)

**English** · [Deutsch](README.de.md)

</div>

---

## What this integration does

Shelly's Gen2, Gen3 and Gen4 energy meters ship with a **Modbus-TCP server** built into the
firmware. This custom integration for [Home Assistant](https://www.home-assistant.io) talks to
that server directly: it opens one TCP connection to port 502, reads the device's input
registers in batched blocks, and turns them into Home Assistant entities.

Everything stays on your network. No Shelly Cloud account, no MQTT broker, no HTTP/RPC polling.

### Why use Modbus instead of the built-in Shelly integration?

The official Shelly integration is excellent and most people should use it. Reach for Modbus when
you want:

| | Modbus-TCP (this integration) | Official Shelly integration |
|---|---|---|
| Transport | Raw TCP, one persistent socket | HTTP/RPC + WebSocket |
| Overhead per reading | A few bytes per register block | A JSON document per request |
| Cloud dependency | None | None (local push available) |
| Update rate | Freely configurable, down to 1 s | Device-driven |
| Interoperability | Same registers your inverter, PLC or Venus GX reads | Home Assistant only |
| Entity scope | Exactly the registers you enable | Everything the device offers |

The practical case: you already read the meter over Modbus from somewhere else (a hybrid
inverter, a Loxone or PLC setup, Victron Venus), and you want Home Assistant to see **the same
numbers from the same source**, at an interval you choose.

---

## Screens

> The images below are illustrations of the integration's dialogs, not photographs of a running
> instance.

<div align="center">
<img src="assets/setup.svg" alt="Home Assistant config flow: connect the Shelly device, then confirm the detected model" width="100%">
</div>

The device is identified automatically — the integration reads the model string straight out of
the device's own registers and preselects it. You can always override the choice.

<div align="center">
<img src="assets/options.svg" alt="Polling interval options, split into fast and slow value categories" width="66%">
</div>

<div align="center">
<img src="assets/entities.svg" alt="Entities created for a Shelly Pro 3EM" width="100%">
</div>

---

## Supported devices

Every Shelly device whose firmware exposes a Modbus server is covered. Enable it first — see
[Enabling Modbus](#1-enable-modbus-on-the-device).

### Energy meters

| Device | Model code | Generation | Status |
|---|---|---|---|
| Shelly Pro 3EM | `SPEM-003CEBEU` | Gen2 | ✅ **Verified on hardware** |
| Shelly Pro 3EM-3CT63 | `SPEM-003CEBEU63` | Gen2 | Register map shared with Pro 3EM |
| Shelly Pro 3EM-120 | `SPEM-003CEBEU120` | Gen2 | Register map shared with Pro 3EM |
| Shelly Pro 3EM-400 | `SPEM-003CEBEU400` | Gen2 | Register map shared with Pro 3EM |
| Shelly Pro EM 50 | `SPEM-002CEBEU50` | Gen2 | From documentation |
| Shelly 3EM-63 Gen3 | `S3EM-003CXCEU63` | Gen3 | ✅ **Verified on hardware** |
| Shelly EM Gen3 | `S3EM-002CXCEU` | Gen3 | From documentation |
| Shelly EM Mini Gen4 | `S4EM-001PXCEU16` | Gen4 | From documentation |
| Shelly EM 63 Gen4 | `S4EM-001CXCEU63` | Gen4 | From documentation |

### Switches and relays

| Device | Model code | Metering | Status |
|---|---|---|---|
| Shelly 1 Gen4 | `S4SW-001X16EU` | — | From documentation |
| Shelly 1 Mini Gen4 | `S4SW-001X8EU` | — | From documentation |
| Shelly 1L Gen4 | `S4SW-0A1X1EUL` | — | From documentation |
| Shelly 1PM Gen4 | `S4SW-001P16EU` | ✅ | From documentation |
| Shelly 1PM Mini Gen4 | `S4SW-001P8EU` | ✅ | From documentation |
| Shelly 2PM Gen4 | `S4SW-002P16EU` | ✅ | From documentation |
| Shelly 2L Gen4 | `S4SW-0A2X4EUL` | — | From documentation |

**"Verified on hardware"** means every register was read from a physical device and each decoded
value was compared against the same device's own RPC output — see [Verification](#verification).
The other entries follow Shelly's published register maps and the same component layout, but
have not been confirmed on real hardware. Reports welcome via
[issues](https://github.com/sphings79/shelly-modbus-home-assistant/issues).

> **Not supported:** Shelly Plus/Pro devices without a Modbus server (Plus 1PM, Plus Plug S,
> Pro 4PM, …) and all Gen1 devices. They have no Modbus server in firmware — use the official
> Shelly integration for those.

### Measuring profiles

The three-phase meters can run as **one three-phase meter** (`triphase`) or as **three
independent single-phase meters** (`monophase`). This changes which Modbus components exist, so
the integration probes the device to find out which profile is active, and lets you override it.

---

## Installation

### Option A — HACS (recommended)

1. Open **HACS** in Home Assistant.
2. Click the three-dot menu → **Custom repositories**.
3. Add `https://github.com/sphings79/shelly-modbus-home-assistant` with category **Integration**.
4. Search for **Shelly Modbus**, install it.
5. Restart Home Assistant.

### Option B — manual

1. Download the latest release.
2. Copy `custom_components/shelly_modbus` into your Home Assistant `config/custom_components/`
   directory. The result should be `config/custom_components/shelly_modbus/manifest.json`.
3. Restart Home Assistant.

---

## Setup

### 1. Enable Modbus on the device

Modbus is **off by default** on every Shelly device.

- **Web interface:** open the device's IP in a browser → **Settings** → **Modbus** → enable.
- **Or over RPC:**

  ```bash
  curl -X POST -d '{"id":1,"method":"Modbus.SetConfig","params":{"config":{"enable":true}}}' \
    http://<device-ip>/rpc
  ```

Verify it took effect:

```bash
curl -s http://<device-ip>/rpc/Modbus.GetConfig
```

This should print `{"enable":true}`.

### 2. Add the integration

Go to **Settings → Devices & Services → Add Integration** and search for **Shelly Modbus**.
Devices announcing themselves over mDNS are discovered automatically.

Enter the host, then confirm the detected model and profile.

| Field | Meaning | Default |
|---|---|---|
| Host or IP address | The device's address. A static IP or DHCP reservation is strongly recommended. | — |
| Port | Modbus-TCP port. Shelly always uses 502. | `502` |
| Modbus unit ID | Shelly ignores this; change it only behind a gateway. | `1` |
| Model | Auto-detected from the device's registers, overridable. | detected |
| Measuring profile | `triphase` or `monophase` for three-phase meters. | detected |

### 3. Tune the polling intervals

**Settings → Devices & Services → Shelly Modbus → Configure**

Registers are grouped into two categories, each polled on its own interval:

| Category | Default | Range | Contains |
|---|---|---|---|
| **Fast values** | **5 s** | 1–3600 s | Active/apparent power, voltage, current, power factor, relay output states |
| **Slow values** | **60 s** | 5–86400 s | Energy counters, frequency, error and diagnostic flags |
| Device identity | read once | — | MAC, model, device name |

**Why 5 seconds.** A fast cycle is three Modbus block reads and completes in 70–100 ms on a
Pro 3EM, so the default keeps the device at roughly 2% utilisation. There is plenty of head
room: at 3 s it is about 3%, at 1 s about 10%. If you drive an export limiter or a battery
controller from these values, going down to 1–2 s is fine. Raise it instead if the device is
on weak Wi-Fi or several Modbus clients share it.

Device identity is read once at startup and never polled again.

> **Tip:** disabling entities you do not need genuinely reduces Modbus traffic — the coordinator
> only reads registers that back an enabled entity.

---

## Entities

Entity names are provided in **English and German** and follow your Home Assistant language
setting.

### Three-phase meter (`triphase`)

| Entity | Unit | Device class | Enabled by default |
|---|---|---|---|
| Total Active Power | W | power | ✅ |
| Total Current | A | current | ✅ |
| Total Apparent Power | VA | apparent_power | — |
| Phase A/B/C Voltage | V | voltage | ✅ |
| Phase A/B/C Current | A | current | ✅ |
| Phase A/B/C Active Power | W | power | ✅ |
| Phase A/B/C Apparent Power | VA | apparent_power | — |
| Phase A/B/C Power Factor | — | power_factor | — |
| Phase A/B/C Frequency | Hz | frequency | — |
| Neutral Current | A | current | — |
| Total Active Energy | kWh | energy | ✅ |
| Total Active Returned Energy | kWh | energy | ✅ |
| Grid Import Power (netted) | W | power | ✅ |
| Grid Export Power (netted) | W | power | ✅ |
| Grid Import Energy (netted) | kWh | energy | ✅ |
| Grid Export Energy (netted) | kWh | energy | ✅ |
| Phase A/B/C Active Energy | kWh | energy | ✅ |
| Phase A/B/C Active Returned Energy | kWh | energy | ✅ |
| Meter / overvoltage / overcurrent / overpower errors | — | problem | — |
| Modbus Connection | — | connectivity | ✅ |

### Single-phase channel (`monophase`, Pro EM, EM Gen3/Gen4)

Voltage, Current, Active Power, Apparent Power, Power Factor, Frequency, Active Energy, Active
Returned Energy and the error flags — one set per channel, named `Channel 1`, `Channel 2`, …

### Switches

Output (writable), plus Voltage, Current, Active Power, Frequency, Power Factor, Active Energy
and error flags on models with a power meter. Physical inputs appear as binary sensors.

### Netted grid power — read this before using the energy dashboard

Shelly's energy counters are **not netted across phases**. Each phase accumulates its own
import and export counter, and the device only adds those up. On a German-style
bidirectional meter that nets across all three phases, that produces badly inflated numbers.

The classic case — solar exporting on one phase while the house draws on the others:

| | Phase A | Phase B | Phase C | Sum |
|---|---|---|---|---|
| Power | −600 W | +50 W | +550 W | **0 W** |
| A netting grid meter records | | | | nothing |
| Shelly's counters record | 600 Wh export | 50 Wh import | 550 Wh import | 600 Wh export **and** 600 Wh import |

Verified on a Pro 3EM: `total_act_power` (register 31013) **is** correctly netted, but
`total_act_energy` (31162) is merely the sum of the per-phase counters.

Because of this, three-phase meters get four extra sensors — **no helpers to set up**:

| Entity | Unit | Meaning |
|---|---|---|
| **Grid Import Power (netted)** | W | `max(0, sum of all phase powers)` |
| **Grid Export Power (netted)** | W | `max(0, −sum of all phase powers)` |
| **Grid Import Energy (netted)** | kWh | the import power, integrated over time |
| **Grid Export Energy (netted)** | kWh | the export power, integrated over time |

The power sensors come from the already-netted signed power, so they behave like a netting
meter. The two energy counters integrate them with the trapezoidal rule — the same method
Home Assistant's Riemann sum helper uses — so you can put them straight into the energy
dashboard under **Grid consumption** and **Return to grid**.

The counters survive Home Assistant restarts. Readings more than 15 minutes apart, or a
reading that fails, break the chain instead of being integrated across, so a dropout cannot
invent energy.

**They start at zero.** Past energy cannot be reconstructed: the device's counters never
netted, and that information is not recoverable from them. The device's own
`Total Active Energy` sensors keep running unchanged next to them.

A shorter fast interval samples power more often and makes the counters more accurate;
1–2 s is reasonable. See [polling intervals](#3-tune-the-polling-intervals).

### Energy dashboard

On single-phase meters, or if your grid meter genuinely bills per phase, the device's own
`Total Active Energy` and `Total Active Returned Energy` are lifetime counters with
`state_class: total_increasing` and can be used directly.

---

## How it works

<div align="center">
<img src="assets/architecture.svg" alt="Data flow from the Shelly device through the Modbus client and coordinator to Home Assistant entities" width="100%">
</div>

### The three things Shelly's documentation does not spell out

Getting Shelly's Modbus right hinges on three details. All three were confirmed against physical
hardware.

**1. The documented addresses are not the wire addresses.**
Shelly documents its registers in the classic `3xxxx` input-register notation. The address
actually sent on the wire is that number **minus 30000**. The documented `31020` (phase A
voltage) is read as input register `1020`. Everything is read with **function code 0x04**
(read input registers) — holding registers are not implemented at all and return an exception.

**2. 32-bit values are word-swapped.**
`float32` and `uint32` span two registers with the **low word first** (CDAB). Reading them in
standard big-endian order produces plausible-looking garbage: the register pair for 240.4 V
decodes to `1.65e16` if you get this wrong.

**3. Strings are byte-swapped inside each register.**
The ASCII device identity registers store their two bytes per register in reverse. Read
big-endian, the MAC `A0DD6CA0E0CC` comes out as `0ADDC60A0ECC`.

### Register layout

Each component type has one register map with offsets; an instance sits at
`base + id × stride`:

| Component | Base (wire) | Documented | Stride | Contents |
|---|---|---|---|---|
| Device identity | 0 | 30000 | — | MAC, model, name |
| `em` | 1000 | 31000 | 80 | Three-phase live measurements |
| `emdata` | 1160 | 31160 | 70 | Three-phase energy counters |
| `em1` | 2000 | 32000 | 20 | Single-phase channel measurements |
| `em1data` | 2300 | 32300 | 20 | Single-phase channel energy counters |
| `switch` | 3000 | 33000 | 20 | Relay state and metering |
| Coils (relay control) | 100 | — | 10 | Writable output |
| Discrete inputs | 100 | — | 10 | Physical input state |

This lives in [`components.yaml`](custom_components/shelly_modbus/registers/components.yaml) and
[`models.yaml`](custom_components/shelly_modbus/registers/models.yaml). **Adding support for a
new device is a data change, not a code change.**

### Efficient reading

Registers are grouped into contiguous blocks and read in one request each. A Shelly Pro 3EM with
all default entities enabled is **three Modbus requests per cycle**, not 69. Blocks never cross
component boundaries (the gaps between components are unmapped and return an exception) and
never exceed 80 registers, which is the firmware's per-request limit.

---

## Verification

The register map is not transcribed from documentation and hoped for the best. The repository
contains a live test that runs the integration's own code against a physical device and compares
every decoded value with the value that same device reports over its RPC API:

```bash
python3 tests/live_test.py 192.168.1.88
```

```
========================================================================
192.168.1.88  SPEM-003CEBEU  gen2  profile=triphase  fw=2.0.0
  69 definitions in 3 block reads
  identity: model='SPEM-003CEBEU' mac='A0DD6CA0E0CC'
  compared 29 values against RPC, 0 mismatched, 0 failed blocks
  decoded 68/69 registers
========================================================================
PASS: all 1 device(s) verified
```

The unit test suite runs without hardware and without Home Assistant:

```bash
pip install pytest pyyaml pymodbus
python3 -m pytest tests/
```

It covers decoding against register values captured from real devices, address arithmetic for
every model and profile, block planning, and translation completeness.

---

## Troubleshooting

<details>
<summary><b>"Cannot reach the device on this address"</b></summary>

Modbus is almost certainly still disabled. Check:

```bash
curl -s http://<device-ip>/rpc/Modbus.GetConfig
```

If this returns `{"enable":false}`, enable it as shown in
[Enabling Modbus](#1-enable-modbus-on-the-device). If it returns nothing at all, the device is
unreachable or does not support Modbus.

Then confirm port 502 is open:

```bash
nc -vz <device-ip> 502
```
</details>

<details>
<summary><b>"Connected, but the device did not expose any known Modbus components"</b></summary>

The Modbus server answered but no known component block responded. This happens on device models
that implement Modbus without any of the components this integration knows. Please
[open an issue](https://github.com/sphings79/shelly-modbus-home-assistant/issues) with the output
of:

```bash
curl -s http://<device-ip>/rpc/Shelly.GetDeviceInfo
curl -s "http://<device-ip>/rpc/Shelly.GetComponents?dynamic_only=false"
```
</details>

<details>
<summary><b>Values look absurd (e.g. 1.65e16 V)</b></summary>

That is the signature of a word-order mismatch. This integration handles Shelly's word order
correctly, so if you see it, the device is likely reporting a register this integration maps to
the wrong type. Please open an issue with the model and the affected entity.
</details>

<details>
<summary><b>Wrong number of phases or channels</b></summary>

The measuring profile is wrong. Remove the integration and add it again, choosing the other
profile in the model step. On the device, the profile is set under **Settings → Measuring
profile**.
</details>

<details>
<summary><b>Entities show as unavailable after a while</b></summary>

Shelly devices accept a limited number of concurrent Modbus connections. If another client (an
inverter, a PLC, another Home Assistant instance) is also connected, the device may drop yours.
Increase the polling intervals, or reduce the number of connected clients.
</details>

<details>
<summary><b>Enabling debug logging</b></summary>

```yaml
# configuration.yaml
logger:
  default: warning
  logs:
    custom_components.shelly_modbus: debug
```
</details>

---

## Contributing

Adding a device usually means adding an entry to
[`models.yaml`](custom_components/shelly_modbus/registers/models.yaml) — no Python required. If
the device uses a component that is not mapped yet, add it to
[`components.yaml`](custom_components/shelly_modbus/registers/components.yaml).

Before opening a pull request:

```bash
python3 -m pytest tests/          # unit tests
ruff check custom_components tests
ruff format --check custom_components tests
```

If you have hardware, please include the output of `tests/live_test.py` for your device.

---

## Credits

- Register semantics from the
  [Shelly Gen2+ API documentation](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Modbus/).
- Architecture inspired by
  [ViperRNMC/marstek_venus_modbus](https://github.com/ViperRNMC/marstek_venus_modbus), whose
  YAML-driven register approach this integration follows.
- Word-order behaviour cross-checked against
  [pipelka/dbus-modbus-shelly](https://github.com/pipelka/dbus-modbus-shelly).

## License

[MIT](LICENSE)

---

<div align="center">
<sub>

**Keywords:** Home Assistant · Shelly · Modbus · Modbus TCP · HACS · custom integration ·
energy monitoring · Shelly Pro 3EM · Shelly 3EM-63 Gen3 · Shelly EM Gen4 · smart meter ·
local polling · energy dashboard · photovoltaics · zero export

</sub>
</div>
