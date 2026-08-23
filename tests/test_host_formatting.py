"""Host strings must stay valid inside a URL.

Regression tests for a bug found on a live system: zeroconf handed out an IPv6
address, the device's configuration_url became "http://d0:d71d:...", and Home
Assistant rejected it as having a non-numeric port. Device registration failed,
so not a single entity was created.
"""

from urllib.parse import urlsplit

import pytest
from shelly_modbus.helpers.modbus_client import format_host


class TestFormatHost:
    @pytest.mark.parametrize(
        "host",
        ["192.168.1.88", "10.0.0.1", "shelly.local", "shellypro3em-a0dd6c.local"],
    )
    def test_ipv4_and_hostnames_are_untouched(self, host):
        assert format_host(host) == host

    @pytest.mark.parametrize(
        ("host", "expected"),
        [
            # The exact address from the live failure.
            (
                "d0:d71d:c901:a2dd:6cff:fea0:e0cf",
                "[d0:d71d:c901:a2dd:6cff:fea0:e0cf]",
            ),
            ("fe80::1", "[fe80::1]"),
            ("::1", "[::1]"),
            ("2001:db8::8a2e:370:7334", "[2001:db8::8a2e:370:7334]"),
        ],
    )
    def test_ipv6_gets_bracketed(self, host, expected):
        assert format_host(host) == expected

    def test_already_bracketed_is_left_alone(self):
        assert format_host("[fe80::1]") == "[fe80::1]"

    @pytest.mark.parametrize(
        "host",
        [
            "192.168.1.88",
            # The address behind the live failure. yarl truncated it at the
            # first colon when reporting the error, which is why the log shows
            # only the tail.
            "2003:d0:d71d:c901:a2dd:6cff:fea0:e0cf",
            "fe80::1",
            "shelly.local",
        ],
    )
    def test_result_parses_as_a_url(self, host):
        """This is what Home Assistant does with configuration_url."""
        parts = urlsplit(f"http://{format_host(host)}")
        # Accessing .port raises ValueError on the unbracketed form.
        assert parts.port is None
        assert parts.hostname

    def test_unbracketed_ipv6_is_what_broke_it(self):
        """Without the fix the URL is rejected - this is the original bug."""
        with pytest.raises(ValueError):
            urlsplit("http://2003:d0:d71d:c901:a2dd:6cff:fea0:e0cf").port
