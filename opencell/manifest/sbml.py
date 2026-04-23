"""SBML walker + unit resolver.

Uses ElementTree only (no libsbml dependency).  Handles SBML L2 v3/v4
patterns observed in BioModels curated set.  For more exotic SBML
(events, function definitions, MathML expressions) we extract what we
can and tag the rest as `unresolved`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable
from xml.etree import ElementTree as ET


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SbmlUnit:
    """One <unit> inside a <unitDefinition>."""

    kind: str            # "mole", "litre", "second", ...
    exponent: int = 1
    scale: int = 0
    multiplier: float = 1.0


@dataclass
class SbmlUnitDefinition:
    """A named <unitDefinition>; e.g. id='substance_per_volume_per_time'."""

    id: str
    units: list[SbmlUnit] = field(default_factory=list)


@dataclass
class SbmlEntity:
    """A parameter or species with a value, unit reference, and origin."""

    sbml_id: str
    value: float | None
    units_ref: str            # the `units` attribute as written in the SBML
    units_resolved: str       # human-readable string after lookup
    kind: str                 # "global_parameter" | "local_parameter" | "species_initial"
    parent_reaction: str = "" # for local_parameter: the enclosing reaction id
    name: str = ""            # SBML <... name="..."> if present
    compartment: str = ""     # for species
    notes: str = ""           # short SBML <notes> excerpt if extractable


@dataclass
class SbmlModelMetadata:
    """Annotations harvested from <model><annotation><rdf:RDF>...</rdf:RDF>.

    All fields are best-effort; absence is normal. Useful for auto-filling
    a manifest header without forcing the user to retype known facts.
    """

    model_id: str = ""              # <model id="...">
    model_name: str = ""            # <model name="...">
    biomodels_id: str = ""          # extracted from identifiers.org/biomodels.db/
    pubmed_id: str = ""             # from identifiers.org/pubmed/
    doi: str = ""                   # from identifiers.org/doi/  (often absent)
    taxonomy_id: str = ""           # from identifiers.org/taxonomy/
    organism: str = ""              # mapped from taxonomy_id when known
    creators: list[str] = field(default_factory=list)
    notes_excerpt: str = ""         # first ~280 chars of <notes>


# NCBI taxonomy id -> human-readable organism name. Small static table for
# the most common BioModels organisms; extend as needed.
_TAXONOMY_NAMES = {
    "562": "Escherichia coli",
    "511145": "Escherichia coli K-12 MG1655",
    "83333": "Escherichia coli K-12",
    "4932": "Saccharomyces cerevisiae",
    "559292": "Saccharomyces cerevisiae S288C",
    "9606": "Homo sapiens",
    "10090": "Mus musculus",
    "10116": "Rattus norvegicus",
    "7227": "Drosophila melanogaster",
    "6239": "Caenorhabditis elegans",
    "3702": "Arabidopsis thaliana",
    "1773": "Mycobacterium tuberculosis",
    "2097": "Mycoplasma genitalium",
}



# ---------------------------------------------------------------------------
# Namespace handling
# ---------------------------------------------------------------------------

def _localname(tag: str) -> str:
    """Return tag without namespace prefix."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _findall_local(parent: ET.Element, name: str) -> list[ET.Element]:
    return [e for e in parent.iter() if _localname(e.tag) == name and e is not parent]


def _direct_children_local(parent: ET.Element, name: str) -> list[ET.Element]:
    return [e for e in list(parent) if _localname(e.tag) == name]


# ---------------------------------------------------------------------------
# Unit resolution
# ---------------------------------------------------------------------------

# SBML built-in unit kinds (subset most relevant for biology)
_SI_PREFIX = {
    -24: "y", -21: "z", -18: "a", -15: "f", -12: "p",
    -9: "n", -6: "u", -3: "m", -2: "c", -1: "d",
    0: "", 1: "da", 2: "h", 3: "k", 6: "M", 9: "G",
}

# Map SBML kind names to short symbols
_KIND_SYMBOL = {
    "mole": "mol", "litre": "L", "liter": "L", "second": "s",
    "metre": "m", "meter": "m", "kilogram": "kg", "gram": "g",
    "ampere": "A", "kelvin": "K", "candela": "cd",
    "becquerel": "Bq", "coulomb": "C", "farad": "F", "henry": "H",
    "hertz": "Hz", "joule": "J", "katal": "kat", "lumen": "lm",
    "lux": "lx", "newton": "N", "ohm": "Ohm", "pascal": "Pa",
    "radian": "rad", "siemens": "S", "sievert": "Sv", "steradian": "sr",
    "tesla": "T", "volt": "V", "watt": "W", "weber": "Wb",
    "dimensionless": "1", "item": "item", "avogadro": "avogadro",
}


