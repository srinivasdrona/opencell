from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

import pytest

# Ensure pytest imports from this worktree even if another editable install exists.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if "opencell" in sys.modules:
    loaded = Path(getattr(sys.modules["opencell"], "__file__", "")).resolve()
    if _REPO_ROOT not in loaded.parents:
        for mod_name in list(sys.modules):
            if mod_name == "opencell" or mod_name.startswith("opencell."):
                del sys.modules[mod_name]

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

from l2_2_replay_common_v2 import _COMPOSITION_ORDER_V2, run_integrated_replay_v2


@pytest.mark.parametrize("rng_seed", [0], ids=["rng_seed_0"])
def test_l25_host_interaction_plus_terminal_organelle_no_hints(rng_seed: int, tmp_path: Path) -> None:
    under_test = ["HostInteraction", "TerminalOrganelleAssembly"]
    pair_in_order = [name for name in _COMPOSITION_ORDER_V2 if name in set(under_test)]
    assert pair_in_order == under_test

    source_schema = _REPO_ROOT / "data/schemas/per_process/terminal_organelle_assembly.toml"
    with source_schema.open("rb") as handle:
        schema = tomllib.load(handle)
    component_wids = [str(wid) for wid in schema["state_groups"]["substrates"]]

    runtime_schema_path = tmp_path / "toa_runtime_schema.toml"
    runtime_schema_path.write_text(
        "\n".join(
            [
                "[substrates]",
                f"wids = {json.dumps(component_wids)}",
                'compartment_wids = ["incorporated", "unincorporated"]',
                "",
                "[extractor_diagnostics.axis_inference]",
                "substrate_axis = 1",
                "compartment_axis = 0",
                "",
            ]
        ),
        encoding="utf-8",
    )

    run_integrated_replay_v2(
        under_test_processes=under_test,
        rng_seed=rng_seed,
        disable_trace_hints=True,
        oracle_type_by_process={
            "HostInteraction": "bit_identity",
            "TerminalOrganelleAssembly": "bit_identity",
        },
        process_config_overrides={
            "TerminalOrganelleAssembly": {"schema_path": str(runtime_schema_path)},
        },
    )
