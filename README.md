# WoW Chat Translator

Переводчик чата World of Warcraft в реальном времени. Companion app + мини-аддон для мультиязычных групп.

## Что делает

- Перехватывает сообщения чата WoW в реальном времени (< 1 секунды)
- Определяет язык входящих сообщений (lingua-py, оффлайн)
- Переводит через DeepL API
- Показывает переводы в **smart overlay** поверх WoW — стилизованном под нативный чат
- Позволяет **отвечать** на любом языке: набрал → перевёл → скопировал → Ctrl+V в WoW
- Встроенный разговорник: ~45 фраз + 30 аббревиатур переводятся мгновенно без API

## Как это работает

### Проблема

WoW пишет чат в `WoWChatLog.txt`, но использует внутренний буфер ~4KB. Файл обновляется только когда буфер заполняется — реальная задержка **1-5 минут**. Для переводчика чата это неприемлемо.

Попытки обойти:
- `LoggingChat(false)/LoggingChat(true)` — НЕ флушит буфер в TWW 12.0.1
- Чтение CRT FILE* буфера из памяти WoW — WoW не использует stdio для чат-лога
- Поиск по таймстампам в памяти — находит стейл-копии в Lua string table

### Решение: ReadProcessMemory + Lua строка

Аддон перехватывает события чата (`CHAT_MSG_*`) напрямую через WoW API и записывает каждое сообщение в **Lua строку с уникальными маркерами**. Companion app находит эту строку в памяти процесса WoW через `ReadProcessMemory` и доставляет сообщения в пайплайн перевода.

```
┌──────────────────────────────────────────────────────────┐
│  World of Warcraft Client                                │
│                                                          │
│  ChatTranslatorHelper (addon)                            │
│  ├── CHAT_MSG_* events → ring buffer (50 msgs)           │
│  │   Каждое сообщение: SEQ|CHANNEL|Author-Server|Text    │
│  │                                                       │
│  └── ChatTranslatorHelperDB.wctbuf =                     │
│      "__WCT_BUF__1|GUILD|Артас-Сервер|Привет\n           │
│       2|WHISPER|Fury-Гордунни|Секрет\n__WCT_END__"       │
│                                                          │
│  Lua строка ─── непрерывный блок в heap ──────────────── │
└──────────┬───────────────────────────────────────────────┘
           │  ReadProcessMemory (каждые 500мс)
           │  Ищем маркер __WCT_BUF__ → читаем до __WCT_END__
           ▼
┌──────────────────────────────────────────────────────────┐
│  Companion App (Python .exe, запущено с правами админа)   │
│                                                          │
│  WoWAddonBufReader ──→ parse_line() ──→ Detector         │
│  (memory reader)       ↓                                 │
│                    Phrasebook ──→ Cache (SQLite)          │
│                        ↓                                 │
│                    DeepL API ──→ Smart Overlay (PyQt6)    │
│                                                          │
│  ┌────────────────────────────────────┐                  │
│  │  Overlay (как Discord overlay)     │                  │
│  │  Стилизован под WoW чат            │                  │
│  │  Click-through / interactive       │                  │
│  │  [Spieler]: Кто танкует? → Wer...  │                  │
│  │  [▼ DE ▾] Я танкую  [Копировать]   │                  │
│  └────────────────────────────────────┘                  │
│                                                          │
│  File Watcher (fallback) ─ полит WoWChatLog.txt каждую   │
│  секунду, подхватывает сообщения при flush буфера         │
└──────────────────────────────────────────────────────────┘
```

### Детали: аддон (Lua)

Аддон регистрируется на все события чата:
- `CHAT_MSG_SAY`, `CHAT_MSG_YELL`, `CHAT_MSG_PARTY`, `CHAT_MSG_RAID`
- `CHAT_MSG_GUILD`, `CHAT_MSG_OFFICER`, `CHAT_MSG_WHISPER`
- `CHAT_MSG_INSTANCE_CHAT` и другие

При каждом событии:
1. Увеличивает монотонный счётчик `seq`
2. Сериализует сообщение: `seq|CHANNEL|Author-Server|Text`
3. Добавляет в таблицу-аккумулятор (кольцевой буфер, 50 сообщений)
4. Пересобирает строку через `table.concat` с маркерами `__WCT_BUF__` / `__WCT_END__`
5. Записывает в `ChatTranslatorHelperDB.wctbuf` — SavedVariable, живёт в Lua heap

### Детали: companion app (Python)

`WoWAddonBufReader` в отдельном потоке:
1. **Attach**: подключается к процессу `Wow.exe` через pymem
2. **Scan**: ищет маркер `__WCT_BUF__` во всех readable memory regions (~1-3 сек)
3. **Poll**: каждые 500мс читает с cached адреса до `__WCT_END__`
4. **Parse**: разбирает `SEQ|CHANNEL|Author|Text`, пропускает уже виденные (`seq <= last_seq`)
5. **Deliver**: генерирует синтетическую log-строку → `parse_line()` → пайплайн перевода

