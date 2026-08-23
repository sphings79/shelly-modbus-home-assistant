"""Register files must be read once and cached.

Home Assistant flags file reads inside the event loop. The register YAML is
static, so it is cached after the first read and preloaded from an executor
during setup.
"""

from shelly_modbus import registers


class TestCaching:
    def test_components_are_cached(self):
        assert registers.load_components() is registers.load_components()

    def test_models_are_cached(self):
        assert registers.load_models() is registers.load_models()

    def test_preload_populates_both_caches(self):
        registers.load_components.cache_clear()
        registers.load_models.cache_clear()

        registers.preload()

        assert registers.load_components.cache_info().currsize == 1
        assert registers.load_models.cache_info().currsize == 1

    def test_repeated_expansion_does_not_reread(self):
        registers.load_components.cache_clear()
        registers.preload()
        before = registers.load_components.cache_info().misses

        for _ in range(5):
            registers.expand_definitions("SPEM-003CEBEU", "triphase")

        assert registers.load_components.cache_info().misses == before
