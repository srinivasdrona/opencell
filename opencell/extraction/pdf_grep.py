"""Regex-based candidate extraction from cached PDF text.

Strategy: produce *all* candidates that match a symbol-equals-value pattern,
along with a context window and a heuristic score.  The score is advisory
only — it never auto-resolves ambiguity.

We handle the pypdf mangling described in ``text_normalize`` by accepting
the equals sign as either ``=`` or the bare digit ``5`` between two
spaces, and by post-processing matched unit strings via ``demangle_unit_string``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .candidate import ExtractionCandidate, SectionType
from .provenance import Provenance, make_provenance
from .text_normalize import demangle_context, demangle_unit_string

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Equals-sign variants: literal '=', '≈', '~', or pypdf-mangled bare '5'
# surrounded by spaces.  We must NOT match a digit '5' that is part of a number.
_EQ = r"(?:=|≈|~|5)"

# Numeric value (allow scientific notation, optional ± uncertainty)
_NUM = r"([\d]+(?:\.[\d]+)?(?:[eE][+\-]?\d+)?)"

# Optional unit: any alnum token, optionally followed by ^-N or just digits
# (which catches pypdf-mangled "s21" etc).  Limited to ~20 chars.
# NB: the optionality is expressed by the outer `?` in the calling pattern;
# this group itself is NOT optional, so it greedily captures when present.
_UNIT = r"([A-Za-z][A-Za-z0-9μµ\^\-\/\·]{0,20})"

# Context window radius (chars before/after match)
CONTEXT_RADIUS = 150

# Definitional language anchors — boost score
_DEFINITIONAL_PHRASES = [
    "fixed at", "base case", "set to", "we use", "we set", "default",
    "corresponds to", "is taken to be", "is taken as", "we choose",
    "we assume", "parameter values", "model parameter",
    "value of", "estimated to be",
]

# References-section markers
_REFS_PHRASES = ["references", "bibliography", "literature cited"]

# Caption markers
_CAPTION_PHRASES = ["fig.", "figure ", "fig ", "table "]

# English stop-words that frequently get eaten as "unit" by the regex
# because they immediately follow a number ("0.5 in our model", "5 of the").
# Treat any of these as "no unit found".
_NON_UNIT_TOKENS = {
    "a", "an", "the", "in", "of", "for", "to", "by", "with", "at",
    "is", "are", "was", "were", "be", "been", "being",
    "and", "or", "but", "as", "if", "then", "than",
    "we", "our", "this", "these", "that", "those", "such",
    "from", "into", "out", "on", "off", "up", "down",
    "no", "not", "all", "any", "each", "every", "some",
}


# ---------------------------------------------------------------------------
# Symbol normalization for matching
# ---------------------------------------------------------------------------

def symbol_variants(symbol: str) -> list[str]:
    """Generate plausible regex-escaped variants of a symbol as it might
    appear after pypdf extraction.

    "k_R"   -> ["k_R", "kR", "k_?R"]
    "γ_P"   -> ["γ_P", "g_P", "gP", "γP"]
    """
    variants: list[str] = [symbol]
    # Strip underscores
    no_underscore = symbol.replace("_", "")
    if no_underscore != symbol:
        variants.append(no_underscore)
    # Greek to latin (common biology mappings)
    greek_map = {"γ": "g", "α": "a", "β": "b", "δ": "d", "μ": "u", "λ": "l", "κ": "k"}
    transliterated = symbol
    for g, latin in greek_map.items():
        transliterated = transliterated.replace(g, latin)
    if transliterated != symbol:
        variants.append(transliterated)
        variants.append(transliterated.replace("_", ""))
    # Deduplicate, preserving order
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


# ---------------------------------------------------------------------------
# Section tagging
# ---------------------------------------------------------------------------

def classify_section(text: str, position: int) -> SectionType:
    """Heuristically classify the document section containing `position`."""
    # Look 600 chars back for nearest section marker
    back = text[max(0, position - 600):position].lower()
    if any(p in back for p in _CAPTION_PHRASES):
        return SectionType.CAPTION
    if any(p in back for p in _REFS_PHRASES):
        return SectionType.REFS
    return SectionType.BODY


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_candidate(
    *,
    context: str,
    section: SectionType,
    raw_unit_normalized: str,
    target_unit: str,
    units_compat: bool,
) -> tuple[float, dict[str, float]]:
    """Compute heuristic score 0..1 for a candidate.

    Components:
      - definitional language present (+0.3)
      - section is caption or table (+0.2)
      - section is references (-0.5, virtual reject)
      - unit family compatible with target (+0.3)
      - unit string non-empty (+0.1)
      - exact target_unit match (+0.1)
    """
    components: dict[str, float] = {}
    score = 0.0

    ctx_lower = context.lower()
    if any(p in ctx_lower for p in _DEFINITIONAL_PHRASES):
        components["definitional"] = 0.3
        score += 0.3

    if section == SectionType.CAPTION:
        components["section_caption"] = 0.2
        score += 0.2
    elif section == SectionType.TABLE:
        components["section_table"] = 0.2
        score += 0.2
    elif section == SectionType.SBML:
        components["section_sbml"] = 0.4
        score += 0.4
    elif section == SectionType.REFS:
        components["section_refs"] = -0.5
        score -= 0.5

    if raw_unit_normalized:
        components["unit_present"] = 0.1
        score += 0.1

    if units_compat:
        components["unit_compatible"] = 0.3
        score += 0.3

    if raw_unit_normalized and target_unit and raw_unit_normalized.replace(" ", "") == target_unit.replace(" ", ""):
        components["unit_exact_match"] = 0.1
        score += 0.1

    return max(0.0, min(1.0, score)), components


# ---------------------------------------------------------------------------
# Main grep
# ---------------------------------------------------------------------------

def _line_for_offset(text: str, offset: int) -> int:
    """1-based line number containing the given character offset."""
    return text.count("\n", 0, offset) + 1


@dataclass
class GrepConfig:
    target_unit: str = ""
    context_radius: int = CONTEXT_RADIUS
    min_score_for_survival: float = 0.3  # below this → mark rejected
    require_unit: bool = True            # if True, hits with no unit are rejected


def grep_for_symbol(
    text: str,
    symbol: str,
    *,
    config: GrepConfig | None = None,
    provenance: Provenance | None = None,
) -> list[ExtractionCandidate]:
    """Find all occurrences of `symbol = value [unit]` in `text`.

    Returns one ExtractionCandidate per regex hit (including ones below
    the survival threshold; those have a non-empty rejection_reason).
    """
    cfg = config or GrepConfig()
    candidates: list[ExtractionCandidate] = []
    seen_spans: set[tuple[int, int]] = set()

    from .units import units_compatible, convert

    for variant in symbol_variants(symbol):
        sym_re = re.escape(variant)
        # Anchor with word boundary on the *left* so kR doesn't match RkR.
        # On the right, allow optional subscript-like suffix to be eaten:
        # we want kR not to match kR1, kRi, etc.  So require non-letter after.
        pattern = rf"(?<![A-Za-z0-9_]){sym_re}(?![A-Za-z_])\s*{_EQ}\s*{_NUM}\s*{_UNIT}?"
        rgx = re.compile(pattern)

        for m in rgx.finditer(text):
            span = m.span()
            if span in seen_spans:
                continue
            seen_spans.add(span)

            try:
                raw_value = float(m.group(1))
            except (ValueError, IndexError):
                continue
            raw_unit = (m.group(2) or "").strip() if m.lastindex and m.lastindex >= 2 else ""
            # Filter out English stop-words that masquerade as units
            if raw_unit.lower() in _NON_UNIT_TOKENS:
                raw_unit = ""
            raw_unit_norm = demangle_unit_string(raw_unit)

            ctx_start = max(0, span[0] - cfg.context_radius)
            ctx_end = min(len(text), span[1] + cfg.context_radius)
            raw_context = text[ctx_start:ctx_end]
            display_context = demangle_context(raw_context)

            section = classify_section(text, span[0])
            line_no = _line_for_offset(text, span[0])

            # Unit compatibility check (advisory; feeds score only)
            units_compat = (
                bool(cfg.target_unit) and bool(raw_unit_norm)
                and units_compatible(raw_unit_norm, cfg.target_unit)
            )

            score, components = score_candidate(
                context=raw_context,
                section=section,
                raw_unit_normalized=raw_unit_norm,
                target_unit=cfg.target_unit,
                units_compat=units_compat,
            )

            # Optional conversion to target unit
            converted_value: float | None = None
            converted_unit = ""
            transformation = ""
            convertible = None
            if cfg.target_unit and raw_unit_norm:
                cr = convert(raw_value, raw_unit_norm, cfg.target_unit)
                convertible = cr.success
                if cr.success:
                    converted_value = cr.converted_value
                    converted_unit = cr.converted_unit
                    transformation = cr.transformation

            # Determine rejection reason (if any)
            rejection = ""
            if section == SectionType.REFS:
                rejection = "in references section"
            elif cfg.require_unit and not raw_unit_norm:
                rejection = "no unit found adjacent to value"
            elif score < cfg.min_score_for_survival:
                rejection = f"score {score:.2f} below threshold {cfg.min_score_for_survival}"

            cand = ExtractionCandidate(
                raw_value=raw_value,
                raw_unit=raw_unit,
                raw_unit_normalized=raw_unit_norm,
                method="pdf_grep",
                locator=f"line {line_no}",
                context_window=display_context,
                section_type=section,
                score=score,
                score_components=components,
                rejection_reason=rejection,
                convertible_to_target=convertible,
                converted_value=converted_value,
                converted_unit=converted_unit,
                transformation=transformation,
                source_path=provenance.path if provenance else "",
                source_sha256=provenance.sha256 if provenance else "",
                extractor_version=provenance.extractor_version if provenance else "",
            )
            candidates.append(cand)

    return candidates


def grep_file(
    path: str | Path,
    symbol: str,
    *,
    config: GrepConfig | None = None,
) -> list[ExtractionCandidate]:
    """Convenience wrapper: read cached text file and grep for symbol."""
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    prov = make_provenance(p)
    return grep_for_symbol(text, symbol, config=config, provenance=prov)
