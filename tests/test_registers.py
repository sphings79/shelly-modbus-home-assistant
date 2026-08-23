"""Tests for register expansion and read planning."""

import pytest
from shelly_modbus.const import MAX_BLOCK_SIZE
from shelly_modbus.registers import (
    build_blocks,
    expand_definitions,
    load_components,
    load_models,
    model_options,
    profiles_for_model,
)

ALL_MODELS = sorted(load_models())


def definitions_by_key(model, profile=None):
    return {d["key"]: d for d in expand_definitions(model, profile)}


class TestAddressing:
    """Addresses must match the documented map minus the 30000 offset."""

    @pytest.mark.parametrize(
        ("key", "address"),
        [
            ("mac", 0),  # documented 30000
            ("model", 6),  # documented 30006
            ("em_0_total_act_power", 1013),  # documented 31013
            ("em_0_a_voltage", 1020),  # documented 31020
            ("em_0_c_freq", 1073),  # documented 31073
            ("emdata_0_total_act_energy", 1162),  # documented 31162
            ("emdata_0_a_total_act_energy", 1182),  # documented 31182
            ("emdata_0_c_total_act_ret_energy", 1224),
        ],
    )
    def test_triphase_addresses(self, key, address):
        assert (
            definitions_by_key("SPEM-003CEBEU", "triphase")[key]["address"] == address
        )

    @pytest.mark.parametrize(
        ("key", "address"),
        [
            ("em1_0_voltage", 2003),  # documented 32003
            ("em1_1_voltage", 2023),  # second instance is +20
            ("em1_2_voltage", 2043),
            ("em1data_0_total_act_energy", 2310),
            ("em1data_2_total_act_energy", 2350),
        ],
    )
    def test_monophase_addresses(self, key, address):
        assert (
            definitions_by_key("SPEM-003CEBEU", "monophase")[key]["address"] == address
        )

    def test_switch_uses_input_register_and_coil(self):
        definition = definitions_by_key("S4SW-002P16EU")["switch_1_output"]
        assert definition["address"] == 3020  # documented 33020
        assert definition["coil_address"] == 110  # 100 + 1 * 10

    def test_input_is_a_discrete_input(self):
        definition = definitions_by_key("S4SW-002P16EU")["input_1_state"]
        assert definition["access"] == "discrete_input"
        assert definition["address"] == 110


class TestExpansion:
    def test_unknown_model_yields_nothing(self):
        assert expand_definitions("NOT-A-SHELLY") == []

    def test_every_model_expands(self):
        for model in ALL_MODELS:
            for profile in profiles_for_model(model):
                assert expand_definitions(model, profile), f"{model}/{profile} empty"

    def test_keys_are_unique_per_model(self):
        for model in ALL_MODELS:
            for profile in profiles_for_model(model):
                keys = [d["key"] for d in expand_definitions(model, profile)]
                assert len(keys) == len(set(keys)), f"duplicate keys in {model}"

    def test_device_identity_always_present(self):
        for model in ALL_MODELS:
            keys = definitions_by_key(model)
            assert "mac" in keys and "model" in keys

    def test_unknown_profile_falls_back_to_default(self):
        fallback = expand_definitions("SPEM-003CEBEU", "does-not-exist")
        assert fallback == expand_definitions("SPEM-003CEBEU", "triphase")

    def test_non_metering_switch_has_no_power_sensors(self):
        keys = definitions_by_key("S4SW-001X16EU")
        assert "switch_0_output" in keys
        assert "switch_0_act_power" not in keys

    def test_metering_switch_has_power_sensors(self):
        assert "switch_0_act_power" in definitions_by_key("S4SW-001P16EU")

    def test_model_options_cover_every_model(self):
        assert set(model_options()) == set(ALL_MODELS)


class TestTranslationKeys:
    def test_instances_share_a_translation_key(self):
        keys = definitions_by_key("SPEM-003CEBEU", "monophase")
        assert (
            keys["em1_0_voltage"]["translation_key"]
            == keys["em1_1_voltage"]["translation_key"]
            == "em1_voltage"
        )

    def test_instance_number_is_one_based(self):
        keys = definitions_by_key("SPEM-003CEBEU", "monophase")
        assert keys["em1_1_voltage"]["translation_placeholders"] == {"idx": "2"}

    def test_single_instance_components_have_no_placeholder(self):
        keys = definitions_by_key("SPEM-003CEBEU", "triphase")
        assert keys["em_0_a_voltage"]["translation_placeholders"] is None


