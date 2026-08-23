# Contributing

## Adding a device

Most devices need no Python at all. The register maps are data:

- [`registers/components.yaml`](custom_components/shelly_modbus/registers/components.yaml) —
  one map per Shelly component type, with offsets relative to the component base.
- [`registers/models.yaml`](custom_components/shelly_modbus/registers/models.yaml) —
  which component instances each model publishes.

To add a model, add an entry to `models.yaml` with its exact model code (the string the device
reports in input registers 6..15) and the components it publishes. If it uses a component that is
not mapped yet, add that to `components.yaml` first.

A component instance's base address is `base + id × stride`.

## Register addressing, in short

- Shelly documents addresses in `3xxxx` notation; the wire address is that **minus 30000**.
- Everything is read with **function code 0x04** (input registers).
- `float32` and `uint32` are **low word first** (CDAB).
- ASCII strings are **byte-swapped within each register**.
- A single request may read at most **80 registers**.

## Running the checks

```bash
pip install pytest pyyaml pymodbus ruff
python3 -m pytest tests/
ruff check custom_components tests
ruff format --check custom_components tests
```

## Testing against hardware

If you own the device, please run the live test and paste the output into your pull request:

```bash
python3 tests/live_test.py <device-ip>
```

It reads every register the integration defines and compares each decoded value with the value
the device reports over its own RPC API. A clean run is the strongest evidence a register map is
correct.

## Translations

Entity names live in `custom_components/shelly_modbus/translations/`. English (`en.json`) and
German (`de.json`) must stay in sync — the test suite enforces that every register has a name in
both, and that placeholders match.
