"""Reproduce TerminalOrganelleAssembly init error."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests" / "vivarium"))

from opencell.vivarium.karr_terminal_organelle_assembly import KarrTerminalOrganelleAssemblyProcess
try:
    p = KarrTerminalOrganelleAssemblyProcess({"rng_seed": 0})
    print("OK")
except Exception as e:
    print(f"{type(e).__name__}: {e}")
