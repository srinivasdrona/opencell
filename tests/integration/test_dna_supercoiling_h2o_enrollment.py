from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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

from opencell.vivarium.karr_composite import build_karr_chassis_v6
from opencell.vivarium.karr_dna_supercoiling import KarrDNASupercoilingProcess


def _supercoil_state(
    process: KarrDNASupercoilingProcess,
    *,
    sigma: float,
    atp: float,
    h2o: float,
    gyrase: float,
    topoiv: float,
    topoi: float = 0.0,
) -> dict[str, Any]:
    protein_counts: dict[str, float] = {}
    complex_counts: dict[str, float] = {}
    for wid, count in (
        (process.gyrase_wid, gyrase),
        (process.topoiv_wid, topoiv),
        (process.topoi_wid, topoi),
    ):
        if process.enzyme_store_by_wid.get(wid) == "complex":
            complex_counts[wid] = float(count)
        else:
            protein_counts[wid] = float(count)

    substrates = {wid: 0.0 for wid in process.substrate_wids}
    substrates[process.atp_wid] = float(atp)
    substrates[process.h2o_wid] = float(h2o)
    substrates[process.adp_wid] = 0.0
    substrates[process.pi_wid] = 0.0
    return {
        "chromosome": process.build_default_chromosome_state(sigma=sigma, replication_state="idle"),
        "protein": {"counts": protein_counts},
        "complex": {"counts": complex_counts},
        "substrates": substrates,
        "requests": {process.name: {process.atp_wid: float(atp), process.h2o_wid: float(h2o)}},
        "substrates_allocated": {
            process.name: {
                process.atp_wid: float(atp),
                process.h2o_wid: float(h2o),
            }
        },
    }


def test_dna_supercoiling_request_vector_and_allocator_enroll_h2o() -> None:
    composite = build_karr_chassis_v6(time_step_s=1.0, emit_step_s=1.0)
    process = composite["processes"]["karr_dna_supercoiling"]
    allocator = composite["steps"]["karr_allocation_step"]

    proc_requests = process.ports_schema()["requests"][process.name]
    assert process.h2o_wid in proc_requests

    consumers = dict(allocator.parameters["consumer_processes"])
    assert process.h2o_wid in consumers[process.name]

    alloc_update = allocator.next_update(
        1.0,
        {
            "substrates": {process.atp_wid: 9.0, process.h2o_wid: 7.0},
            "requests": {
                process.name: {
                    process.atp_wid: 6.0,
                    process.h2o_wid: 5.0,
                }
            },
        },
    )
    assert alloc_update["substrates_allocated"][process.name][process.h2o_wid] == 5.0


def test_dna_supercoiling_consumes_h2o_with_atp() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "rng_seed": 7,
            "gyrase_activity_rate": 20.0,
            "topoiv_activity_rate": 20.0,
            "reference_gyrase_count": 1.0,
            "reference_topoiv_count": 1.0,
        }
    )
    state = _supercoil_state(
        process,
        sigma=-0.01,
        atp=5_000.0,
        h2o=5_000.0,
        gyrase=40.0,
        topoiv=40.0,
    )

    update = process.next_update(1.0, state)
    req = update["requests"][process.name]
    assert process.h2o_wid in req
    assert req[process.h2o_wid] == pytest.approx(req[process.atp_wid])

    substrate_delta = update["substrates"]
    assert substrate_delta[process.atp_wid] < 0.0
    assert substrate_delta[process.h2o_wid] < 0.0
    assert substrate_delta[process.h2o_wid] == pytest.approx(substrate_delta[process.atp_wid])
