import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opencell.vivarium.karr_host_interaction import KarrHostInteractionProcess

p = KarrHostInteractionProcess({})
print("terminal_organelle_wids", p.terminal_organelle_wids)
print("adhesin_wids", p.adhesin_wids)
print("tlr12_ligand_wids", p.tlr12_ligand_wids)
print("tlr26_ligand_wids", p.tlr26_ligand_wids)
print("antigen_wids", p.antigen_wids)

schema = p.ports_schema()
print("cell schema keys:", sorted(schema["cell"].keys()))

# Mirror the genuine seed-0 tick-1 enzyme counts observed via MATLAB canary:
counts = {
    "MG_075_MONOMER": 27.0,
    "MG_149_MONOMER": 11.0,
    "MG_191_MONOMER": 31.0,
    "MG_192_MONOMER": 31.0,
    "MG_200_MONOMER": 22.0,
    "MG_217_MONOMER": 17.0,
    "MG_218_MONOMER": 33.0,
    "MG_288_MONOMER": 0.0,
    "MG_309_MONOMER": 17.0,
    "MG_312_MONOMER": 26.0,
    "MG_317_MONOMER": 19.0,
    "MG_318_MONOMER": 24.0,
    "MG_386_MONOMER": 11.0,
    "MG_412_MONOMER": 28.0,
    "MG_410_411_412_PENTAMER": 17.0,
}
state = {"cell": {}, "protein": {"counts": counts}}
update = p.next_update(1.0, state)
print("update (all-nonzero, expect all True):", update)

# Zero out one terminal-organelle protein -> adherence (and everything
# downstream) must flip false.
counts_zeroed = dict(counts)
counts_zeroed["MG_218_MONOMER"] = 0.0
# Start from the all-True state (as applied after tick 1) so the flip is observable.
cell_state_true = {k: True for k in update["cell"]}
state2 = {"cell": cell_state_true, "protein": {"counts": counts_zeroed}}
update2 = p.next_update(1.0, state2)
print("update (MG_218=0, expect all fields flip to False):", update2)