Если маркер пропал (Lua GC пересоздал строку) — rescan. Если WoW закрылся — retry каждые 5 сек.

**Дедупликация**: memory reader доставляет мгновенно, file watcher — через 1-5 минут. Pipeline дедуплицирует по `(author, text)` с TTL 30 секунд.

### Пайплайн перевода

```
Сообщение → Аббревиатуры (phrasebook) → Детектор языка (lingua)
         → Фразы (phrasebook) → Кэш (SQLite) → DeepL API
         → Overlay
```

1. **Аббревиатуры** (pre-detector): `gg` → `хорошая игра`, `ty` → `спасибо` — мгновенно
2. **Детектор**: lingua-py определяет язык (оффлайн, ~1мс)
3. **Фразы** (post-detector): `hello` → `привет` по таблице EN/RU/DE/FR/ES
4. **Кэш**: SQLite хранит все ранее переведённые тексты
5. **DeepL API**: для всего остального, 500K символов/месяц бесплатно

### Smart overlay

- **Click-through** по умолчанию (клики проходят в WoW)
- **Горячая клавиша** переключает в интерактивный режим
- Стилизован под WoW чат: тёмный фон, цвета каналов (оранжевый = Party, синий = Raid, зелёный = Guild, белый = Say, розовый = Whisper)
- Фильтры каналов: Party, Raid, Guild, Say, Whisper, Instance
- Работает в borderless fullscreen

## Стек

| Компонент | Технология |
|-----------|------------|
| Companion App | Python 3.12 |
| GUI / Overlay | PyQt6 (WS_EX_TRANSPARENT, click-through) |
| Memory Reader | pymem (ReadProcessMemory) |
| File Watcher | polling (watchdog не подходит — WoW буферизирует) |
| Language Detection | lingua-py (оффлайн) |
| Translation | DeepL Free API (500K символов/мес) |
| Phrasebook | Встроенный: 45 фраз + 30 аббревиатур |
| Cache | SQLite + in-memory LRU dict |
| Build | PyInstaller → single .exe (с правами администратора) |
| WoW Addon | Lua 5.1, ~200 строк |
| WoW Version | The War Within / Midnight (12.0+) |

## Установка

### Companion App
```bash
# Из исходников
pip install -r requirements.txt
python -m app.main

# Или готовый .exe (запускать от администратора)
dist\WoWTranslator.exe
```

### WoW Addon
Скопировать `addon/ChatTranslatorHelper/` в `World of Warcraft/_retail_/Interface/AddOns/`

Или запустить companion app — он предложит установить аддон автоматически.

### Команды аддона
```
/wct            — статус (логирование, flush timer, буфер)
/wct buf        — информация о memory buffer (кол-во сообщений, seq)
/wct log on|off — вкл/выкл логирование чата
/wct flush on|off|<сек> — управление flush timer
/wct verbose on|off — подробные сообщения
```

## Разработка

```bash
python -m app.main          # запуск
pytest                       # тесты
ruff check app/ tests/       # линтер
pyinstaller build.spec       # сборка .exe
```

## Безопасность и защиты

| Сценарий | Защита |
|----------|--------|
| Переполнение буфера | Кольцевой буфер 50 сообщений, `tremove` удаляет старые |
| Lua GC переместил строку | Маркер проверяется на каждом poll, rescan при отсутствии |
| WoW crash/выход | pymem exception → detach → retry через 5 сек |
| Дубли (memory + file) | Дедупликация по (author, text) с TTL 30 сек |
| `\|` в тексте | `split("\|", 3)` — всё после 3-го пайпа = текст целиком |
| Кириллица в именах | UTF-8 decode с `errors="replace"` |
| Аддон не установлен | Маркер не найден → warning, fallback на file watcher |
| Чтение > 64KB | `MAX_BUF_READ` ограничивает read-ahead |

## Соответствие ToS Blizzard

| Аспект | Статус |
|--------|--------|
| Чтение памяти процесса (ReadProcessMemory) | Только чтение, Warden не флагит (аналог WeakAuras Companion, WCL) |
| Overlay поверх окна | Разрешено (Discord Overlay работает так же) |
| Аддон перехватывает CHAT_MSG_* | Штатное API WoW, используется всеми чат-аддонами |
| Нет инъекции кода в WoW | Разрешено |
| Нет автоматизации действий | Разрешено |
| Отправка через clipboard | Ctrl+V — действие игрока, не автоматизация |

## Ограничения

- **WoW Lua sandbox**: аддон не может делать HTTP-запросы — перевод только через companion app
- **Secret Values (Midnight)**: чат заблокирован для аддонов во время M+/PvP/boss — но CHAT_MSG_* события всё равно приходят
- **Отправка в WoW**: автоматическая вставка невозможна (нарушение ToS) — только clipboard + Ctrl+V
- **DeepL Free**: 500K символов/мес (~10K сообщений) — хватает для личного использования
- **Права администратора**: ReadProcessMemory требует запуска от администратора

## Лицензия

Private project.
