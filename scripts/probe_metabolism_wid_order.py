import sys
from pathlib import Path
sys.path.insert(0, str(Path('tests/vivarium').resolve()))
sys.path.insert(0, str(Path('.').resolve()))
import h5py, numpy as np
from l2_replay_common import cell_vector, build_state_template, project_karr_vector
from opencell.vivarium.karr_metabolism import KarrMetabolismProcess

process = KarrMetabolismProcess({'rng_seed': 0})
sw = list(process.substrate_wids)
print(f'OC substrate_wids count: {len(sw)}')
print(f'OC substrate_wids[:20] = {sw[:20]}')
print(f'OC substrate_wids[10] = {sw[10]!r}')

# Also check states_before at idx 10 in the full 1755 vs the proj=585
p = 'data/m1_sources/karr_native/per_process_traces_v2/Metabolism_100ticks.mat'
with h5py.File(p, 'r') as f:
    sb = cell_vector(f, 'states_before', 'substrates', 0)
    sa = cell_vector(f, 'states_after', 'substrates', 0)
    print(f'\nKarr raw substrates t=0 shape: {sb.shape}')
    print(f'  Karr states_before[10] = {sb[10]}')
    print(f'  Karr states_after [10] = {sa[10]}')
    # Find which indices are nonzero in first 585
    nz_before = [i for i in range(585) if sb[i] != 0]
    print(f'\nFirst 585 nonzero indices (BEFORE): count={len(nz_before)}')
    print(f'  {nz_before[:30]}')
    # What changed in first 585?
    diff = sa[:585] - sb[:585]
    changed = [(i, sb[i], sa[i]) for i in range(585) if sb[i] != sa[i]]
    print(f'\nFirst 585 changes (tick 0): count={len(changed)}')
    for i, b, a in changed[:20]:
        print(f'  idx={i:3d} wid={sw[i] if i < len(sw) else "?"!r:20s} before={b} after={a} delta={a-b}')
