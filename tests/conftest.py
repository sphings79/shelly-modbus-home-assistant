"""Make the integration importable without installing Home Assistant."""

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "custom_components"

if "shelly_modbus" not in sys.modules:
    sys.path.insert(0, str(ROOT))
    package = types.ModuleType("shelly_modbus")
    package.__path__ = [str(ROOT / "shelly_modbus")]
    sys.modules["shelly_modbus"] = package