def _format_unit_token(unit: SbmlUnit) -> str:
    """Format a single SbmlUnit as a string fragment, e.g. 'mmol' or 's^-1'."""
    sym = _KIND_SYMBOL.get(unit.kind, unit.kind)
    prefix = _SI_PREFIX.get(unit.scale, f"10^{unit.scale}*" if unit.scale != 0 else "")
    base = f"{prefix}{sym}" if sym != "1" else "1"
    if unit.exponent == 1:
        return base
    return f"{base}^{unit.exponent}"


def stringify_unit(definition: SbmlUnitDefinition) -> str:
    """Produce a compact human-readable string for a unit definition.

    Convention: numerator units joined by '*', denominator (negative
    exponents) gathered into a single '/( ... )' group when there are 2+;
    a single negative-exponent unit becomes 'X/Y' with positive exponent.
    """
    if not definition.units:
        return definition.id  # fallback to the SBML id
    pos = [u for u in definition.units if u.exponent > 0]
    neg = [u for u in definition.units if u.exponent < 0]
    if not pos and not neg:
        return definition.id

    def _flip_sign(u: SbmlUnit) -> SbmlUnit:
        return SbmlUnit(kind=u.kind, exponent=-u.exponent, scale=u.scale, multiplier=u.multiplier)

    num = "*".join(_format_unit_token(u) for u in pos) if pos else "1"
    if not neg:
        return num
    if len(neg) == 1:
        return f"{num}/{_format_unit_token(_flip_sign(neg[0]))}"
    den = "*".join(_format_unit_token(_flip_sign(u)) for u in neg)
    return f"{num}/({den})"


def resolve_unit(units_ref: str, definitions: dict[str, SbmlUnitDefinition]) -> str:
    """Resolve an SBML units reference to a human-readable string.

    Tries (in order):
      1. lookup in user-defined <unitDefinition> by id
      2. SBML built-in kind (e.g. 'mole', 'second') → short symbol
      3. fall back to the raw reference string
    """
    if not units_ref:
        return ""
    if units_ref in definitions:
        return stringify_unit(definitions[units_ref])
    if units_ref in _KIND_SYMBOL:
        return _KIND_SYMBOL[units_ref]
    return units_ref


# ---------------------------------------------------------------------------
# Walker
# ---------------------------------------------------------------------------

def _parse_unit_element(elem: ET.Element) -> SbmlUnit:
    return SbmlUnit(
        kind=elem.attrib.get("kind", ""),
        exponent=int(elem.attrib.get("exponent", "1")),
        scale=int(elem.attrib.get("scale", "0")),
        multiplier=float(elem.attrib.get("multiplier", "1")),
    )


def _parse_unit_definitions(root: ET.Element) -> dict[str, SbmlUnitDefinition]:
    out: dict[str, SbmlUnitDefinition] = {}
    for ud in root.iter():
        if _localname(ud.tag) != "unitDefinition":
            continue
        uid = ud.attrib.get("id", "")
        units = [_parse_unit_element(u) for u in ud.iter() if _localname(u.tag) == "unit" and u is not ud]
        out[uid] = SbmlUnitDefinition(id=uid, units=units)
    return out


def _to_float(s: str | None) -> float | None:
    if s is None or s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_sbml(sbml_bytes: bytes, *, include_species: bool = True) -> tuple[list[SbmlEntity], dict[str, SbmlUnitDefinition]]:
    """Parse an SBML byte-string and return (entities, unit_definitions).

    Entities include global parameters, local kinetic-law parameters, and
    (optionally) species initial concentrations.
    """
    root = ET.fromstring(sbml_bytes)
    udefs = _parse_unit_definitions(root)

    entities: list[SbmlEntity] = []

    # 1) global parameters: in <listOfParameters> at model level
    for elem in root.iter():
        if _localname(elem.tag) != "parameter":
            continue
        # Decide if this is global or local
        # Walk up — but ET doesn't have parent links by default; use a heuristic
        # via attribute: globals are always direct children of model->listOfParameters,
        # locals are inside kineticLaw->listOfParameters.  We'll detect by ancestry below.
        pass  # handled in two passes

    # Build a parent map once (cheap for typical SBML sizes)
    parent_map = {child: parent for parent in root.iter() for child in parent}

    def _ancestor_local(e: ET.Element, name: str) -> ET.Element | None:
        cur = parent_map.get(e)
        while cur is not None:
            if _localname(cur.tag) == name:
                return cur
            cur = parent_map.get(cur)
        return None

    for elem in root.iter():
        if _localname(elem.tag) != "parameter":
            continue
        sbml_id = elem.attrib.get("id", "") or elem.attrib.get("name", "")
        value = _to_float(elem.attrib.get("value"))
        units_ref = elem.attrib.get("units", "")
        name = elem.attrib.get("name", "")
        kinlaw = _ancestor_local(elem, "kineticLaw")
        if kinlaw is not None:
            reaction = _ancestor_local(elem, "reaction")
            rxn_id = reaction.attrib.get("id", "") if reaction is not None else ""
            kind = "local_parameter"
            entities.append(SbmlEntity(
                sbml_id=sbml_id, value=value,
                units_ref=units_ref,
                units_resolved=resolve_unit(units_ref, udefs),
                kind=kind, parent_reaction=rxn_id, name=name,
            ))
        else:
            entities.append(SbmlEntity(
                sbml_id=sbml_id, value=value,
                units_ref=units_ref,
                units_resolved=resolve_unit(units_ref, udefs),
                kind="global_parameter", name=name,
            ))

    # 2) species (optional)
    if include_species:
        for elem in root.iter():
            if _localname(elem.tag) != "species":
                continue
            sbml_id = elem.attrib.get("id", "") or elem.attrib.get("name", "")
            # Initial concentration / amount
            value = _to_float(elem.attrib.get("initialConcentration"))
            units_ref = elem.attrib.get("substanceUnits", "") or "substance"
            if value is None:
                value = _to_float(elem.attrib.get("initialAmount"))
            if value is None:
                continue  # nothing to record
            entities.append(SbmlEntity(
                sbml_id=sbml_id, value=value,
                units_ref=units_ref,
                units_resolved=resolve_unit(units_ref, udefs),
                kind="species_initial",
                compartment=elem.attrib.get("compartment", ""),
                name=elem.attrib.get("name", ""),
            ))

    return entities, udefs


