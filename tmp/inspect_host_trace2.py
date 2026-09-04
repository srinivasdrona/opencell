import h5py
import numpy as np

path = "data/m1_sources/karr_native/per_process_traces_v2_event_s000/HostInteraction_100ticks.mat"


def deref_scalar_cell(f, dataset):
    refs = dataset[()]
    out = []
    for ref in refs.ravel():
        val = f[ref][()]
        out.append(np.asarray(val).ravel()[0])
    return np.asarray(out)


with h5py.File(path, "r") as f:
    for name in (
        "isBacteriumAdherent",
        "isTLRActivated_1",
        "isTLRActivated_2",
        "isTLRActivated_3",
        "isNFkBActivated",
        "isInflammatoryResponseActivated",
    ):
        vals = deref_scalar_cell(f, f["states_after"][name])
        print(name, "n=", vals.size, "all True?", bool(np.all(vals != 0)), "first5=", vals[:5])
