"""Request plumbing: timeout handling, the retry budget and request pacing.

These exercise ShellyModbusClient against a stubbed pymodbus client, so no
device and no Home Assistant is involved.
"""

import asyncio

from shelly_modbus.const import DEFAULT_TIMEOUT
from shelly_modbus.helpers.modbus_client import ShellyModbusClient


class FakeResponse:
    """Minimal stand-in for a pymodbus response."""

    def __init__(self, registers=None, error=False):
        self.registers = registers or [0, 0]
        self._error = error

    def isError(self):  # noqa: N802 - pymodbus spells it this way
        return self._error


class FakeModbus:
    """Stubbed pymodbus client recording when each call was made."""

    connected = True

    def __init__(self, behaviour="ok"):
        self.behaviour = behaviour
        self.calls: list[float] = []

    async def read_input_registers(self, address, count, **kwargs):
        self.calls.append(asyncio.get_running_loop().time())
        if self.behaviour == "hang":
            await asyncio.sleep(3600)
        if self.behaviour == "error":
            return FakeResponse(error=True)
        return FakeResponse([0] * count)

    def close(self):
        return None


def make_client(behaviour="ok", **kwargs):
    """Return a client wired to a stubbed pymodbus client.

    Reconnecting hands back the same stub, so a retry keeps recording into the
    same call list instead of reaching for the network.
    """
    client = ShellyModbusClient("192.0.2.1", 502, **kwargs)
    fake = FakeModbus(behaviour)
    client.client = fake

    async def reconnect():
        client.client = fake
        return True

    client.async_connect = reconnect
    return client


class TestTimeoutGuard:
    """pymodbus reads a missing timeout as 'wait forever'."""

    def test_none_falls_back_to_the_default(self):
        assert ShellyModbusClient("h", 502, timeout=None).timeout == DEFAULT_TIMEOUT

    def test_zero_falls_back_to_the_default(self):
        assert ShellyModbusClient("h", 502, timeout=0).timeout == DEFAULT_TIMEOUT

    def test_a_real_value_is_kept(self):
        assert ShellyModbusClient("h", 502, timeout=7).timeout == 7.0


class TestRequestBudget:
    """All attempts of one request share a single deadline."""

    def test_a_hanging_device_gives_up_within_the_budget(self):
        client = make_client("hang", timeout=0.05)

        async def run():
            started = asyncio.get_running_loop().time()
            result = await client.async_read_input_registers(1020, 2)
            return result, asyncio.get_running_loop().time() - started

        result, elapsed = asyncio.run(run())

        assert result is None
        # Without the shared deadline this would be retries x (connect + read).
        assert elapsed < client._request_budget * 2
        assert elapsed >= client._request_budget * 0.5

    def test_the_socket_is_dropped_after_a_cut_off_request(self):
        """A cancelled request leaves the transaction half-done."""
        client = make_client("hang", timeout=0.05)

        asyncio.run(client.async_read_input_registers(1020, 2))

        assert client.client is None
        assert not client.is_connected

    def test_a_fast_failure_still_uses_every_attempt(self):
        """The budget must not eat the retries a flaky device needs."""
        client = make_client("error", timeout=5)

        result = asyncio.run(client.async_read_input_registers(1020, 2, retries=3))

        assert result is None
        assert len(client.client.calls) == 3


class TestPacing:
    """Requests are spaced by message_wait_ms, once - not twice."""

    def test_consecutive_reads_wait_exactly_one_interval(self):
        client = make_client(message_wait_ms=50)

        async def run():
            for _ in range(3):
                await client.async_read_input_registers(1020, 2)

        asyncio.run(run())

        calls = client.client.calls
        gaps = [b - a for a, b in zip(calls, calls[1:])]
        assert gaps, "expected more than one request"
        for gap in gaps:
            assert 0.045 <= gap < 0.09, f"expected ~50 ms spacing, got {gap * 1000:.0f}"
