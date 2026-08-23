"""Tests for the trapezoidal energy integration.

The sensor class itself needs Home Assistant, so this reproduces the exact
accumulation rule and pins its behaviour, including the cases that would
otherwise invent or lose energy.
"""

import pytest
from shelly_modbus.registers import expand_definitions

MAX_GAP = 900  # must match MAX_INTEGRATION_GAP in sensor.py


class Integrator:
    """Mirror of ShellyModbusEnergySensor's accumulation."""

    def __init__(self, total=0.0):
        self.total = total
        self.last_power = None
        self.last_time = None

    def update(self, power, now):
        if power is None:
            # Break the chain so the outage is not integrated across.
            self.last_power = None
            self.last_time = None
            return self.total
        if self.last_power is not None and self.last_time is not None:
            elapsed = now - self.last_time
            if 0 < elapsed <= MAX_GAP:
                self.total += (power + self.last_power) / 2 * elapsed / 3_600_000
        self.last_power = power
        self.last_time = now
        return self.total


class TestAccumulation:
    def test_constant_load_for_one_hour(self):
        """1000 W held for an hour is 1 kWh, sampled every 5 s."""
        i = Integrator()
        for step in range(0, 3601, 5):
            i.update(1000.0, step)
        assert i.total == pytest.approx(1.0)

    def test_trapezoidal_ramp(self):
        """0 W rising linearly to 1000 W over an hour averages 500 W."""
        i = Integrator()
        for step in range(0, 3601, 5):
            i.update(1000.0 * step / 3600, step)
        assert i.total == pytest.approx(0.5)

    def test_five_second_samples_add_up(self):
        i = Integrator()
        for step in range(0, 3601, 5):
            i.update(2000.0, step)
        assert i.total == pytest.approx(2.0, rel=1e-6)

    def test_first_reading_adds_nothing(self):
        i = Integrator()
        i.update(5000.0, 0)
        assert i.total == 0.0

    def test_zero_power_adds_nothing(self):
        i = Integrator()
        i.update(0.0, 0)
        i.update(0.0, 3600)
        assert i.total == 0.0

    def test_counter_only_grows(self):
        """Fed a netted power sensor, which is never negative."""
        i = Integrator()
        previous = 0.0
        for n, p in enumerate([0.0, 500.0, 1200.0, 0.0, 80.0]):
            i.update(p, n * 5)
            assert i.total >= previous
            previous = i.total


class TestOutages:
    def test_dropout_is_not_integrated_across(self):
        """A missing reading must not become energy when the device returns."""
        i = Integrator()
        i.update(1000.0, 0)
        i.update(None, 5)  # device unreachable
        i.update(1000.0, 3600)  # back an hour later
        assert i.total == 0.0

    def test_long_gap_is_ignored(self):
        i = Integrator()
        i.update(1000.0, 0)
        i.update(1000.0, MAX_GAP + 1)
        assert i.total == 0.0

    def test_gap_at_the_limit_still_counts(self):
        i = Integrator()
        i.update(3600.0, 0)
        i.update(3600.0, MAX_GAP)
        assert i.total == pytest.approx(3600.0 * MAX_GAP / 3_600_000)

    def test_total_survives_a_restart(self):
        i = Integrator()
        for step in range(0, 3601, 5):
            i.update(1000.0, step)
        assert i.total == pytest.approx(1.0)

        restored = Integrator(total=i.total)  # RestoreSensor path
        assert restored.total == pytest.approx(1.0)

        # The first reading after a restart only seeds the chain; the downtime
        # was never measured and must not be integrated.
        restored.update(1000.0, 0)
        assert restored.total == pytest.approx(1.0)

        for step in range(5, 3601, 5):
            restored.update(1000.0, step)
        assert restored.total == pytest.approx(2.0)

    def test_backwards_clock_is_ignored(self):
        i = Integrator()
        i.update(1000.0, 100)
        i.update(1000.0, 50)
        assert i.total == 0.0


class TestDefinitions:
    def test_energy_counters_exist_on_grid_profiles(self):
        keys = {d["key"]: d for d in expand_definitions("SPEM-003CEBEU", "triphase")}
        assert "grid_import_energy" in keys
        assert "grid_export_energy" in keys

    def test_they_are_energy_totals(self):
        keys = {d["key"]: d for d in expand_definitions("SPEM-003CEBEU", "triphase")}
        for key in ("grid_import_energy", "grid_export_energy"):
            d = keys[key]
            assert d["unit"] == "kWh"
            assert d["device_class"] == "energy"
            assert d["state_class"] == "total_increasing"
            assert d["access"] == "integrated"
            assert d["enabled_by_default"] is True

    def test_each_counter_points_at_its_power_sensor(self):
        keys = {d["key"]: d for d in expand_definitions("SPEM-003CEBEU", "triphase")}
        assert keys["grid_import_energy"]["source"] == "grid_import_power"
        assert keys["grid_export_energy"]["source"] == "grid_export_power"

    def test_absent_where_channels_are_unrelated(self):
        keys = {d["key"] for d in expand_definitions("SPEM-002CEBEU50")}
        assert "grid_import_energy" not in keys
