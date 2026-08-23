"""
Live verification against real hardware.

Runs the integration's own register expansion, block planner, client and
decoder against a device, then compares every decoded value with the value the
same device reports over its RPC API.  This is what proves the register map,
the address translation and the word order are right.

Usage:  python3 tests/live_test.py <host> [<host> ...]
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
import urllib.request
from pathlib import Path

# Import the integration modules without pulling in Home Assistant.
ROOT = Path(__file__).resolve().parent.parent / "custom_components"
sys.path.insert(0, str(ROOT))
package = types.ModuleType("shelly_modbus")
package.__path__ = [str(ROOT / "shelly_modbus")]
sys.modules["shelly_modbus"] = package

from shelly_modbus.helpers.modbus_client import (  # noqa: E402
    ShellyModbusClient,
    decode_registers,
)
from shelly_modbus.registers import build_blocks, expand_definitions  # noqa: E402


def rpc(host: str, method: str, query: str = "") -> dict:
    """Call a Shelly RPC method and return the parsed response."""
    url = f"http://{host}/rpc/{method}{query}"
    with urllib.request.urlopen(url, timeout=6) as response:
        return json.load(response)


def reference_values(host: str) -> dict[str, float]:
    """Collect the device's own readings, keyed like our definitions."""
    reference: dict[str, float] = {}

    try:
        status = rpc(host, "EM.GetStatus", "?id=0")
        for name, value in status.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                reference[f"em_0_{name}"] = float(value)
    except Exception:
        pass

    try:
        status = rpc(host, "EMData.GetStatus", "?id=0")
        for name, value in status.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                # Our energy sensors are scaled to kWh.
                reference[f"emdata_0_{name}"] = float(value) / 1000.0
    except Exception:
        pass

    for component_id in range(3):
        for component, scale in (("em1", 1.0), ("em1data", 1000.0)):
            try:
                status = rpc(
                    host,
                    f"{'EM1' if component == 'em1' else 'EM1Data'}.GetStatus",
                    f"?id={component_id}",
                )
            except Exception:
                continue
            for name, value in status.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    reference[f"{component}_{component_id}_{name}"] = (
                        float(value) / scale
                    )

    return reference


# RPC field names that map onto a differently named definition.
ALIASES = {
    "emdata_0_total_act": "emdata_0_total_act_energy",
    "emdata_0_total_act_ret": "emdata_0_total_act_ret_energy",
}


async def check(host: str) -> bool:
    """Read the whole register map from one device and verify it."""
    print("=" * 72)
    info = rpc(host, "Shelly.GetDeviceInfo")
    model = info["model"]
    profile = info.get("profile")
    print(f"{host}  {model}  gen{info['gen']}  profile={profile}  fw={info['ver']}")

    definitions = expand_definitions(model, profile)
    if not definitions:
        print(f"  FAIL: no definitions for model {model}")
        return False

    client = ShellyModbusClient(host=host, port=502)
    if not await client.async_connect():
        print("  FAIL: cannot connect")
        return False

    values: dict[str, object] = {}
    failed_blocks = 0

    try:
        blocks = build_blocks(definitions)
        print(f"  {len(definitions)} definitions in {len(blocks)} block reads")

        for block in blocks:
            start = block[0]["address"]
            end = max(d["address"] + d.get("count", 1) for d in block)
            registers = await client.async_read_input_registers(start, end - start)

            if registers is None:
                failed_blocks += 1
                print(f"  block {start}..{end - 1} FAILED")
                continue

            for definition in block:
                offset = definition["address"] - start
                chunk = registers[offset : offset + definition.get("count", 1)]
                value = decode_registers(chunk, definition["data_type"])
                if value is not None and (scale := definition.get("scale")):
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        value = value * scale
                values[definition["key"]] = value
    finally:
        await client.async_close()

    # Derived sensors are computed from the values just read, exactly as the
    # coordinator does, so the netting logic is exercised against real readings.
    netted_ok = True
    for definition in definitions:
        if definition.get("access") != "derived":
            continue
        parts = [values.get(src) for src in definition["sources"]]
        if any(p is None for p in parts):
            values[definition["key"]] = None
            continue
        total = sum(parts)
        values[definition["key"]] = (
            max(total, 0.0) if definition["sign"] == "positive" else max(-total, 0.0)
        )

    if "grid_import_power" in values and "grid_export_power" in values:
        imp, exp = values["grid_import_power"], values["grid_export_power"]
        signed = (
            sum(
                values.get(src, 0.0)
                for d in definitions
                if d.get("access") == "derived"
                for src in d["sources"]
            )
            / 2
        )  # both sensors share the same sources
        netted_ok = abs((imp - exp) - signed) < 0.01
        print(
            f"  netted: import={imp:.2f} W export={exp:.2f} W "
            f"(signed total {signed:.2f} W) -> {'OK' if netted_ok else 'MISMATCH'}"
        )

    reference = reference_values(host)

    compared = mismatched = 0
    for key, expected in reference.items():
        target = ALIASES.get(key, key)
        if target not in values:
            continue
        actual = values[target]
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            continue
        compared += 1
        tolerance = max(abs(expected) * 0.02, 0.05)
        if abs(actual - expected) > tolerance:
            mismatched += 1
            print(f"  MISMATCH {target}: modbus={actual!r} rpc={expected!r}")

    identity_ok = values.get("model") == model
    print(f"  identity: model={values.get('model')!r} mac={values.get('mac')!r}")
    print(
        f"  compared {compared} values against RPC, {mismatched} mismatched, "
        f"{failed_blocks} failed blocks"
    )

    register_defs = [d for d in definitions if d.get("access") != "derived"]
    decoded = sum(1 for d in register_defs if values.get(d["key"]) is not None)
    print(f"  decoded {decoded}/{len(register_defs)} registers")

    return (
        mismatched == 0
        and failed_blocks == 0
        and identity_ok
        and compared > 0
        and netted_ok
    )


async def main() -> int:
    hosts = sys.argv[1:]
    if not hosts:
        print(__doc__)
        return 2

    results = [await check(host) for host in hosts]
    print("=" * 72)
    if all(results):
        print(f"PASS: all {len(results)} device(s) verified")
        return 0
    print(f"FAIL: {results.count(False)} of {len(results)} device(s) failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
