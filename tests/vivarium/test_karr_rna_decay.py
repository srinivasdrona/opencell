from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
from scipy.io import savemat

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from opencell.vivarium.karr_rna_decay import RnaDecayLightProcess


def _write_fixture(
    path: Path,
    *,
    rna_ids: list[str],
    half_lives_s: list[float],
    substrate_ids: list[str],
    decay_reactions: np.ndarray,
    substrate_index_water_1based: int,
) -> Path:
    rna_state = {
        "x_class_": "edu.stanford.covert.cell.sim.state.Rna",
        "wholeCellModelIDs": np.asarray(rna_ids, dtype=object),
        "halfLives": np.asarray(half_lives_s, dtype=np.float64),
    }
    fixture = {
        "states": np.asarray([rna_state], dtype=object),
        "substrateWholeCellModelIDs": np.asarray(substrate_ids, dtype=object),
        "substrateIndexs_water": np.int64(substrate_index_water_1based),
        "decayReactions": np.asarray(decay_reactions, dtype=np.int64),
    }
    savemat(path, {"data": {"fixture": fixture}})
    return path


def _make_process(tmp_path: Path) -> RnaDecayLightProcess:
    fixture_path = _write_fixture(
        tmp_path / "RnaDecay_flat.mat",
        rna_ids=["RNA_A", "RNA_B"],
        half_lives_s=[0.1, 1.0e9],
        substrate_ids=["H2O", "AMP", "CMP"],
        decay_reactions=np.asarray(
            [
                [-2, 1, 1],  # RNA_A decay consumes 2 H2O, produces AMP+CMP.
                [-2, 1, 1],  # RNA_B same H2O ratio (used by mass-balance test).
            ],
            dtype=np.int64,
        ),
        substrate_index_water_1based=1,
    )
    return RnaDecayLightProcess(
        {
            "fixture_path": str(fixture_path),
            "rng_seed": 0,
        }
    )


def test_ports_schema_declares_accumulate_on_rna_and_substrates(tmp_path: Path) -> None:
    process = _make_process(tmp_path)
    schema = process.ports_schema()

    assert schema["rna"]["counts"]["RNA_A"]["_updater"] == "accumulate"
    assert schema["rna"]["counts"]["RNA_B"]["_updater"] == "accumulate"
    assert schema["substrates"]["H2O"]["_updater"] == "accumulate"
    assert schema["substrates"]["AMP"]["_updater"] == "accumulate"


def test_one_tick_reduces_selected_rna_count(tmp_path: Path) -> None:
    process = _make_process(tmp_path)

    update = process.next_update(
        1.0,
        {
            "rna": {"counts": {"RNA_A": 10.0, "RNA_B": 0.0}},
            "substrates_allocated": {"karr_rna_decay": {"H2O": 1000.0}},
        },
    )

    assert update["requests"]["karr_rna_decay"]["H2O"] > 0.0
    assert update["rna"]["counts"]["RNA_A"] < 0.0
    assert update["substrates"]["H2O"] < 0.0


def test_allocation_limited_zero_h2o_allocation_gives_zero_decay(tmp_path: Path) -> None:
    process = _make_process(tmp_path)

    update = process.next_update(
        1.0,
        {
            "rna": {"counts": {"RNA_A": 20.0, "RNA_B": 0.0}},
            "substrates_allocated": {"karr_rna_decay": {"H2O": 0.0}},
        },
    )

    assert update["requests"]["karr_rna_decay"]["H2O"] > 0.0
    assert "rna" not in update
    assert "substrates" not in update


def test_mass_balance_h2o_matches_decay_ratio_from_fixture(tmp_path: Path) -> None:
    process = _make_process(tmp_path)

    update = process.next_update(
        1.0,
        {
            "rna": {"counts": {"RNA_A": 5.0, "RNA_B": 3.0}},
            "substrates_allocated": {"karr_rna_decay": {"H2O": 10_000.0}},
        },
    )

    total_rna_decayed = -sum(update["rna"]["counts"].values())
    h2o_consumed = -update["substrates"]["H2O"]

    assert total_rna_decayed > 0.0
    assert h2o_consumed == 2.0 * total_rna_decayed
