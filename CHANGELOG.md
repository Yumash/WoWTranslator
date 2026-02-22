# Changelog / История изменений

## [1.0.1] — 2026-02-22

### Fixed / Исправлено
- Undetectable language now falls through to DeepL auto-detect instead of being skipped
- Debug console now works correctly in windowed .exe (AllocConsole + CONOUT$ redirect)
- Console hidden by default — enable via Settings → Overlay → "Show debug console"
- Added INFO-level logging for translation pipeline steps (detect, skip, translate, DeepL result)
- Fixed StreamHandler crash when sys.stderr is None in windowed exe

## [1.0.0] — 2026-02-22

First public release.

Первый публичный релиз.

### Added / Добавлено

**Core / Ядро:**
- Real-time chat translation via addon memory buffer (< 1s latency)
- Tiered memory scanning: region history (~30ms) → heap scan (~2.5s) → full scan (~7s)
- File watcher fallback — polls WoWChatLog.txt every 1s when addon unavailable
- Deduplication — messages from memory reader and file watcher are deduplicated by (author, text) with 30s TTL
- WoW item/spell link filtering — messages with only item links are skipped

**Translation / Перевод:**
- DeepL Free API integration (500K characters/month)
- Built-in phrasebook: 45 phrases (EN/RU/DE/FR/ES) + 30 gaming abbreviations — instant, no API needed
- Two-level translation cache: in-memory LRU (1000 entries) + SQLite persistent cache (7-day TTL)
- Offline language detection via lingua-py (~1ms per message)
- Cyrillic script fallback for short text that lingua can't classify
- Dual-threshold language detector: lenient (0.1) for short text (≤20 chars), strict (0.25) for longer text
- Gaming jargon auto-skip: lol, afk, brb, pull, cc, dps, heal, tank, etc.

**Overlay / Оверлей:**
- Smart overlay with WoW-native dark theme and channel colors
- Click-through mode by default (clicks pass through to the game)
- Draggable title bar, resizable from all edges
- Minimize to title bar with one click
- Channel filter tabs: All, Party, Raid, Guild, Say, Whisper, Instance
- Reply translator panel: type → translate → copy → paste in WoW
- WoW connection status indicator (attached / searching / offline)
- Translation ON/OFF toggle in title bar
- Opacity slider (20-100%)

**WoW Addon / Аддон WoW:**
- ChatTranslatorHelper addon (~300 lines Lua)
- ChatFrame scrollback polling every 200ms
- Ring buffer (50 messages) with `__WCT_BUF__` / `__WCT_END__` markers
- StripMarkup preserves hyperlinks while removing color codes
- `/wct` slash commands: status, buf, log, auto, flush, poll, verbose
- Auto-enable chat logging on login
- Buffer flush every 1.5 seconds

**Configuration / Настройка:**
- 5-step setup wizard for first-time configuration
- Settings dialog with 3 tabs: General, Overlay, Hotkeys
- Global hotkeys via Win32 API (default: Ctrl+Shift+T to toggle translation)
- 22 target languages supported
- One-click addon installation from settings
- Auto-detect WoW path via Windows Registry
- Debug console toggle in settings

**Infrastructure / Инфраструктура:**
- System tray integration with context menu
- PyInstaller single-file .exe build (admin privileges required)
- GitHub Actions: CI (lint + test) and Release (build .exe + GitHub Release)
- Apache-2.0 license
