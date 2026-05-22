"""Probe 4: empirical Vivarium merge semantics for same-leaf writers.

This probe intentionally writes to the same leaf from multiple Processes
within one tick to characterize how vivarium-core 1.6.5 merges updates.
"""

from __future__ import annotations

from collections.abc import Sequence

from vivarium.core.composer import Composer
from vivarium.core.engine import Engine
from vivarium.core.process import Process


class WriterProcess(Process):
    """Write one configured value to one configured store leaf."""

    defaults = {
        "port_name": "protein",
        "wid": "X",
        "value": 0,
        "updater": "set",
        "time_step": 1.0,
    }

    def ports_schema(self):
        return {
            self.parameters["port_name"]: {
                "counts": {
                    self.parameters["wid"]: {
                        "_default": 100,
                        "_updater": self.parameters["updater"],
                        "_emit": True,
                    }
                }
            }
        }

    def next_update(self, timestep, states):
        return {
            self.parameters["port_name"]: {
                "counts": {self.parameters["wid"]: self.parameters["value"]}
            }
        }


class WriterComposer(Composer):
    """Generate N writer processes all wired to the same `protein` store."""

    defaults = {"writers": {}}

    def generate_processes(self, config):
        return {
            name: WriterProcess(writer_config)
            for name, writer_config in config["writers"].items()
        }

    def generate_topology(self, config):
        return {
            name: {"protein": ("protein",)}
            for name in config["writers"].keys()
        }


def run_single_tick(writers: Sequence[tuple[str, dict]]) -> int:
    """Run exactly one tick and return final `protein.counts.X`."""
    composer = WriterComposer({"writers": dict(writers)})
    composite = composer.generate()
    engine = Engine(
        processes=composite["processes"],
        topology=composite["topology"],
        emit_step=1.0,
        display_info=False,
    )
    engine.update(1.0)
    return int(engine.emitter.get_timeseries()["protein"]["counts"]["X"][-1])


def test_set_plus_accumulate_three_way_merge():
    # Observed behavior (vivarium-core 1.6.5):
    # Schema conflict warns but does not raise. The later schema assignment
    # for `_updater` wins for this leaf, and updates are then applied in
    # process registration order under that resolved updater.
    final_value = run_single_tick(
        [
            ("ProcessA", {"value": 80, "updater": "set"}),
            ("ProcessB", {"value": -10, "updater": "accumulate"}),
            ("ProcessC", {"value": 5, "updater": "accumulate"}),
        ]
    )
    print(f"three_way_merge final protein.counts.X = {final_value}")
    assert final_value == 175


def test_process_registration_order_matters():
    # Observed behavior (vivarium-core 1.6.5):
    # Reversing process registration changes the result, so order matters.
    baseline = run_single_tick(
        [
            ("ProcessA", {"value": 80, "updater": "set"}),
            ("ProcessB", {"value": -10, "updater": "accumulate"}),
            ("ProcessC", {"value": 5, "updater": "accumulate"}),
        ]
    )
    reversed_order = run_single_tick(
        [
            ("ProcessC", {"value": 5, "updater": "accumulate"}),
            ("ProcessB", {"value": -10, "updater": "accumulate"}),
            ("ProcessA", {"value": 80, "updater": "set"}),
        ]
    )
    print(f"registration_order baseline={baseline}, reversed={reversed_order}")
    assert baseline == 175
    assert reversed_order == 80
    assert reversed_order != baseline


def test_set_only_two_writers():
    # Observed behavior (vivarium-core 1.6.5):
    # With two `set` writers on the same leaf in one tick, the later writer
    # in registration order wins.
    final_value = run_single_tick(
        [
            ("ProcessA", {"value": 80, "updater": "set"}),
            ("ProcessB", {"value": 70, "updater": "set"}),
        ]
    )
    print(f"set_only_two_writers final protein.counts.X = {final_value}")
    assert final_value == 70


def test_accumulate_only_two_writers():
    # Observed behavior (vivarium-core 1.6.5):
    # Pure `accumulate` merges are additive from the shared initial state.
    final_value = run_single_tick(
        [
            ("ProcessB", {"value": -10, "updater": "accumulate"}),
            ("ProcessC", {"value": 5, "updater": "accumulate"}),
        ]
    )
    print(f"accumulate_only_two_writers final protein.counts.X = {final_value}")
    assert final_value == 95


def test_set_zero_plus_negative_accumulate():
    # Observed behavior (vivarium-core 1.6.5):
    # In this registration order, resolved updater semantics yield 90,
    # not -10, so `set: 0` does not behave like a hard reset followed by
    # accumulate on the same leaf under mixed updater declarations.
    final_value = run_single_tick(
        [
            ("ProcessA", {"value": 0, "updater": "set"}),
            ("ProcessB", {"value": -10, "updater": "accumulate"}),
        ]
    )
    print(f"set_zero_plus_negative_accumulate final protein.counts.X = {final_value}")
    assert final_value == 90
