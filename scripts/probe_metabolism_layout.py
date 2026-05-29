import sys
from pathlib import Path
sys.path.insert(0, str(Path('tests/vivarium').resolve()))
import h5py, numpy as np
from l2_replay_common import cell_vector

p = sys.argv[1]
with h5py.File(p, 'r') as f:
    print('top-level keys:', list(f.keys()))
    for grp in ('metadata', 'states_before', 'states_after'):
        if grp in f:
            print(f'  {grp} keys:', list(f[grp].keys()))
    # Print raw shape of substrates dataset
    for grp in ('states_before',):
        d = f[f'{grp}/substrates']
        print(f'{grp}/substrates dataset shape: {d.shape}, dtype: {d.dtype}')
    # cell_vector at t=0
    v0 = cell_vector(f, 'states_before', 'substrates', 0)
    print(f'cell_vector substrates t=0 shape: {v0.shape}, sum={float(v0.sum()):.0f}, nonzero={int((v0!=0).sum())}')
    print(f'  first 20: {v0[:20].tolist()}')
    print(f'  idx 583..587: {v0[583:588].tolist()}')
    print(f'  idx 1168..1172: {v0[1168:1173].tolist()}')
    # Check if reshape (585, 3) F-order or (3, 585) F-order makes idx=10 zero/nonzero
    for shape in [(585, 3), (3, 585)]:
        for order in ('F', 'C'):
            try:
                m = v0.reshape(shape, order=order)
                col0 = m[:, 0] if shape == (585, 3) else m[0, :]
                row0 = m[0, :] if shape == (585, 3) else m[:, 0]
                print(f'  reshape {shape} order={order}: col0[10]={col0[10] if len(col0)>10 else "n/a"}, row0[10]={row0[10] if len(row0)>10 else "n/a"}, col0 sum={col0.sum():.0f}')
            except Exception as e:
                print(f'  reshape {shape} order={order}: ERR {e}')
