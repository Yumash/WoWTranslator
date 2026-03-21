# BabelChat

## Break the language barrier in World of Warcraft

[![Donate](https://img.shields.io/badge/Donate-USDT%20%7C%20OpenCollective-blue?style=for-the-badge&logo=tether&logoColor=white)](https://yumatech.ru/donate/)

## The Problem

You join a PUG raid. The tank explains tactics — in Spanish. The healer asks something — in German. Nobody understands each other. Sound familiar?

**BabelChat fixes this.** It translates WoW chat in real time — both gaming terms (instantly) and full sentences (via DeepL companion app).

## Key Features

**Standalone (addon only):**
- **347 gaming terms** translated in 14 languages — lfm, wts, dps, ez, copium, go next...
- Clean annotation below the original message (no inline color spam)
- 12 categories: Social, Classes, Combat, Raid, M+, PvP, Trade, Professions...
- Hyperlink-aware — never breaks item/spell/achievement links
- Works out of the box, no API keys needed

**With companion app (free):**
- **Full sentence translation** via DeepL (22 languages)
- Smart overlay on top of WoW with channel colors
- Streaming — original shows instantly, translation arrives 0.5-2s later
- 500,000 characters/month free (DeepL Free tier)
- Read-only memory access — never writes, injects, or automates

## Dictionary

**347 terms x 14 languages:**

| Category | Examples | Count |
|----------|----------|-------|
| Social & Slang | ty, gg, brb, ez, copium, go next, kek | 104 |
| Classes & Specs | dk, ret, bm, disc, resto, boomkin | 59 |
| Raid & Dungeon | wipe, prog, soak, kite, brez, vault | 54 |
| Combat | aggro, aoe, cc, dps, dot, cleave | 33 |
| Groups | lfm, lf1m, premade, pug | 29 |
| Stats | crit, haste, mastery, vers, ilvl | 19 |
| Professions | jc, bs, enchant, herb, alch | 17 |
| Trade | wtb, wts, bis, mats, cod | 8 |
| + Zones | 5000+ zone names via LibBabble | — |

**Languages:** English, Spanish, German, French, Italian, Portuguese, Russian, Korean, Chinese (Simplified & Traditional), Polish, Swedish, Norwegian.

## Commands

- **/babel** — Show help
- **/babel config** — Open settings
- **/babel on/off** — Toggle dictionary
- **/babel test** — Test with sample message
- **/babel companion** — Companion app status

## Companion App

For full sentence translation, download the free companion app:
https://github.com/Yumash/BabelChat

The companion reads the addon's buffer via ReadProcessMemory (read-only, no injection, no automation) and shows translations in a sleek overlay.

## Credits

BabelChat's dictionary is based on [WoW Translator](https://www.curseforge.com/wow/addons/wow-translator) by **Pirson** (MIT License) — 314 original terms in 14 languages. We added 33 slang terms, rewrote the translation engine for clean output, and built the companion app.

- **Pirson** — Dictionary data & in-game translation idea — [Buy Me a Coffee](https://buymeacoffee.com/franciscorb)
- **Andrey Yumashev** — BabelChat addon, companion app, DictEngine v2

## License

MIT License — free to use, modify, and distribute.
