# Compartment Layer Design (Projector)

## Goal

Define a projector that converts compartmented matrix observables from MATLAB traces
into the harness-friendly flat mapping shape without losing axis semantics.

This is a design document only; no implementation is included here.

## Projector Signature

```python
def project_compartmented_observable(
    *,
    observable_name: str,
    matrix: np.ndarray,
    wids: list[str],
    compartment_wids: list[str],
    substrate_axis: int,
    compartment_axis: int,
    strict: bool = True,
) -> dict[str, float]:
    """Return flat mapping keyed by '<wid>@<compartment_wid>'."""
```

## Contract

1. Input matrix shape must match schema `shape`.
2. `wids` length must match matrix extent on `substrate_axis`.
3. `compartment_wids` length must match matrix extent on `compartment_axis`.
4. Output key format is deterministic: `"{wid}@{compartment_wid}"`.
5. `strict=True` raises on shape/axis mismatch; `strict=False` emits diagnostics and partial projection.

## Axis Policy

The projector must never assume row=substrate, col=compartment.  
It must use schema-provided axis metadata:

- `substrate_axis`: where wid index lives
- `compartment_axis`: where compartment index lives

This is required because TOA is transposed relative to many other processes.

## Worked Example: TerminalOrganelleAssembly

Schema facts (from `data/schemas/per_process/terminal_organelle_assembly.toml`):

- `substrates.wids` = 8 protein IDs
- `substrates.shape` = `[2, 8]`
- `substrates.compartment_wids` = `["incorporated", "unincorporated"]`
- `extractor_diagnostics.axis_inference.substrate_axis` = `1`
- `extractor_diagnostics.axis_inference.compartment_axis` = `0`

Interpretation:

- Axis 1 indexes substrate wid
- Axis 0 indexes compartment state label

Projection on one tick matrix `M`:

- `M[0, j]` -> `"<wids[j]>@incorporated"`
- `M[1, j]` -> `"<wids[j]>@unincorporated"`

Example keys:

- `MG_191_MONOMER@incorporated`
- `MG_191_MONOMER@unincorporated`
- `MG_386_MONOMER@incorporated`
- `MG_386_MONOMER@unincorporated`

This preserves TOA’s observed `(2, 8)` orientation while producing a flat dict for harness APIs.

## Error Handling

Recommended failure modes:

1. `ShapeMismatchError`: matrix shape differs from schema shape.
2. `AxisCardinalityError`: wid or compartment length mismatch.
3. `AxisAmbiguityError`: schema missing axis metadata.

For non-strict mode, return:

- projected dict for valid indices
- side-channel diagnostics list of dropped/unknown coordinates

## Why This Layer Is Needed

Without an explicit projector, flat harness code can silently swap axes on
transposed processes (TOA class), producing biologically invalid routing.
The schema’s axis metadata is the correctness anchor for this conversion.
