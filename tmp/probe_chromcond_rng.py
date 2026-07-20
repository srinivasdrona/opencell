import json

from opencell.vivarium.karr_chromosome_condensation import (
    KarrChromosomeCondensationProcess,
)


class LoggingRng:
    def __init__(self, values):
        self._values = iter(values)
        self.calls = []

    def random(self):
        value = float(next(self._values))
        self.calls.append({"method": "random", "value": value})
        return value


def main():
    proc = object.__new__(KarrChromosomeCondensationProcess)
    proc._rng = LoggingRng([0.2, 0.6, 0.8, 0.1])
    proc._smc_bindable_span = 4
    proc._smc_exclusion_offset = 1
    proc._smc_exclusion_len = 6

    positions, strands = KarrChromosomeCondensationProcess._sample_binding_positions(
        proc,
        intervals_by_strand={
            0: [(0, 9)],
            1: [(20, 29)],
        },
        n_to_bind=2,
        sequence_len=40,
    )

    print(
        json.dumps(
            {
                "rng_calls": proc._rng.calls,
                "positions": positions,
                "strands": strands,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
