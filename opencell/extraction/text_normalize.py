"""Demangle common pypdf extraction artifacts.

pypdf loses superscripts/subscripts.  Empirically observed mappings on
Thattai (2001) PNAS PDF:

    "="    →  "5"     (the equals sign reads as digit 5)
    "^-1"  →  "21"    (e.g. "s^-1" → "s21", "min^-1" → "min21")
    "^-2"  →  "22"
    "_R"   →  "R"     (subscripts dropped, no underscore)
    "γ"    →  "g"     (Greek gamma → latin g)
"""

from __future__ import annotations

import re

_UNIT_STEMS = r"(s|sec|secs|second|seconds|min|mins|minute|minutes|h|hr|hour|hours|ms|us|d|day)"

_RE_POWER_MANGLED = re.compile(rf"\b{_UNIT_STEMS}\s*2(\d)\b")
_RE_POWER_MANGLED_SP = re.compile(rf"\b{_UNIT_STEMS}\s+2(\d)\b")


def demangle_unit_string(raw: str) -> str:
    """Best-effort fix for unit-string artifacts produced by pypdf.

    Idempotent.  Examples:
        "s21"   -> "s^-1"
        "min21" -> "min^-1"
        "h 22"  -> "h^-2"
    """
    if not raw:
        return raw

    def _sub(m: re.Match[str]) -> str:
        return f"{m.group(1)}^-{m.group(2)}"

    out = _RE_POWER_MANGLED.sub(_sub, raw)
    out = _RE_POWER_MANGLED_SP.sub(_sub, out)
    return out


def demangle_context(text: str) -> str:
    """Cosmetic demangling for human-readable context windows.

    The original raw text is always preserved for hashing/audit.  This
    helper is purely for display.
    """
    text = re.sub(r"([A-Za-z_])\s+5\s+(\d)", r"\1 = \2", text)
    text = demangle_unit_string(text)
    return text
