from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))

_HELPER_DIR = Path(__file__).resolve().parent
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))

import verify_multiseed_pilot as pilot  # noqa: E402
import _l2_2_design_a_runner_helpers as runner_helpers  # noqa: E402


def _pilot_files_present() -> bool:
    return all(
        pilot._trace_path(process, seed).exists()
        for process in pilot.PILOT_PROCESSES
        for seed in pilot.PILOT_SEEDS
    )


pytestmark = pytest.mark.skipif(
    not _pilot_files_present(),
    reason=(
        "L2.2 bounded multi-seed pilot traces are local-only extraction output "
        "(gitignored) and are not present on this machine; see "
        "docs/phase_f/l2_2_design_a/MULTISEED_PILOT_REPORT.md to regenerate."
    ),
)


@pytest.mark.parametrize("process", pilot.PILOT_PROCESSES)
@pytest.mark.parametrize("seed", pilot.PILOT_SEEDS)
def test_pilot_trace_is_structurally_valid(process: str, seed: int) -> None:
    path = pilot._trace_path(process, seed)
    validated = pilot._validate_trace_file(path)
    assert validated["metadata"]["process_name"] == process
    assert validated["metadata"]["rng_seed"] == seed
    assert int(validated["metadata"]["n_ticks"]) == 100
    assert "substrates" in validated["before_channels"]
    assert "substrates" in validated["after_channels"]


@pytest.mark.parametrize("process", pilot.PILOT_PROCESSES)
def test_pilot_seeds_are_non_vacuously_independent(process: str) -> None:
    """Seed 0 and seed 1 must NOT produce identical trajectories.

    If they did, the extractor's `seed` parameter would be a no-op and any
    downstream distributional (multi-seed) claim built on top of it would be
    vacuous.
    """
    channel = pilot.NONVACUOUS_CHANNEL[process]
    matrices = {}
    for seed in pilot.PILOT_SEEDS:
        validated = pilot._validate_trace_file(pilot._trace_path(process, seed))
        matrices[seed] = validated["_channel_matrices"][f"after/{channel}"]

    seed_a, seed_b = pilot.PILOT_SEEDS[0], pilot.PILOT_SEEDS[1]
    assert matrices[seed_a].shape == matrices[seed_b].shape
    assert not (matrices[seed_a] == matrices[seed_b]).all(), (
        f"{process}: seed {seed_a} and seed {seed_b} produced identical {channel!r} traces"
    )


def test_rna_decay_and_protein_decay_are_genuinely_multiseed_via_loader() -> None:
    """RNADecay/ProteinDecay have no specialized 50-seed ensemble (unlike
    Transcription/Translation), so the pilot's 2-seed data is exactly what
    the Design-A loader dispatches to. Before this pilot, both processes were
    legacy single-seed (`KARR_LEGACY_SINGLE_SEED_FALLBACK`, canonical_seed_count=1).
    """
    for process in ("RNADecay", "ProteinDecay"):
        oracle = runner_helpers.load_karr_oracle(process)
        assert oracle["canonical_seed_count"] == 2
        assert not oracle.get("warnings")


def test_transcription_pilot_data_does_not_disturb_specialized_ensemble() -> None:
    """Transcription already has a richer 50-seed specialized ensemble; the
    pilot's 2-seed v2 addition must not regress the loader's existing
    preference for the richer source.
    """
    oracle = runner_helpers.load_karr_oracle("Transcription")
    assert oracle["canonical_seed_count"] == 50
    assert "ensembles/transcription" in str(oracle["oracle_path"]).replace("\\", "/")
