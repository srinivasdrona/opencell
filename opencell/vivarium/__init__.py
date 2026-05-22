"""Vivarium-core adapters for OpenCell solvers and models.

This subpackage is *additive* — it wraps existing ``opencell/models`` and
``opencell/solvers`` as Vivarium ``Process`` subclasses with explicit
ports, but the underlying biology and numerics are unchanged. Standalone
use of the wrapped modules (without Vivarium) remains a first-class entry
point; this package exists so the same code can be composed inside the
Vivarium-core orchestrator and (eventually) future bigraph engines.

Design rules (Phase 4 / A1):

* One Process == one numerical sub-system (metabolism, gene network,
  signal derivation). We do **not** ship a single mega-process; the
  whole point of this layer is to expose coupling to the engine.
* Coupling state ``f_met`` is a first-class Vivarium store, not an
  internal field. This makes the bidirectional-coupling refactor (M0)
  a topology change rather than a code change.
* Updates use the ``set`` updater for deterministic ODE state and
  the ``accumulate`` updater for stochastic count deltas — see
  ``data/semantics/A6_semantics_contract.md`` for the formal rule.
* RNG remains a single ``np.random.Generator`` per realisation,
  threaded through Process construction. Vivarium's parameter dict
  carries the ``rng`` reference; we never touch numpy global state.
"""

from opencell.vivarium.composite import build_coupled_engine
from opencell.vivarium.karr_composite import (
    build_karr_m1_m2_engine,
    build_karr_m1_m2_m3_engine,
)
from opencell.vivarium.karr_m1 import (
    KarrMetabolismProcess,
    build_karr_m1_engine,
)
from opencell.vivarium.karr_m2 import (
    KarrTranscriptionProcess,
    build_karr_m2_engine,
)
from opencell.vivarium.karr_m3 import (
    KarrTranslationProcess,
    build_karr_m3_engine,
)
from opencell.vivarium.persist import PersistentMetabolismProcess
from opencell.vivarium.processes import (
    GeneNetworkProcess,
    MetabolismProcess,
    SignalProcess,
)

__all__ = [
    "GeneNetworkProcess",
    "MetabolismProcess",
    "PersistentMetabolismProcess",
    "SignalProcess",
    "build_coupled_engine",
    "KarrMetabolismProcess",
    "build_karr_m1_engine",
    "KarrTranscriptionProcess",
    "build_karr_m2_engine",
    "KarrTranslationProcess",
    "build_karr_m3_engine",
    "build_karr_m1_m2_engine",
    "build_karr_m1_m2_m3_engine",
]
