<p align="center">
  <img src="assets/icon.png" alt="WoWTranslator" width="80" />
</p>

<h1 align="center">WoW Chat Translator</h1>

<p align="center">
  <b>Real-time World of Warcraft chat translation with a smart overlay</b><br>
  Companion app + tiny WoW addon for multilingual groups
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License" /></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.12+-yellow.svg" alt="Python" /></a>
  <a href="https://github.com/Yumash/WoWTranslator/releases"><img src="https://img.shields.io/github/v/release/Yumash/WoWTranslator" alt="Release" /></a>
</p>

<p align="center">
  <a href="README.md">Русская версия</a>
</p>

---

## What Is This?

WoWTranslator is a desktop companion app that translates World of Warcraft chat **in real time** — with less than 1 second latency. A tiny WoW addon captures chat messages and writes them to a memory buffer; the companion app reads this buffer, detects the language, translates via DeepL, and displays results in a sleek overlay on top of your game.

No more language barriers in PUGs, international guilds, or cross-realm groups.

## Key Features

- **Real-time translation** — messages appear in the overlay within ~1 second
- **Auto language detection** — powered by lingua-py, fully offline (~1ms per message)
- **Smart overlay** — WoW-native dark theme with proper channel colors, click-through by default
- **Bidirectional translation** — translate incoming chat AND compose outgoing messages in any language
- **Built-in phrasebook** — 45 common phrases + 30 gaming abbreviations translated instantly without API
- **Channel filters** — Party, Raid, Guild, Say/Yell, Whisper, Instance — pick what you need
- **DeepL Free API** — 500,000 characters/month for free (that's a LOT of chat)
- **Translation cache** — SQLite + in-memory LRU, never translates the same thing twice
- **Global hotkeys** — toggle translation ON/OFF without leaving the game
- **Setup wizard** — guided 5-step first-run configuration
- **System tray** — minimize to tray, quick access to settings
- **22 languages supported** — EN, RU, DE, FR, ES, IT, PT, PL, NL, SV, DA, FI, CS, RO, HU, BG, EL, TR, UK, JA, KO, ZH

## How It Works

### The Problem

WoW writes chat to `WoWChatLog.txt`, but uses an internal ~4KB buffer. The file only updates when the buffer fills — **real delay is 1-5 minutes**. Unacceptable for a chat translator.

### The Solution

A tiny addon hooks chat events via the standard WoW API and writes messages into a Lua string with unique markers. The companion app finds this string in WoW's process memory via `ReadProcessMemory` and delivers messages to the translation pipeline — all within ~1 second.

```
┌──────────────────────────────────────────────────────────┐
│  World of Warcraft                                       │
│                                                          │
│  ChatTranslatorHelper addon                              │
│  ├── Hooks CHAT_MSG_* events                             │
│  ├── Polls ChatFrame scrollback (200ms)                  │
│  ├── Ring buffer (50 messages)                           │
│  │   Format: SEQ|RAW|formatted text                      │
│  └── Writes to ChatTranslatorHelperDB.wctbuf             │
│      with __WCT_BUF__ / __WCT_END__ markers              │
└──────────┬───────────────────────────────────────────────┘
           │  ReadProcessMemory (every 500ms)
           ▼
┌──────────────────────────────────────────────────────────┐
│  Companion App (Python, runs as admin)                   │
│                                                          │
│  Memory Reader ──→ Parser ──→ Language Detector          │
│       │                           │                      │
│       │         ┌─────────────────┘                      │
│       │         ▼                                        │
│       │    Phrasebook (instant) ──→ Cache (SQLite)       │
│       │         │                      │                 │
│       │         ▼                      ▼                 │
│       │    DeepL API ─────────→ Smart Overlay (PyQt6)    │
│       │                                                  │
│  File Watcher (fallback, polls every 1s)                 │
└──────────────────────────────────────────────────────────┘
```

### Translation Pipeline

Every message goes through a multi-stage pipeline:

1. **Abbreviation check** (pre-detection) — `gg` → `good game`, `ty` → `thank you` — instant
2. **Language detection** — lingua-py identifies language offline, Cyrillic fallback for short text
3. **Phrase lookup** (post-detection) — `привет` → `hello`, `danke` → `thanks` — instant
4. **Cache lookup** — SQLite persistent cache + in-memory LRU (1000 entries)
5. **DeepL API** — only called when all above miss

Messages in your own language are never translated. Gaming jargon (`lol`, `afk`, `brb`, `pull`, etc.) is automatically skipped.

### Smart Overlay

The overlay is styled like WoW's native chat — dark semi-transparent background with proper channel colors:

| Channel | Color |
|---------|-------|
| Say | White |
| Yell | Red |
| Party | Light blue |
| Raid | Orange |
| Guild | Green |
| Whisper | Pink |
| Instance | Orange |

Features:
- **Click-through** by default — clicks pass through to the game
- **Draggable and resizable** — position and size are remembered
- **Minimize to title bar** — collapse with one click
- **Channel filter tabs** — show only the channels you want
- **Reply translator** — type a message, pick target language, hit Enter, copy translation to clipboard

### Memory Reader Architecture

The memory reader uses a tiered scanning strategy for maximum speed:

| Tier | Speed | When Used |
|------|-------|-----------|
| History scan (16 cached regions) | ~30ms | First try — checks where markers were found before |
| Heap scan (all regions ≤ 8MB) | ~1-3s | History miss — scans all heap regions |
| Full scan (entire process) | ~7-10s | Last resort — pymem pattern scan |

The addon creates a new Lua string on every buffer update (Lua strings are immutable). The memory reader tracks which memory regions previously contained the marker and checks those first — resulting in sub-second relocation after buffer moves.

## Installation

### Quick Start (Recommended)

1. Download `WoWTranslator.zip` from [Releases](https://github.com/Yumash/WoWTranslator/releases)
2. Extract anywhere and run `WoWTranslator.exe` **as Administrator**
3. Follow the setup wizard:
   - Get a [free DeepL API key](https://www.deepl.com/pro-api) (takes 2 minutes)
   - Set your WoW installation path (auto-detected in most cases)
   - Choose your language and target translation language
   - Install the addon with one click
4. Launch WoW, enter a group, and watch translations appear!

### From Source

```bash
git clone https://github.com/Yumash/WoWTranslator.git
cd WoWTranslator
pip install -r requirements.txt
python -m app.main
```

> **Note:** Must be run as Administrator (ReadProcessMemory requires elevated privileges).

### WoW Addon (Manual Install)

Copy the `addon/ChatTranslatorHelper/` folder to:
```
World of Warcraft/_retail_/Interface/AddOns/ChatTranslatorHelper/
```

Or let the companion app install it for you (Settings → Install Addon).

## Configuration

### Setup Wizard

On first launch, a 5-step wizard guides you through:

1. **Welcome** — choose your interface language
2. **API Key** — paste your DeepL API key and validate it
3. **WoW Path** — auto-detect or browse to your WoW installation
4. **Languages** — set your own language and target translation language
5. **Ready** — install the addon and launch

### Settings Dialog

Access via the overlay toolbar button or system tray → Settings.

**General tab:**
- DeepL API key management with usage quota display
- WoW path and addon installer
- Interface language (RU, EN)
- Your language / target language
- Channel toggles (Party, Raid, Guild, Say/Yell, Whisper, Instance)

**Overlay tab:**
- Background opacity (20-100%)
- Font size (8-20pt)
- Translation ON by default toggle
- Debug console toggle

**Hotkeys tab:**
- Toggle Translation (default: `Ctrl+Shift+T`)
- Clipboard Translate (default: `Ctrl+Shift+C`)
- Custom key capture with modifier support

### Addon Commands

Type in WoW chat:

| Command | Description |
|---------|------------|
| `/wct` | Show addon status |
| `/wct buf` | Memory buffer info (message count, seq) |
| `/wct log on\|off` | Enable/disable chat logging |
| `/wct auto on\|off` | Auto-enable logging on login |
| `/wct flush on\|off\|<sec>` | Control log flush timer |
| `/wct poll on\|off` | Control ChatFrame polling |
| `/wct verbose on\|off` | Toggle verbose output |

### config.json

All settings are stored in `config.json` (auto-generated). Key fields:

```json
{
  "deepl_api_key": "your-key-here:fx",
  "wow_path": "D:/World of Warcraft",
  "own_language": "RU",
  "target_language": "EN",
  "overlay_opacity": 180,
  "overlay_font_size": 10,
  "hotkey_toggle_translate": "Ctrl+Shift+T",
  "channels_party": true,
  "channels_raid": true,
  "channels_guild": true,
  "channels_say": true,
  "channels_whisper": true,
  "channels_instance": true,
  "show_debug_console": false
}
```

## Built-in Phrasebook

WoWTranslator includes a built-in phrasebook for instant translation of common phrases and gaming abbreviations — **no API call needed**.

**45 phrases** across 5 languages (EN, RU, DE, FR, ES):
- Greetings: hello, bye, good morning, welcome, see you...
- Politeness: thanks, please, sorry, no problem, my bad...
- Gaming: ready, wait, follow me, on my way, need help...
- WoW-specific: summon please, invite please, good run, well played...

**30 gaming abbreviations** (universal):
`gg`, `bb`, `afk`, `brb`, `ty`, `np`, `wp`, `gj`, `gl`, `hf`, `omw`, `oom`, `lfg`, `lfm`, `inv`, `rdy`, `inc`, `wts`, `wtb`, `mb`, `idd`, `lf`, `pls`, `thx`, `nvm`, `idk`, `imo`, `tbh`, `btw`, `gtg`

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Companion App | Python 3.12 |
| GUI / Overlay | PyQt6 (WS_EX_TRANSPARENT, click-through) |
| Memory Reader | pymem (ReadProcessMemory) |
| Language Detection | lingua-py (offline, ~1ms) |
| Translation | DeepL Free API (500K chars/month) |
| Phrasebook | Built-in: 45 phrases + 30 abbreviations |
| Cache | SQLite + in-memory LRU |
| Build | PyInstaller → single .exe |
| WoW Addon | Lua 5.1 (~300 lines) |
| WoW Version | The War Within / Midnight (12.0+) |

## Blizzard ToS Compliance

| Aspect | Status |
|--------|--------|
| Memory reading (ReadProcessMemory) | Read-only. Warden does not flag read-only access. Same approach as WeakAuras Companion and WarcraftLogs. |
| Overlay on top of game | Allowed. Same approach as Discord Overlay. |
| Addon hooks CHAT_MSG_* | Standard WoW API. Used by every chat addon. |
| No code injection | Compliant. No DLL injection, no hooking. |
| No automation | Compliant. No automated actions, movement, or combat. |
| Outgoing via clipboard | User manually pastes with Ctrl+V. Not automation. |

## Limitations

- **Requires Administrator** — ReadProcessMemory needs elevated privileges
- **DeepL Free** — 500K characters/month (~10K messages). Upgrade to paid plan for unlimited.
- **WoW Lua sandbox** — addon cannot make HTTP requests, so translation requires the companion app
- **Outgoing messages** — must be sent manually (copy → paste → Enter in WoW). By design for ToS compliance.
- **Numbered channels** — Trade, General, LookingForGroup not yet parsed (low priority)
- **Windows only** — ReadProcessMemory is a Windows API

## Development

```bash
# Run
python -m app.main

# Test
pytest

# Lint
ruff check app/ tests/

# Build .exe
pyinstaller build.spec
```

## Authors

- **Andrey Yumashev** — [@Yumash](https://github.com/Yumash)
- **Claude** (Anthropic) — AI co-author

## Support the Project

If WoWTranslator makes your multilingual WoW experience better, consider supporting its development:

| Cryptocurrency | Address |
|---|---|
| **USDT TRC20 (ByBit)** | `TGaUz963ZaCoHrfoDDgy1sCvSrK1wsZvcx` |
| **BTC (ByBit)** | `1BkYvFT8iBVG3GfTqkR2aBkABNkTrhYuja` |
| **TON** | `UQDFaHBN1pcQZ7_9-w1E_hS_JNfGf3d0flS_467w7LOQ7xbK` |

## License

[Apache License 2.0](LICENSE)
