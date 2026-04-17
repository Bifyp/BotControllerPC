<div align="center">

```
██████╗  ██████╗    ██████╗ ████████╗██████╗██╗     
██╔══██╗██╔════╝   ██╔════╝╚══██╔══╝██╔══██╗██║     
██████╔╝██║        ██║        ██║   ██████╔╝██║     
██╔═══╝ ██║        ██║        ██║   ██╔══██╗██║     
██║     ╚██████╗   ╚██████╗   ██║   ██║  ██║███████╗
╚═╝      ╚═════╝    ╚═════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝

     ██████╗  ██████╗ ████████╗    ██╗   ██╗██████╗ 
     ██╔══██╗██╔═══██╗╚══██╔══╝    ██║   ██║╚════██╗
     ██████╔╝██║   ██║   ██║       ██║   ██║ █████╔╝
     ██╔══██╗██║   ██║   ██║        ██╗ ██╔╝ ╚═══██╗
     ██████╔╝╚██████╔╝   ██║         ╚████╔╝ ██████╔╝
     ╚═════╝  ╚═════╝    ╚═╝          ╚═══╝  ╚═════╝ 
```

**`// WINDOWS PC CONTROLLER BOT v3.2`**

*telegram-бот · удалённое управление · Win32 API · whitelist-безопасность*

---

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Telegram](https://img.shields.io/badge/Telegram-Bot_API-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![Windows](https://img.shields.io/badge/Windows-Win32_API-0078D4?style=for-the-badge&logo=windows&logoColor=white)](https://github.com)
[![TTS](https://img.shields.io/badge/TTS-edge--tts%20%7C%20pyttsx3-FF007A?style=for-the-badge)](https://github.com)
[![Security](https://img.shields.io/badge/Security-Whitelist-00FFCC?style=for-the-badge)](https://github.com)

</div>

---

```
  ╔══════════════════════════════════════════════════════════════════════╗
  ║                                                                      ║
  ║   TELEGRAM CLIENT          INTERNET           WINDOWS HOST           ║
  ║   ────────────────         ────────           ─────────────────      ║
  ║   [ /screenshot ]  ──━━━━━━━━━━━━━━━━━━━━━  bot_controller.py        ║
  ║   [ /sysinfo     ]                            ├── Win32 API          ║
  ║   [ /say <text>  ]  ━━━━━━━━━━━━━━━━━━━━━━  ├── TTS Engine           ║
  ║   [ /volume 80   ]                            ├── Volume Control     ║
  ║   [ /off         ]                            └── Power Management   ║
  ║                                                                      ║
  ║   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░     ║
  ║   STATUS: // ONLINE   ▌  SECURITY: WHITELIST   ▌  OS: WINDOWS        ║
  ╚══════════════════════════════════════════════════════════════════════╝
```

---

## `> SYSTEM.FEATURES`

| МОДУЛЬ | ОПИСАНИЕ | СТАТУС |
|:-------|:---------|:------:|
| `SCREENSHOT` | Захват и отправка текущего экрана | `[ACTIVE]` |
| `TTS_ENGINE` | Произнести текст через edge-tts / pyttsx3 | `[ACTIVE]` |
| `VOLUME_CTRL` | Управление системной громкостью (0–100) | `[ACTIVE]` |
| `YOUTUBE` | Поиск и открытие видео в браузере | `[ACTIVE]` |
| `SYSINFO` | CPU · RAM · диски — в реальном времени | `[ACTIVE]` |
| `USER_MGMT` | Whitelist: adduser / removeuser (только admin) | `[ACTIVE]` |
| `POWER_CTRL` | Выключение и перезагрузка ПК | `[ACTIVE]` |
| `INLINE_MENU` | Inline-кнопки — удобное меню управления | `[ACTIVE]` |

---

## `> QUICK.BOOT`

### Требования

```
Runtime   ─── Python 3.10+
Platform  ─── Windows (Win32 API)
Account   ─── Telegram Bot Token (@BotFather)
```

### `// STEP 1 — клонирование`

```bash
git clone https://github.com/Bifyp/BotControllerPC
cd BotControllerPC/Bot
```

### `// STEP 2 — виртуальное окружение`

```bash
python -m venv .venv
.venv\Scripts\activate
```

### `// STEP 3 — зависимости`

```bash
pip install -r requirements.txt
```

### `// STEP 4 — переменные окружения`

```bash
cp .env.example .env
```

Заполните `.env`:

```env
# ── BOT ───────────────────────────────────────────
BOT_TOKEN=ваш_токен_бота

# ── ACCESS CONTROL ────────────────────────────────
MASTER_ADMIN_ID=ваш_telegram_id
```

> Получить токен — `@BotFather` · Узнать свой ID — `@userinfobot`

### `// STEP 5 — запуск`

```bash
# Через Python
python bot_controller.py

# Через bat-файл (Windows)
start_bot.bat
```

---

## `> COMMAND.TABLE`

```
╔═══════════════════════════╦══════════════════════════════════════════╗
║   КОМАНДА                 ║   ОПИСАНИЕ                               ║
╠═══════════════════════════╬══════════════════════════════════════════╣
║  /start                   ║  Главное меню                            ║
║  /screenshot              ║  Скриншот экрана                         ║
║  /sysinfo                 ║  CPU · RAM · диски                       ║
╠═══════════════════════════╬══════════════════════════════════════════╣
║  /say <текст>             ║  Произнести текст (TTS)                  ║
║  /volume <0-100>          ║  Установить громкость                    ║
║  /sc <запрос>             ║  Найти на YouTube                        ║
╠═══════════════════════════╬══════════════════════════════════════════╣
║  /adduser <id>          ║  Добавить пользователя в whitelist         ║
║  /removeuser <id>       ║  Удалить пользователя из whitelist         ║
║  /off                   ║  Выключить ПК                              ║
╚═══════════════════════════╩══════════════════════════════════════════╝
                                                         только admin
```

---

## `> SECURITY.PROTOCOL`

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   [!] WHITELIST MODE                                            │
│       Только разрешённые пользователи могут отправлять команды  │
│                                                                 │
│   [!] MASTER_ADMIN_ID                                           │
│       Полный доступ · не может быть удалён из whitelist         │
│                                                                 │
│   [!] BOT TOKEN                                                 │
│       Никогда не публикуйте токен в открытом виде               │
│       Не коммитьте .env в репозиторий                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## `> ARCHITECTURE.MAP`

```
Bot/
│
├── bot_controller.py     основной файл бота
├── bot_config.json       конфигурация (громкость, TTS и т.д.)
├── whitelist.json        список разрешённых пользователей
├── requirements.txt      зависимости Python
│
├── start_bot.bat         быстрый запуск (Windows)
├── start_bot.vbs         запуск в фоне (Windows)
│
└── .env.example          шаблон переменных окружения
```

---

<div align="center">

```
 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
 ░                                                    ░
 ░       // YOUR PC.  YOUR RULES.  ANYWHERE.          ░
 ░                  PC CTRL BOT v3.2                  ░
 ░                                                    ░
 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
```

</div>