class TestBlockPlanning:
    def test_blocks_respect_the_device_limit(self):
        for model in ALL_MODELS:
            for profile in profiles_for_model(model):
                for block in build_blocks(expand_definitions(model, profile)):
                    start = block[0]["address"]
                    end = max(d["address"] + d.get("count", 1) for d in block)
                    assert end - start <= MAX_BLOCK_SIZE

    def test_blocks_never_span_components(self):
        for model in ALL_MODELS:
            for profile in profiles_for_model(model):
                for block in build_blocks(expand_definitions(model, profile)):
                    groups = {(d["component"], d["component_id"]) for d in block}
                    assert len(groups) == 1

    def test_every_input_register_lands_in_exactly_one_block(self):
        definitions = expand_definitions("SPEM-003CEBEU", "triphase")
        expected = {d["key"] for d in definitions if d["access"] == "input_register"}
        planned = [d["key"] for block in build_blocks(definitions) for d in block]
        assert sorted(planned) == sorted(expected)

    def test_discrete_inputs_are_not_block_read(self):
        definitions = expand_definitions("S4SW-002P16EU")
        planned = {d["key"] for block in build_blocks(definitions) for d in block}
        assert not any(key.endswith("_state") for key in planned)

    def test_reads_are_batched_not_one_per_register(self):
        definitions = expand_definitions("SPEM-003CEBEU", "triphase")
        blocks = build_blocks(definitions)
        assert len(blocks) < 10, "block planner should batch aggressively"


class TestComponentMaps:
    def test_offsets_do_not_overlap(self):
        for name, component in load_components().items():
            used = {}
            for field_key, field in component["fields"].items():
                if (offset := field.get("offset")) is None:
                    continue
                count = field.get("count") or (
                    2 if field["data_type"] in ("float", "uint32") else 1
                )
                for position in range(offset, offset + count):
                    assert position not in used, (
                        f"{name}: {field_key} overlaps {used.get(position)} at {position}"
                    )
                    used[position] = field_key

    def test_fields_stay_inside_their_stride(self):
        for name, component in load_components().items():
            stride = component.get("stride")
            if not stride:
                continue
            for field_key, field in component["fields"].items():
                if (offset := field.get("offset")) is None:
                    continue
                count = field.get("count") or (
                    2 if field["data_type"] in ("float", "uint32") else 1
                )
                assert offset + count <= stride, f"{name}.{field_key} exceeds stride"


class TestNettedSensors:
    """The netted grid sensors compensate for Shelly's per-phase energy counters."""

    def test_grid_profiles_get_netted_sensors(self):
        keys = definitions_by_key("SPEM-003CEBEU", "triphase")
        assert "grid_import_power" in keys
        assert "grid_export_power" in keys

    def test_source_is_the_signed_total_power(self):
        keys = definitions_by_key("SPEM-003CEBEU", "triphase")
        assert keys["grid_import_power"]["sources"] == ["em_0_total_act_power"]

    def test_monophase_sums_every_channel(self):
        keys = definitions_by_key("SPEM-003CEBEU", "monophase")
        assert keys["grid_export_power"]["sources"] == [
            "em1_0_act_power",
            "em1_1_act_power",
            "em1_2_act_power",
        ]

    def test_not_added_where_channels_meter_unrelated_circuits(self):
        """Pro EM 50 meters two independent circuits — summing them is meaningless."""
        for model in ("SPEM-002CEBEU50", "S3EM-002CXCEU", "S4SW-002P16EU"):
            keys = definitions_by_key(model)
            assert "grid_import_power" not in keys, model

    def test_netted_sensors_are_not_read_over_modbus(self):
        definitions = expand_definitions("SPEM-003CEBEU", "triphase")
        planned = {d["key"] for block in build_blocks(definitions) for d in block}
        assert "grid_import_power" not in planned
        assert "grid_export_power" not in planned

    def test_derived_definitions_carry_no_address(self):
        for d in expand_definitions("SPEM-003CEBEU", "triphase"):
            if d.get("access") == "derived":
                assert "address" not in d

    def test_they_are_power_sensors(self):
        keys = definitions_by_key("SPEM-003CEBEU", "triphase")
        for key in ("grid_import_power", "grid_export_power"):
            d = keys[key]
            assert d["unit"] == "W"
            assert d["device_class"] == "power"
            assert d["state_class"] == "measurement"
            assert d["enabled_by_default"] is True


class TestNettingMath:
    """Reproduces the coordinator's split of signed power into import/export."""

    @staticmethod
    def split(total):
        return max(total, 0.0), max(-total, 0.0)

    def test_pure_import(self):
        assert self.split(900.0) == (900.0, 0.0)

    def test_pure_export(self):
        assert self.split(-900.0) == (0.0, 900.0)

    def test_the_case_shelly_gets_wrong(self):
        """-600 W on one phase against +600 W on the others nets to zero.

        Shelly's own counters would record 600 Wh of export *and* 600 Wh of
        import at the same time; a netting meter records neither.
        """
        phases = [-600.0, 50.0, 550.0]
        import_w, export_w = self.split(sum(phases))
        assert import_w == 0.0
        assert export_w == 0.0

    def test_import_minus_export_is_always_the_signed_total(self):
        for total in (-1234.5, -1.0, 0.0, 0.5, 4321.0):
            i, e = self.split(total)
            assert i - e == pytest.approx(total)