# ---------------------------------------------------------------------------
# Model metadata (MIRIAM annotations)
# ---------------------------------------------------------------------------

import re as _re

_RDF_RESOURCE_KEY = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource"
_RDF_LI = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li"

_BIOMODELS_RX = _re.compile(r"identifiers\.org/biomodels\.db/(BIOMD\d+)")
_PUBMED_RX    = _re.compile(r"identifiers\.org/pubmed/(\d+)")
_DOI_RX       = _re.compile(r"identifiers\.org/doi/([^\s\"]+)")
_TAXONOMY_RX  = _re.compile(r"identifiers\.org/taxonomy/(\d+)")


def _collect_resource_uris(model_elem: ET.Element) -> list[str]:
    """Walk the <model><annotation> subtree and harvest every rdf:resource URI."""
    uris: list[str] = []
    for elem in model_elem.iter():
        # rdf:li / rdf:Description / bqmodel:* etc. — we only care about the URI attr
        uri = elem.attrib.get(_RDF_RESOURCE_KEY)
        if uri:
            uris.append(uri)
    return uris


def _collect_creators(model_elem: ET.Element) -> list[str]:
    """Extract 'Given Family' strings from each vCard:N block.

    Robust to either Given-then-Family or Family-then-Given child order.
    """
    out: list[str] = []
    for elem in model_elem.iter():
        if _localname(elem.tag) != "N":
            continue
        given = ""
        family = ""
        for child in elem.iter():
            ln = _localname(child.tag)
            if ln == "Given":
                given = (child.text or "").strip()
            elif ln == "Family":
                family = (child.text or "").strip()
        name = " ".join(x for x in (given, family) if x)
        if name:
            out.append(name)
    return out


def _extract_notes_excerpt(model_elem: ET.Element, max_len: int = 280) -> str:
    for elem in model_elem.iter():
        if _localname(elem.tag) == "notes":
            text = " ".join((elem.itertext())).strip()
            text = " ".join(text.split())
            if len(text) > max_len:
                text = text[:max_len].rstrip() + "..."
            return text
    return ""


def extract_metadata(sbml_bytes: bytes) -> SbmlModelMetadata:
    """Pull MIRIAM-style annotations from <model> for manifest auto-fill.

    Best-effort: missing fields are returned as empty strings. Never raises.
    """
    md = SbmlModelMetadata()
    try:
        root = ET.fromstring(sbml_bytes)
    except ET.ParseError:
        return md
    # Find <model>
    model_elem: ET.Element | None = None
    for e in root.iter():
        if _localname(e.tag) == "model":
            model_elem = e
            break
    if model_elem is None:
        return md

    md.model_id = model_elem.attrib.get("id", "")
    md.model_name = model_elem.attrib.get("name", "")
    md.notes_excerpt = _extract_notes_excerpt(model_elem)
    md.creators = _collect_creators(model_elem)

    uris = _collect_resource_uris(model_elem)
    for uri in uris:
        if not md.biomodels_id:
            m = _BIOMODELS_RX.search(uri)
            if m:
                md.biomodels_id = m.group(1)
                continue
        if not md.pubmed_id:
            m = _PUBMED_RX.search(uri)
            if m:
                md.pubmed_id = m.group(1)
                continue
        if not md.doi:
            m = _DOI_RX.search(uri)
            if m:
                md.doi = m.group(1)
                continue
        if not md.taxonomy_id:
            m = _TAXONOMY_RX.search(uri)
            if m:
                md.taxonomy_id = m.group(1)
                continue

    if md.taxonomy_id and md.taxonomy_id in _TAXONOMY_NAMES:
        md.organism = _TAXONOMY_NAMES[md.taxonomy_id]
    return md

