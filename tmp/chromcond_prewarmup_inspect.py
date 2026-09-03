from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.io import loadmat


def _unwrap_scalar(value: object) -> object:
    arr = np.asarray(value)
    if arr.size == 1:
        return arr.reshape(-1)[0]
    return value


def _scalar_text(value: object) -> str:
    arr = np.asarray(_unwrap_scalar(value))
    if arr.size == 0:
        return ""
    item = arr.reshape(-1)[0]
    if isinstance(item, str):
        return item
    if isinstance(item, bytes):
        return item.decode("utf-8")
    return str(item)


def _count_values(positions: object, values: object) -> dict[int, int]:
    pos_arr = np.asarray(positions).reshape(-1)
    if pos_arr.size == 0:
        return {}
    value_arr = np.asarray(values).reshape(-1).astype(int)
    uniq, counts = np.unique(value_arr, return_counts=True)
    return {int(value): int(count) for value, count in zip(uniq, counts, strict=False)}


def _field_nnz(field: object) -> int:
    positions = np.asarray(field.positions).reshape(-1)
    return int(positions.size)


def main() -> int:
    path = Path("tmp/chromcond_prewarmup_state.mat")
    mat = loadmat(path, squeeze_me=True, struct_as_record=False)
    artifact = mat["artifact"]
    meta = artifact.metadata
    proc = artifact.process
    chrom = artifact.chromosome

    print(f"path={path.resolve()}")
    print(f"target_process={_scalar_text(meta.target_process)}")
    print(f"target_wid={_scalar_text(meta.target_wholeCellModelID)}")
    print(f"seed={int(np.asarray(meta.seed).reshape(-1)[0])}")
    print(
        "target_init_order_slot_1based="
        f"{int(np.asarray(meta.target_init_order_slot_1based).reshape(-1)[0])}"
    )
    print(f"wcm_root={_scalar_text(meta.wcm_root)}")
    print(f"source_fixture_path={_scalar_text(meta.source_fixture_path)}")
    print(f"substrates={np.asarray(proc.substrates).reshape(-1).astype(int).tolist()}")
    print(f"enzymes={np.asarray(proc.enzymes).reshape(-1).astype(int).tolist()}")
    print(f"bound_enzymes={np.asarray(proc.boundEnzymes).reshape(-1).astype(int).tolist()}")
    print(f"rand_stream_type={_scalar_text(proc.randStreamType)}")
    print(f"rand_stream_seed={int(np.asarray(proc.randStreamSeed).reshape(-1)[0])}")
    print(f"rand_stream_state={int(np.asarray(proc.randStreamState).reshape(-1)[0])}")
    print(f"polymerized_regions_n={_field_nnz(chrom.polymerizedRegions)}")
    print(f"complex_bound_sites_n={_field_nnz(chrom.complexBoundSites)}")
    print(f"monomer_bound_sites_n={_field_nnz(chrom.monomerBoundSites)}")
    print(
        "complex_bound_value_counts="
        f"{_count_values(chrom.complexBoundSites.positions, chrom.complexBoundSites.values)}"
    )
    print(
        "monomer_bound_value_counts="
        f"{_count_values(chrom.monomerBoundSites.positions, chrom.monomerBoundSites.values)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
