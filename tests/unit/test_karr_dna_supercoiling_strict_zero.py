from __future__ import annotations

from typing import Any

from opencell.vivarium.karr_dna_supercoiling import KarrDNASupercoilingProcess


class _GuardedSubstrates(dict[str, float]):
    def __init__(self, values: dict[str, float], blocked_wid: str) -> None:
        super().__init__(values)
        self._blocked_wid = blocked_wid

    def get(self, key: str, default: Any = None) -> Any:
        if key == self._blocked_wid:
            raise AssertionError(f"strict-zero violation: global substrate read for {key}")
        return super().get(key, default)


def test_karr_dna_supercoiling_strict_zero_no_global_fallback() -> None:
    process = KarrDNASupercoilingProcess(
        {
            "rng_seed": 3,
            "gyrase_activity_rate": 4.0,
            "topoiv_activity_rate": 0.05,
            "reference_gyrase_count": 1.0,
            "reference_topoiv_count": 1.0,
            "chromosome_length_bp": 10_500.0,
        }
    )

    substrate_values = {wid: 0.0 for wid in process.substrate_wids}
    substrate_values[process.atp_wid] = 10_000.0
    guarded_substrates = _GuardedSubstrates(substrate_values, process.atp_wid)

    state = {
        "chromosome": process.build_default_chromosome_state(sigma=-0.01, replication_state="idle"),
        "protein": {
            "counts": {
                process.gyrase_wid: 20.0,
                process.topoiv_wid: 1.0,
            }
        },
        "complex": {"counts": {wid: 0.0 for wid in process.complex_enzyme_wids}},
        "substrates": guarded_substrates,
        "requests": {process.name: {process.atp_wid: 0.0}},
        "substrates_allocated": {process.name: {process.atp_wid: 0.0}},
    }

    update = process.next_update(1.0, state)

    assert abs(float(update.get("substrates", {}).get(process.atp_wid, 0.0))) <= 1.0e-12
