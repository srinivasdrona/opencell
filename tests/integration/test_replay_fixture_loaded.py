from __future__ import annotations

from opencell.validation.replay import load_per_process_fixture


def _first_before_series_shape(process_name: str) -> tuple[int, ...]:
    fixture = load_per_process_fixture(process_name)
    assert fixture.n_ticks == 100
    assert fixture.inputs, "expected at least one resolved input channel"
    assert fixture.outputs, "expected at least one resolved output channel"

    assert "substrates" in fixture.inputs
    return fixture.inputs["substrates"].shape


def test_replay_fixture_loaded_cytokinesis() -> None:
    shape = _first_before_series_shape("Cytokinesis")
    assert shape[0] == 100


def test_replay_fixture_loaded_chromosome_condensation() -> None:
    shape = _first_before_series_shape("ChromosomeCondensation")
    assert shape[0] == 100


def test_replay_fixture_loaded_transcription() -> None:
    shape = _first_before_series_shape("Transcription")
    assert shape[0] == 100
