"""WoW glossary: abbreviation lookup + context-gated term expansion.

Data source: Pirson's WoW Translator addon (CurseForge).
See app/glossary_data.py for the extracted dictionary.

Two public functions:

1. lookup_abbreviation(text, target_lang) -> str | None
   Standalone translation of safe WoW abbreviations (Tier 1).
   Called from phrasebook — no API needed.

2. expand_wow_terms(text) -> str
   Expands WoW-specific terms to plain English before DeepL (Tier 2).
   Context-gated: only expands when 2+ gaming terms in the message.
"""

from __future__ import annotations

import logging
import re

from app.glossary_data import CONTEXT_EXPANSIONS, SAFE_ABBREVIATIONS

logger = logging.getLogger(__name__)

# Words that must NEVER be expanded even if they appear in CONTEXT_EXPANSIONS,
# because they have common non-gaming meanings.
_NEVER_EXPAND = frozenset({
    "add", "hit", "focus", "fire", "arms", "fury", "balance", "shadow",
    "holy", "blood", "sub", "cap", "need", "link", "gear", "spirit",
    "dodge", "trap", "burst", "stun", "recruit", "officer", "fresh",
    "mining", "cooking", "fishing", "frost", "arcane", "beast",
    "guardian", "resto", "disc", "brew", "wind", "mist", "dev",
    "survival", "mark", "warden", "assa", "haven",
})

# Minimum number of recognized WoW terms in a message to trigger expansion.
_CONTEXT_GATE = 2

# Build word-boundary regex for context expansions (longest first).
_expansion_keys = sorted(CONTEXT_EXPANSIONS.keys(), key=len, reverse=True)
_EXPAND_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _expansion_keys) + r")\b",
    re.IGNORECASE,
)


def lookup_abbreviation(text: str, target_lang: str) -> str | None:
    """Look up a safe WoW abbreviation (Tier 1).

    Returns translated string if found, None on miss.
    """
    norm = text.strip().lower()
    entry = SAFE_ABBREVIATIONS.get(norm)
    if entry is None:
        return None

    tgt = target_lang.upper()
    result = entry.get(tgt)
    if result is not None:
        logger.debug("Glossary abbrev hit: %r -> %s = %r", norm, tgt, result)
    return result


def expand_wow_terms(text: str) -> str:
    """Expand WoW-specific terms to plain English (Tier 2, context-gated).

    Only expands when the message contains 2+ recognized gaming terms.
    Words in _NEVER_EXPAND are never touched.

    Returns the expanded text (may be identical if no expansion needed).
    """
    # Count how many known WoW terms appear in the text
    words_lower = set(re.findall(r"\b\w+\b", text.lower()))
    wow_term_count = sum(
        1 for w in words_lower
        if w in CONTEXT_EXPANSIONS and w not in _NEVER_EXPAND
    )

    if wow_term_count < _CONTEXT_GATE:
        return text

    def _replace(m: re.Match) -> str:
        word = m.group(0).lower()
        if word in _NEVER_EXPAND:
            return m.group(0)
        return CONTEXT_EXPANSIONS.get(word, m.group(0))

    result = _EXPAND_RE.sub(_replace, text)
    if result != text:
        logger.info("WoW terms expanded: %r -> %r", text[:60], result[:60])
    return result
