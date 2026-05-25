from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for module_name in list(sys.modules):
            if module_name == "opencell" or module_name.startswith("opencell."):
                del sys.modules[module_name]

if not hasattr(np, "cumproduct"):
    np.cumproduct = np.cumprod

_VIVARIUM_PKG = _REPO_ROOT / "opencell" / "vivarium"
if "opencell.vivarium" not in sys.modules and _VIVARIUM_PKG.exists():
    vivarium_module = types.ModuleType("opencell.vivarium")
    vivarium_module.__path__ = [str(_VIVARIUM_PKG)]
    sys.modules["opencell.vivarium"] = vivarium_module

try:
    import pint

    if "pint.quantity" not in sys.modules and hasattr(pint, "Quantity"):
        quantity_module = types.ModuleType("pint.quantity")
        quantity_module._Quantity = pint.Quantity
        sys.modules["pint.quantity"] = quantity_module
    if "pint.unit" not in sys.modules and hasattr(pint, "Unit"):
        unit_module = types.ModuleType("pint.unit")
        unit_module.Unit = pint.Unit
        sys.modules["pint.unit"] = unit_module
except Exception:
    pass

try:
    from vivarium.core.process import Process as _VivariumProcess  # noqa: F401
except Exception:
    vivarium_module = types.ModuleType("vivarium")
    core_module = types.ModuleType("vivarium.core")
    process_module = types.ModuleType("vivarium.core.process")

    class Process:  # type: ignore[override]
        defaults: dict[str, object] = {}
        name = "process"

        def __init__(self, parameters: dict[str, object] | None = None) -> None:
            merged = dict(getattr(type(self), "defaults", {}))
            if parameters:
                merged.update(parameters)
            self.parameters = merged
            self.name = str(getattr(type(self), "name", self.__class__.__name__))

        def ports_schema(self) -> dict[str, object]:
            return {}

        def next_update(self, timestep: float, states: dict[str, object]) -> dict[str, object]:
            del timestep, states
            return {}

    process_module.Process = Process
    core_module.process = process_module
    vivarium_module.core = core_module
    vivarium_module.__path__ = []
    core_module.__path__ = []
    sys.modules["vivarium"] = vivarium_module
    sys.modules["vivarium.core"] = core_module
    sys.modules["vivarium.core.process"] = process_module
