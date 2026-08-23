"""Decoder tests using register values captured from real devices."""

import pytest
from shelly_modbus.helpers.modbus_client import decode_registers, register_count


class TestFloat:
    """Shelly encodes float32 low word first (CDAB)."""

    @pytest.mark.parametrize(
        ("registers", "expected"),
        [
            # Captured from a Pro 3EM alongside its RPC readings.
            ([23147, 17264], 240.353),  # phase A voltage, RPC said 240.4 V
            ([48472, 16317], 1.4823),  # phase A current, RPC said 1.482 A
            ([50091, 16808], 21.0955),  # total active power, RPC said 21.096 W
            ([5122, 16968], 50.0195),  # phase A frequency
            ([0, 0], 0.0),
        ],
    )
    def test_decodes_low_word_first(self, registers, expected):
        assert decode_registers(registers, "float") == pytest.approx(expected, rel=1e-4)

    def test_word_order_actually_matters(self):
        """Swapping the words must not produce the same number."""
        swapped = decode_registers([17264, 23147], "float")
        assert swapped != pytest.approx(240.353, rel=1e-4)

    def test_short_block_returns_none(self):
        assert decode_registers([1], "float") is None

    def test_nan_becomes_none(self):
        # All-ones exponent with a payload is NaN, used for unpopulated slots.
        assert decode_registers([0xFFFF, 0x7FFF], "float") is None


class TestInteger:
    def test_uint32_is_low_word_first(self):
        # EM timestamp captured together with the device clock.
        assert decode_registers([54493, 27274], "uint32") == 1787483357

    def test_boolean(self):
        assert decode_registers([0], "boolean") is False
        assert decode_registers([1], "boolean") is True

    def test_uint16(self):
        assert decode_registers([4242], "uint16") == 4242


class TestText:
    """ASCII strings are byte-swapped inside each register."""

    def test_mac_from_pro_3em(self):
        registers = [12353, 17476, 17206, 12353, 12357, 17219]
        assert decode_registers(registers, "char") == "A0DD6CA0E0CC"

    def test_model_from_3em_63_gen3(self):
        registers = [13139, 19781, 12333, 13104, 22595, 17731, 13909, 51, 0, 0]
        assert decode_registers(registers, "char") == "S3EM-003CXCEU63"

    def test_empty_string_becomes_none(self):
        assert decode_registers([0, 0, 0], "char") is None


class TestRegisterCount:
    @pytest.mark.parametrize(
        ("data_type", "expected"),
        [("float", 2), ("uint32", 2), ("boolean", 1), ("uint16", 1)],
    )
    def test_defaults(self, data_type, expected):
        assert register_count(data_type) == expected

    def test_explicit_count_wins(self):
        assert register_count("char", 10) == 10


def test_unsupported_type_raises():
    with pytest.raises(ValueError):
        decode_registers([0], "nonsense")
