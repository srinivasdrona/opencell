import sys
from pathlib import Path
sys.path.insert(0, str(Path('tests/vivarium').resolve()))
sys.path.insert(0, str(Path('.').resolve()))
import h5py, numpy as np
from l2_replay_common import cell_vector

p = 'data/m1_sources/karr_native/per_process_traces_v2/ProteinDecay_100ticks.mat'
with h5py.File(p, 'r') as f:
    print('observables and per-tick mutation counts:')
    for obs in f['states_before'].keys():
        mutated_ticks = 0
        total_diff = 0
        for t in range(100):
            try:
                b = cell_vector(f, 'states_before', obs, t)
                a = cell_vector(f, 'states_after', obs, t)
                d = int((b != a).sum())
                if d > 0:
                    mutated_ticks += 1
                    total_diff += d
            except Exception:
                pass
        print(f'  {obs}: len={b.shape[0]}, mutated_in_{mutated_ticks}/100_ticks, total_index_diffs={total_diff}')

print('\n--- OC ProteinDecayLightProcess ---')
from opencell.vivarium.karr_protein_decay_light import ProteinDecayLightProcess
proc = ProteinDecayLightProcess({'rng_seed': 0})
for attr in dir(proc):
    if attr.startswith('_') or callable(getattr(proc, attr, None)):
        continue
    try:
        v = getattr(proc, attr)
        if hasattr(v, '__len__'):
            print(f'  {attr}: type={type(v).__name__}, len={len(v)}')
    except Exception:
        pass
