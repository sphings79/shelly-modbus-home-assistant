"""
Modbus-TCP transport for Shelly Gen2+ devices.

Shelly exposes everything measurable as *input registers* (function code 0x04);
relay outputs are coils (0x01/0x05) and physical inputs are discrete inputs
(0x02).  Holding registers are not implemented by the firmware at all.

Address translation
-------------------
The Shelly documentation lists input registers in the classic "3xxxx" notation.
The address actually sent on the wire is that number minus 30000, so the
documented 31020 (EM phase A voltage) is read as input register 1020.  Callers
pass wire addresses; :data:`INPUT_REGISTER_OFFSET` is only used for logging.

Encoding
--------
Verified against a Shelly Pro 3EM (SPEM-003CEBEU) and a Shelly 3EM-63 Gen3
(S3EM-003CXCEU63) on firmware 2.0.0 by comparing every decoded value with the
device's own RPC output:

``float``   32 bit IEEE754 over two registers, **low word first** (CDAB).
``uint32``  32 bit unsigned over two registers, **low word first**.
``boolean`` one register, 0 or 1.
``char``    ASCII, two bytes per register, **byte-swapped within each register**.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import struct
from typing import Any

from pymodbus.client.tcp import AsyncModbusTcpClient

from ..const import (
    DEFAULT_MESSAGE_WAIT_MS,
    DEFAULT_TIMEOUT,
    DEFAULT_UNIT_ID,
    INPUT_REGISTER_OFFSET,
    MAX_BLOCK_SIZE,
)

_LOGGER = logging.getLogger(__name__)

# Number of registers each data type occupies.
REGISTER_COUNTS = {
    "float": 2,
    "uint32": 2,
    "int32": 2,
    "boolean": 1,
    "uint16": 1,
}


def register_count(data_type: str, count: int | None = None) -> int:
    """Return how many registers a field of ``data_type`` occupies."""
    if count is not None:
        return int(count)
    return REGISTER_COUNTS.get(data_type, 1)


def decode_registers(regs: list[int], data_type: str) -> Any:
    """Decode raw input registers into a Python value.

    ``regs`` must already hold exactly the registers belonging to the field.
    Returns ``None`` when the block is too short to decode.
    """
    if data_type == "boolean":
        return bool(regs[0])

    if data_type == "uint16":
        return regs[0]

    if data_type in ("float", "uint32", "int32"):
        if len(regs) < 2:
            _LOGGER.warning("Expected 2 registers for %s, got %d", data_type, len(regs))
            return None
        # Low word first: rebuild as big-endian with the words swapped.
        packed = struct.pack(">2H", regs[1], regs[0])
        if data_type == "float":
            value = struct.unpack(">f", packed)[0]
            # The firmware reports unpopulated slots as NaN/inf.
            if value != value or value in (float("inf"), float("-inf")):
                return None
            return value
        if data_type == "uint32":
            return struct.unpack(">I", packed)[0]
        return struct.unpack(">i", packed)[0]

    if data_type == "char":
        raw = bytearray()
        for reg in regs:
            # Bytes are swapped inside each register.
            raw.append(reg & 0xFF)
            raw.append((reg >> 8) & 0xFF)
        text = raw.split(b"\0")[0].decode("ascii", errors="ignore").strip()
        return text or None

    raise ValueError(f"Unsupported data_type: {data_type}")


class ShellyModbusClient:
    """Async Modbus-TCP client tailored to Shelly's register layout."""

    def __init__(
        self,
        host: str,
        port: int,
        unit_id: int = DEFAULT_UNIT_ID,
        timeout: int = DEFAULT_TIMEOUT,
        message_wait_ms: int = DEFAULT_MESSAGE_WAIT_MS,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

        try:
            self.unit_id = int(unit_id)
        except (TypeError, ValueError):
            self.unit_id = DEFAULT_UNIT_ID

        try:
            self.message_wait_sec = max(0.0, float(message_wait_ms) / 1000.0)
        except (TypeError, ValueError):
            self.message_wait_sec = DEFAULT_MESSAGE_WAIT_MS / 1000.0

        self.client: AsyncModbusTcpClient | None = None
        # Serialises requests so concurrent reads cannot collide on
        # transaction ids.
        self._lock = asyncio.Lock()
        self._last_finished_at: float | None = None

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Return True while the underlying client holds an open socket."""
        return bool(self.client and getattr(self.client, "connected", False))

    async def async_connect(self) -> bool:
        """Open a fresh connection, replacing any previous client."""
        await self._discard_client()

        self.client = AsyncModbusTcpClient(
            host=self.host, port=self.port, timeout=self.timeout
        )

        try:
            connected = await self.client.connect()
        except Exception as err:  # noqa: BLE001 - surfaced as a failed connect
            _LOGGER.debug("Connect to %s:%s failed: %s", self.host, self.port, err)
            return False

        if not connected:
            _LOGGER.debug("Could not connect to %s:%s", self.host, self.port)
            return False

        self._enable_keepalive()
        _LOGGER.debug("Connected to Shelly Modbus server %s:%s", self.host, self.port)
        return True

    def _enable_keepalive(self) -> None:
        """Ask the OS to probe dead peers instead of hanging for hours."""
        try:
            transport = getattr(self.client, "transport", None)
            sock = transport.get_extra_info("socket") if transport else None
            if sock is None:
                return
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            if hasattr(socket, "TCP_KEEPIDLE"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
            if hasattr(socket, "TCP_KEEPINTVL"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
            if hasattr(socket, "TCP_KEEPCNT"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
        except Exception as err:  # noqa: BLE001 - keepalive is best effort
            _LOGGER.debug("Could not enable TCP keepalive: %s", err)

    async def _discard_client(self) -> None:
        """Close and drop the current client, ignoring shutdown errors."""
        if not self.client:
            return
        try:
            result = self.client.close()
            if asyncio.iscoroutine(result):
                await result
        except Exception as err:  # noqa: BLE001 - closing must never raise
            _LOGGER.debug("Error closing Modbus client: %s", err)
        finally:
            self.client = None

    async def async_close(self) -> None:
        """Close the connection."""
        async with self._lock:
            await self._discard_client()

    async def _ensure_connected(self) -> bool:
        """Reconnect if the socket dropped."""
        if self.is_connected:
            return True
        return await self.async_connect()

    # ------------------------------------------------------------------
    # Request plumbing
    # ------------------------------------------------------------------

    async def _execute(self, call_name: str, **kwargs: Any):
        """Run one pymodbus call under the request lock, with pacing.

        Returns the pymodbus response, or ``None`` if the request could not be
        sent or came back as an error.
        """
        if not await self._ensure_connected():
            return None

        async with self._lock:
            # Space requests out so the device is not overwhelmed.
            if self._last_finished_at is not None and self.message_wait_sec > 0:
                elapsed = asyncio.get_running_loop().time() - self._last_finished_at
                if (wait := self.message_wait_sec - elapsed) > 0:
                    await asyncio.sleep(wait)

            try:
                method = getattr(self.client, call_name)
                # pymodbus renamed the unit kwarg across versions.
                for unit_kw in ("device_id", "slave", "unit"):
                    try:
                        return await method(**kwargs, **{unit_kw: self.unit_id})
                    except TypeError:
                        continue
                _LOGGER.error("No compatible unit keyword for %s", call_name)
                return None
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 - retried by the caller
                cause = getattr(err, "__cause__", None)
                if isinstance(cause, asyncio.CancelledError):
                    # Shutdown cancellation must propagate, not be retried.
                    raise cause from err
                _LOGGER.debug("Modbus %s failed: %s", call_name, err)
                await self._discard_client()
                return None
            finally:
                self._last_finished_at = asyncio.get_running_loop().time()

    async def _request(self, call_name: str, retries: int, **kwargs: Any):
        """Run a call with retries, reconnecting between attempts."""
        for attempt in range(retries):
            result = await self._execute(call_name, **kwargs)
            if result is not None and not result.isError():
                return result

            if attempt + 1 < retries:
                await self._discard_client()
                await asyncio.sleep(0.2 * (attempt + 1))

        return None

    # ------------------------------------------------------------------
    # Public reads and writes
    # ------------------------------------------------------------------

    async def async_read_input_registers(
        self, address: int, count: int, retries: int = 3
    ) -> list[int] | None:
        """Read ``count`` input registers starting at wire address ``address``."""
        if not 0 <= address <= 0xFFFF:
            _LOGGER.error("Invalid register address %d", address)
            return None
        if not 1 <= count <= MAX_BLOCK_SIZE:
            _LOGGER.error(
                "Invalid register count %d (device allows 1..%d)", count, MAX_BLOCK_SIZE
            )
            return None

        result = await self._request(
            "read_input_registers", retries, address=address, count=count
        )
        if result is None:
            _LOGGER.debug(
                "Failed reading input registers %d..%d (documented %d..%d)",
                address,
                address + count - 1,
                address + INPUT_REGISTER_OFFSET,
                address + INPUT_REGISTER_OFFSET + count - 1,
            )
            return None

        registers = list(result.registers)
        if len(registers) < count:
            _LOGGER.debug(
                "Short read at %d: wanted %d registers, got %d",
                address,
                count,
                len(registers),
            )
            return None
        return registers

    async def async_read_coil(self, address: int, retries: int = 3) -> bool | None:
        """Read a single coil (relay output state)."""
        result = await self._request("read_coils", retries, address=address, count=1)
        if result is None or not getattr(result, "bits", None):
            return None
        return bool(result.bits[0])

    async def async_write_coil(
        self, address: int, value: bool, retries: int = 3
    ) -> bool:
        """Write a single coil, turning a relay output on or off."""
        result = await self._request(
            "write_coil", retries, address=address, value=bool(value)
        )
        return result is not None

    async def async_read_discrete_input(
        self, address: int, retries: int = 3
    ) -> bool | None:
        """Read a single discrete input (physical input state)."""
        result = await self._request(
            "read_discrete_inputs", retries, address=address, count=1
        )
        if result is None or not getattr(result, "bits", None):
            return None
        return bool(result.bits[0])

    async def async_probe(self, address: int, count: int = 2) -> bool:
        """Return True when ``address`` answers, used to detect components.

        Uses a single attempt: an absent component replies with an exception
        response, which is a definite answer and must not be retried.
        """
        result = await self._request(
            "read_input_registers", 1, address=address, count=count
        )
        return result is not None
