"""Convert Pirson's WoWTranslator Lua dictionaries to Python glossary_data.py.

One-time script. Reads WoWTranslator/Data/*.lua files, classifies entries
into SAFE_ABBREVIATIONS (Tier 1) and CONTEXT_EXPANSIONS (Tier 2),
deduplicates against existing phrasebook + slang, and writes app/glossary_data.py.

Usage:
    python scripts/convert_pirson_glossary.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "WoWTranslator" / "Data"
OUTPUT_FILE = REPO_ROOT / "app" / "glossary_data.py"

# Locale code mapping: Pirson -> DeepL
LOCALE_MAP = {
    "enUS": "EN", "ruRU": "RU", "deDE": "DE", "frFR": "FR",
    "esES": "ES", "esMX": "ES", "itIT": "IT", "koKR": "KO",
    "ptBR": "PT", "zhCN": "ZH", "zhTW": "ZH",
}

# Already in our phrasebook or slang — skip these keys
_EXISTING_ABBREVS = {
    "gg", "bb", "afk", "brb", "ty", "np", "wp", "gj", "gl", "hf",
    "omw", "oom", "lfg", "lfm", "inv", "rdy", "inc", "wts", "wtb",
    "mb", "idd", "lf", "pls", "thx", "nvm", "idk", "imo", "tbh",
    "btw", "gtg", "nw", "bio", "wipe", "lust", "bl", "hero", "brez",
    "rez", "rezz", "cds", "kick", "int", "sum", "summ",
    # slang.py words
    "cd", "plz", "dps", "zamn", "alr", "rn", "ngl", "tbf", "omg",
    "w8", "m8", "u", "ur", "sec", "secs", "min", "mins",
}

# Dangerous English words that should NEVER be expanded — they have
# common non-gaming meanings that would corrupt normal sentences.
NEVER_EXPAND = frozenset({
    "add", "hit", "focus", "fire", "arms", "fury", "balance", "shadow",
    "holy", "blood", "sub", "cap", "need", "link", "gear", "spirit",
    "dodge", "trap", "burst", "stun", "recruit", "officer", "fresh",
    "mining", "cooking", "fishing", "frost", "arcane", "beast",
    "guardian", "resto", "disc", "brew", "wind", "mist", "dev",
    "survival", "mark", "warden", "assa", "haven",
})

# Keys that are safe standalone abbreviations (Tier 1) — they are unambiguous
# gaming terms that don't collide with common English words.
# Everything else from Pirson that's not in NEVER_EXPAND and not already
# in our phrasebook goes to CONTEXT_EXPANSIONS (Tier 2).
SAFE_ABBREV_KEYS = frozenset({
    # Social
    "gz", "gratz", "grats", "ggwp", "glhf", "g2g", "uw", "gn",
    "wb", "dc", "fh", "fm",
    # Classes
    "pala", "warr", "dk", "dh", "hpala", "rpala", "ppala",
    "lock", "spriest", "sham", "rsham", "esham", "dudu",
    "rdruid", "bdruid", "fdruid", "mage", "hunter", "monk",
    "ww", "mw", "bm",
    # Combat
    "aoe", "gcd", "cc", "dot", "hot", "hps",
    "debuff", "proc",
    # Groups
    "lfr", "lf1m", "lf2m", "lf3m", "hc", "nm",
    "10m", "25m", "ilvl", "achiev", "achieve", "achv",
    "pug", "gdkp",
    # Items
    "boe", "bop", "ml", "wtt", "cod",
    # PvP
    "rbg", "ab", "av", "wsg",
    "2s", "3s", "5s",
    # Professions
    "jc", "jw", "bs", "ec", "lw", "alch", "herb",
    # Roles
    "healers", "heals", "healer", "tanks",
    # Stats
    "ap", "haste", "mastery", "crit",
    # Raids
    "ms", "os",
    # misc
    "rng", "mog", "pve", "pvp",
    "omfg", "rofl", "lmao",
    "ninja", "nerf", "buff",
    "tailor", "enchant", "skinning",
})

# Regex to parse Pirson's Lua dict entries
_RE_ENTRY = re.compile(
    r'\["([^"]+)"\]\s*=\s*\{([^}]+)\}',
    re.DOTALL,
)
_RE_LOCALE = re.compile(
    r'(\w+)\s*=\s*"([^"]*)"',
)


def parse_lua_file(path: Path) -> dict[str, dict[str, str]]:
    """Parse a Pirson Lua data file. Returns {key: {locale: translation}}."""
    text = path.read_text(encoding="utf-8", errors="replace")
    entries: dict[str, dict[str, str]] = {}

    for m in _RE_ENTRY.finditer(text):
        key = m.group(1).strip().lower()
        body = m.group(2)

        translations: dict[str, str] = {}
        for lm in _RE_LOCALE.finditer(body):
            locale = lm.group(1)
            value = lm.group(2).strip()
            if locale in LOCALE_MAP and value:
                deepl_code = LOCALE_MAP[locale]
                # Don't overwrite — first locale wins (esES before esMX)
                if deepl_code not in translations:
                    translations[deepl_code] = value

        if translations:
            entries[key] = translations

    return entries


def classify_entries(
    all_entries: dict[str, dict[str, str]],
) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """Classify entries into safe abbreviations and context expansions.

    Returns (safe_abbreviations, context_expansions).
    """
    safe: dict[str, dict[str, str]] = {}
    context: dict[str, str] = {}

    for key, translations in sorted(all_entries.items()):
        # Skip if already in our phrasebook/slang
        if key in _EXISTING_ABBREVS:
            continue

        # Skip dangerous words
        if key in NEVER_EXPAND:
            continue

        if key in SAFE_ABBREV_KEYS:
            safe[key] = translations
        else:
            # Context expansion: use English translation as expansion
            en_text = translations.get("EN", "")
            if en_text and en_text.lower() != key:
                context[key] = en_text

    return safe, context


def generate_python(
    safe: dict[str, dict[str, str]],
    context: dict[str, str],
) -> str:
    """Generate glossary_data.py content."""
    lines = [
        '"""WoW glossary data extracted from Pirson\'s WoW Translator addon.',
        '',
        'Source: https://www.curseforge.com/wow/addons/wow-translator',
        'Author: Pirson (CurseForge project ID 1431567)',
        '',
        'Auto-generated by scripts/convert_pirson_glossary.py — do not edit manually.',
        '"""',
        '',
        'from __future__ import annotations',
        '',
        '# Tier 1: Safe standalone abbreviations with translations per language.',
        '# These are unambiguous gaming terms — safe to translate without context.',
        'SAFE_ABBREVIATIONS: dict[str, dict[str, str]] = {',
    ]

    for key in sorted(safe):
        translations = safe[key]
        pairs = ", ".join(
            f'"{lang}": "{val}"'
            for lang, val in sorted(translations.items())
        )
        lines.append(f'    "{key}": {{{pairs}}},')

    lines.append('}')
    lines.append('')
    lines.append('# Tier 2: Context expansions — WoW-specific terms expanded to plain English.')
    lines.append('# Only applied when 2+ gaming terms appear in the same message.')
    lines.append('CONTEXT_EXPANSIONS: dict[str, str] = {')

    for key in sorted(context):
        lines.append(f'    "{key}": "{context[key]}",')

    lines.append('}')
    lines.append('')

    return "\n".join(lines)


