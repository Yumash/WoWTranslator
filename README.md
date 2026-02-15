# WoW Chat Translator

Переводчик чата World of Warcraft в реальном времени. Companion app + мини-аддон для мультиязычных групп.

## Что делает

- Мониторит `WoWChatLog.txt` — WoW пишет туда непрерывно
- Определяет язык входящих сообщений (lingua-py)
- Переводит через DeepL API (fallback: Google Translate)
- Показывает переводы в **smart overlay** поверх WoW — стилизованном под нативный чат
- Позволяет **отвечать** на любом языке: набрал → перевёл → скопировал → Ctrl+V в WoW

## Архитектура

```
┌──────────────────────────────────────┐
│    World of Warcraft Client          │
│  [ChatTranslatorHelper addon]        │
│   • auto-enable /chatlog             │
│   • /wct — статус                    │
└──────────┬───────────────────────────┘
           │  WoWChatLog.txt (непрерывно)
           ▼
┌──────────────────────────────────────┐
│  Companion App (Python .exe)         │
│                                      │
│  File Watcher → Parser → Detector    │
│  → Cache (SQLite) → DeepL API       │
│  → Smart Overlay (PyQt6)            │
│                                      │
│  ┌────────────────────────────────┐  │
│  │  Overlay (как Discord overlay) │  │
│  │  Стилизован под WoW чат        │  │
│  │  Click-through / interactive   │  │
│  │  [Spieler]: Кто танкует?      │  │
│  │  [▼ DE ▾] Я танкую  [Send ➜] │  │
│  └────────────────────────────────┘  │
└──────────────────────────────────────┘
```

**Smart overlay** — не просто окно поверх WoW. Работает как Discord overlay:
- Click-through по умолчанию (клики проходят в WoW)
- Горячая клавиша переключает в интерактивный режим (ввод, настройки)
- Стилизован под WoW чат (тёмный фон, цвета каналов, WoW-шрифт)
- Работает в borderless fullscreen

## Стек

| Компонент | Технология |
|-----------|------------|
| Companion App | Python 3.12 |
| GUI / Overlay | PyQt6 (WS_EX_TRANSPARENT, click-through) |
| File Watcher | watchdog |
| Language Detection | lingua-py (оффлайн) |
| Translation | DeepL Free API (500K символов/мес) |
| Translation Fallback | googletrans |
| Cache | SQLite + in-memory LRU dict |
| Build | PyInstaller → single .exe |
| WoW Addon | Lua 5.1, ~100 строк |
| WoW Version | Midnight (Patch 12.0+) |

## Функции

### MVP
- Мониторинг WoWChatLog.txt в реальном времени (~1-2 сек задержка)
- Автоопределение языка входящих сообщений
- Перевод any → any (RU, EN, DE, FR, ES, PT, IT, KO, ZH)
- Smart overlay: стилизованный чат с фильтрами каналов (Party, Raid, Guild, Say, Whisper)
- Toggle «Переводить» (вкл/выкл) — экономия API квоты
- Ответ на любом языке: ввод → live preview перевода → clipboard
- Автоопределение языка собеседника для ответа
- Горячая клавиша: перевод из буфера обмена
- Системный трей
- Мини-аддон: авто-включение /chatlog

## Установка

### Companion App
```bash
# Из исходников
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app/main.py

# Или готовый .exe
WoWTranslator.exe
```

### WoW Addon
Скопировать `addon/ChatTranslatorHelper/` в `World of Warcraft/_retail_/Interface/AddOns/`

## Разработка

```bash
python app/main.py          # запуск
pytest                       # тесты
ruff check .                 # линтер
pyinstaller build.spec       # сборка .exe
```

## Ограничения

- **WoW Lua sandbox**: аддон не может делать HTTP-запросы — перевод только через companion app
- **Secret Values (Midnight)**: чат заблокирован для аддонов во время M+/PvP/boss — но WoWChatLog.txt не затронут
- **Отправка в WoW**: автоматическая вставка в чат невозможна (нарушение ToS) — только через clipboard + Ctrl+V
- **DeepL Free**: 500K символов/мес (~10K сообщений) — хватает для личного использования

## Соответствие ToS Blizzard

| Аспект | Статус |
|--------|--------|
| Чтение лог-файла с диска | Разрешено (Wowhead Client, WCL делают так же) |
| Overlay поверх окна | Разрешено (Discord Overlay работает так же) |
| Аддон включает /chatlog | Разрешено (штатная функция WoW) |
| Нет инъекции в процесс | Разрешено |
| Нет автоматизации действий | Разрешено |

## Лицензия

Private project.
