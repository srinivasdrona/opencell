import sys
from pathlib import Path
sys.path.insert(0, str(Path('tests/vivarium').resolve()))
import h5py, numpy as np
from l2_replay_common import cell_vector
p = sys.argv[1]
with h5py.File(p, 'r') as f:
    for obs in ('enzymes', 'boundEnzymes'):
        v0b = cell_vector(f, 'states_before', obs, 0)
        v0a = cell_vector(f, 'states_after', obs, 0)
        print(f'{obs} t=0 len={v0b.shape[0]} BEFORE head={v0b[:5].tolist()} sum={float(v0b.sum()):.0f}')
        print(f'{obs} t=0 len={v0a.shape[0]} AFTER  head={v0a[:5].tolist()} sum={float(v0a.sum()):.0f}')
        diff = v0a - v0b
        nz = int(np.count_nonzero(diff))
        print(f'{obs} t=0 nonzero_diffs={nz}')