def main() -> int:
    if not DATA_DIR.is_dir():
        print(f"Error: {DATA_DIR} not found", file=sys.stderr)
        return 1

    # Parse all Lua files
    all_entries: dict[str, dict[str, str]] = {}
    lua_files = sorted(DATA_DIR.glob("*.lua"))
    print(f"Found {len(lua_files)} Lua files in {DATA_DIR}")

    for path in lua_files:
        entries = parse_lua_file(path)
        print(f"  {path.name}: {len(entries)} entries")
        for key, translations in entries.items():
            if key not in all_entries:
                all_entries[key] = translations
            else:
                # Merge translations from different files
                for lang, val in translations.items():
                    if lang not in all_entries[key]:
                        all_entries[key][lang] = val

    print(f"\nTotal unique entries: {len(all_entries)}")

    # Classify
    safe, context = classify_entries(all_entries)
    print(f"Tier 1 (safe abbreviations): {len(safe)}")
    print(f"Tier 2 (context expansions): {len(context)}")
    print(f"Skipped (already in phrasebook/slang): {len(_EXISTING_ABBREVS & set(all_entries))}")
    print(f"Skipped (NEVER_EXPAND): {len(NEVER_EXPAND & set(all_entries))}")

    # Generate
    content = generate_python(safe, context)
    OUTPUT_FILE.write_text(content, encoding="utf-8")
    print(f"\nWritten to {OUTPUT_FILE}")
    print(f"  SAFE_ABBREVIATIONS: {len(safe)} entries")
    print(f"  CONTEXT_EXPANSIONS: {len(context)} entries")

    return 0


if __name__ == "__main__":
    sys.exit(main())
