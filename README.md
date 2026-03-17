# Windows PC Controller Bot v3.2

Telegram-бот для удалённого управления Windows-компьютером.

## Возможности

- **Скриншот** — получение текущего экрана
- **Голос** — произнести текст через TTS (edge-tts / pyttsx3)
- **Громкость** — управление системной громкостью
- **Поиск на YouTube** — открыть видео в браузере
- **Системная информация** — CPU, RAM, диски
- **Управление пользователями** — whitelist (adduser / removeuser)
- **Выключение/перезагрузка** — команды питания
- **Inline-кнопки** — удобное меню управления

## Требования

- Python 3.10+
- Windows (основные функции используют Win32 API)

## Установка

```bash
# Клонировать репозиторий
git clone https://github.com/your_username/your_repo.git
cd your_repo/Bot

# Создать виртуальное окружение
python -m venv .venv
.venv\Scripts\activate

# Установить зависимости
pip install -r requirements.txt
```

## Настройка

1. Создайте бота через [@BotFather](https://t.me/BotFather) и получите токен.
2. Узнайте свой Telegram ID (например, через [@userinfobot](https://t.me/userinfobot)).
3. Скопируйте `.env.example` в `.env` и заполните:

```env
BOT_TOKEN=ваш_токен_бота
MASTER_ADMIN_ID=ваш_telegram_id
```

Или установите переменные окружения вручную перед запуском.

## Запуск

```bash
# Через Python
python bot_controller.py

# Через bat-файл (Windows)
start_bot.bat
```

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Главное меню |
| `/say <текст>` | Произнести текст |
| `/volume <0-100>` | Установить громкость |
| `/sc <запрос>` | Найти на YouTube |
| `/screenshot` | Скриншот экрана |
| `/sysinfo` | Информация о системе |
| `/adduser <id>` | Добавить пользователя (только admin) |
| `/removeuser <id>` | Удалить пользователя (только admin) |
| `/off` | Выключить ПК |

## Безопасность

- Бот работает по whitelist — только разрешённые пользователи могут отправлять команды
- `MASTER_ADMIN_ID` имеет полный доступ и не может быть удалён из whitelist
- Никогда не публикуйте токен бота в открытом виде

## Структура проекта

```
Bot/
├── bot_controller.py   # Основной файл бота
├── bot_config.json     # Конфигурация (громкость, TTS и т.д.)
├── whitelist.json      # Список разрешённых пользователей
├── requirements.txt    # Зависимости Python
├── start_bot.bat       # Быстрый запуск (Windows)
├── start_bot.vbs       # Запуск в фоне (Windows)
└── .env.example        # Шаблон переменных окружения
```
