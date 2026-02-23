"""Gaming slang normalizer — expands abbreviations to plain English before DeepL.

DeepL struggles with short gaming slang ("summ all pls", "rezz me",
"30 sec bio").  This module replaces known slang tokens with their
plain-English equivalents so DeepL can translate them correctly.

The replacement happens BEFORE sending to DeepL.  Characters in the
context parameter are free, but the actual text must be comprehensible.

Example:
    "summ all pls"  → "summon all please"
    "30 sec bio"    → "30 sec break"
    "rezz me pls"   → "resurrect me please"
    "pop cds"       → "pop cooldowns"
"""

from __future__ import annotations

import re

# Word-level replacements: slang → plain English
# Order matters for multi-word patterns — longer patterns checked first.
_WORD_MAP: dict[str, str] = {
    # Summon variants
    "summ": "summon",
    "sum": "summon",
    # Resurrect
    "rezz": "resurrect",
    "rez": "resurrect",
    "brez": "battle resurrect",
    # Break / bio
    "bio": "break",
    # Cooldowns
    "cds": "cooldowns",
    "cd": "cooldown",
    # Please
    "pls": "please",
    "plz": "please",
    # Roles / actions
    "dps": "damage",
    "int": "interrupt",
    # Lust / hero
    "lust": "bloodlust",
    "bl": "bloodlust",
    "hero": "heroism",
    # Exclamations
    "zamn": "damn",
    # Misc
    "alr": "already",
    "rn": "right now",
    "ngl": "not gonna lie",
    "tbf": "to be fair",
    "omg": "oh my god",
    "idk": "I don't know",
    "imo": "in my opinion",
    "w8": "wait",
    "m8": "mate",
    "u": "you",
    "ur": "your",
    "sec": "second",
    "secs": "seconds",
    "min": "minute",
    "mins": "minutes",
}

# Build regex: match whole words, longest first to avoid partial matches
_pattern_parts = sorted(_WORD_MAP.keys(), key=len, reverse=True)
_SLANG_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _pattern_parts) + r")\b",
    re.IGNORECASE,
)


def expand_slang(text: str) -> str:
    """Replace gaming slang tokens with plain English equivalents.

    Only replaces whole words (word boundaries).  Case-insensitive
    matching, preserves surrounding text.

    Returns the expanded text (may be identical if no slang found).
    """
    def _replace(m: re.Match) -> str:
        word = m.group(0).lower()
        return _WORD_MAP.get(word, m.group(0))

    return _SLANG_RE.sub(_replace, text)
