import sys
from pathlib import Path
sys.path.insert(0, str(Path('tests/vivarium').resolve()))
sys.path.insert(0, str(Path('.').resolve()))
import h5py, numpy as np
from l2_replay_common import cell_vector, build_state_template, infer_wids_for_observable
from opencell.vivarium.karr_metabolism import KarrMetabolismProcess

process = KarrMetabolismProcess({'rng_seed': 0})
state_template = build_state_template(process)

# What's in the state template's substrate store?
def show_keys(d, path=()):
    if isinstance(d, dict):
        if not d:
            print('  ' + '.'.join(path) + ' = {} (empty)')
        else:
            sample = list(d.keys())[:5]
            print(f'  {".".join(path)}: {len(d)} keys, sample={sample}')
            for k, v in list(d.items())[:1]:
                if isinstance(v, dict):
                    show_keys(v, path + (k,))

print('state_template top:')
for k in state_template:
    print(f'  {k}:', type(state_template[k]).__name__, len(state_template[k]) if hasattr(state_template[k], '__len__') else '?')
for k in state_template:
    if isinstance(state_template[k], dict):
        show_keys(state_template[k], (k,))

print('\n--- inferring wids ---')
wids = infer_wids_for_observable(process, state_template, 'substrates', karr_len=585, explicit_attr='substrate_wids')
print(f'inferred wids for substrates (karr_len=585): count={len(wids)}, head={wids[:20]}')
print(f'  wids[10] = {wids[10]!r}')
