"""The quiet reachability check in front of the Modbus client.

Discovery reruns on every mDNS announcement, so a Shelly with Modbus switched
off used to produce two pymodbus warnings every few minutes, forever. This
check answers "is anything listening" without involving pymodbus at all.
"""

import asyncio
import socket

from shelly_modbus.helpers.modbus_client import async_port_is_open


def free_port() -> int:
    """Return a port number nothing is listening on."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class TestAsyncPortIsOpen:
    def test_open_port_is_reported_open(self):
        async def run():
            connected = asyncio.Event()

            async def handle(reader, writer):
                connected.set()
                writer.close()

            server = await asyncio.start_server(handle, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            try:
                return await async_port_is_open("127.0.0.1", port)
            finally:
                server.close()
                await server.wait_closed()

        assert asyncio.run(run()) is True

    def test_refused_port_is_reported_closed(self):
        """A Shelly without Modbus refuses 502 exactly like this."""
        port = free_port()

        assert asyncio.run(async_port_is_open("127.0.0.1", port)) is False

    def test_unresolvable_host_is_reported_closed(self):
        result = asyncio.run(async_port_is_open("no-such-host.invalid", 502, timeout=1))

        assert result is False

    def test_a_hanging_connect_gives_up_after_the_timeout(self, monkeypatch):
        """A device that drops packets must not stall the discovery flow."""

        async def never_connects(*args, **kwargs):
            await asyncio.sleep(3600)

        monkeypatch.setattr(asyncio, "open_connection", never_connects)

        async def run():
            loop = asyncio.get_running_loop()
            started = loop.time()
            result = await async_port_is_open("192.0.2.1", 502, timeout=0.2)
            return result, loop.time() - started

        result, elapsed = asyncio.run(run())

        assert result is False
        assert elapsed < 1

    def test_the_probe_closes_its_socket(self):
        """Nothing may be left half-open on the device."""

        async def run():
            closed = asyncio.Event()

            async def handle(reader, writer):
                # Returns once the peer has gone away.
                await reader.read()
                closed.set()
                writer.close()

            server = await asyncio.start_server(handle, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            try:
                await async_port_is_open("127.0.0.1", port)
                await asyncio.wait_for(closed.wait(), timeout=2)
            finally:
                server.close()
                await server.wait_closed()
            return True

        assert asyncio.run(run()) is True
