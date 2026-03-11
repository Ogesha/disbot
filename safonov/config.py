import os
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()

# -------------------- ОСНОВНЫЕ ТОКЕНЫ --------------------
# Токен Discord бота (получается в Discord Developer Portal)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# -------------------- ПОДКЛЮЧЕНИЕ К БАЗЕ ДАННЫХ --------------------
# Настройки PostgreSQL
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", 5432))
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")
PG_DATABASE = os.getenv("PG_DATABASE", "discord_bot")

# -------------------- ЛОГИРОВАНИЕ В TELEGRAM --------------------
# Токен Telegram-бота и ID чата для отправки критических ошибок
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

# -------------------- ГИФКИ (глобальные, для всех серверов) --------------------
# Путь к папке с гифками
GIF_FOLDER = os.getenv("GIF_FOLDER", "./gifs/")
# Имена файлов гифок для разных событий
GIF_SAFONOV_OPLATIT = os.getenv("GIF_SAFONOV_OPLATIT", "safonov_oplatit.gif")
GIF_ILYA_MUROMETS = os.getenv("GIF_ILYA_MUROMETS", "ilya_muromets.gif")
# Список гифок для напоминаний (выбирается случайная)
GIF_REMINDER_LIST = os.getenv("GIF_REMINDER_LIST", "").split(',') if os.getenv("GIF_REMINDER_LIST") else []

# -------------------- НАПОМИНАНИЯ О ШТРАФАХ (глобальные) --------------------
# Эти настройки могут быть переопределены для каждой гильдии через БД,
# но здесь заданы значения по умолчанию.
REMINDER_ENABLED = os.getenv("REMINDER_ENABLED", "true").lower() == "true"
REMINDER_INTERVAL_HOURS = int(os.getenv("REMINDER_INTERVAL_HOURS", 24))
REMINDER_MESSAGE = os.getenv("REMINDER_MESSAGE", "Напоминание: у вас есть неоплаченный штраф {link}.")
REMINDER_LOG_ENABLED = os.getenv("REMINDER_LOG_ENABLED", "false").lower() == "true"
REMINDER_LOG_CHANNEL_ID = int(os.getenv("REMINDER_LOG_CHANNEL_ID", 0))
REMINDER_LOG_ROLE_ID = int(os.getenv("REMINDER_LOG_ROLE_ID", 0))

# -------------------- МОДЕРАЦИЯ (глобальный флаг включения) --------------------
MODERATION_ENABLED = os.getenv("MODERATION_ENABLED", "false").lower() == "true"
# Остальные настройки модерации хранятся в БД (MODERATION_CHANNELS, тайм-ауты и т.д.)

# -------------------- АНТИСПАМ (глобальный флаг включения) --------------------
ANTISPAM_ENABLED = os.getenv("ANTISPAM_ENABLED", "false").lower() == "true"
# Детальные настройки антиспама – в БД.

# -------------------- ПРОВЕРКА НОВЫХ ПОЛЬЗОВАТЕЛЕЙ (глобальный флаг) --------------------
NEW_MEMBER_VERIFICATION_ENABLED = os.getenv("NEW_MEMBER_VERIFICATION_ENABLED", "false").lower() == "true"
# Детали (минимальный возраст, роль, тайм-аут) – в БД.

# -------------------- ЗАЩИТА ОТ СНОСА (глобальный флаг) --------------------
ANTI_NUKE_ENABLED = os.getenv("ANTI_NUKE_ENABLED", "false").lower() == "true"
# Параметры защиты (лимиты, интервал, действие, белый список) – в БД.

# -------------------- АВТОМАТИЧЕСКИЙ БЭКАП (глобальные настройки) --------------------
BACKUP_ENABLED = os.getenv("BACKUP_ENABLED", "false").lower() == "true"
BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", 24))
BACKUP_FOLDER = os.getenv("BACKUP_FOLDER", "./backups/")
BACKUP_MAX_KEEP = int(os.getenv("BACKUP_MAX_KEEP", 5))
BACKUP_NOTIFY_CHANNEL_ID = int(os.getenv("BACKUP_NOTIFY_CHANNEL_ID", 0))

# -------------------- STALCRAFT API (глобальные) --------------------
STALCRAFT_CLIENT_ID = int(os.getenv("STALCRAFT_CLIENT_ID", 0))
STALCRAFT_CLIENT_SECRET = os.getenv("STALCRAFT_CLIENT_SECRET", "")
STALCRAFT_REGION = os.getenv("STALCRAFT_REGION", "eu")

# -------------------- КАНАЛЫ ДЛЯ КОМАНД (глобальные значения по умолчанию) --------------------
# Эти значения используются как fallback, если в БД ничего не задано.
COMMAND_CHANNEL_IDS = list(map(int, os.getenv("COMMAND_CHANNEL_IDS", "").split(','))) if os.getenv("COMMAND_CHANNEL_IDS") else []
LINK_CHANNEL_ID = int(os.getenv("LINK_CHANNEL_ID", 0))
LINK_COMMAND_CHANNEL_ID = int(os.getenv("LINK_COMMAND_CHANNEL_ID", 0))

# -------------------- РОЛИ НАКАЗАНИЙ (глобальные значения по умолчанию) --------------------
FINE_ROLE_ID = int(os.getenv("FINE_ROLE_ID", 0))
WARN_ROLE_1_ID = int(os.getenv("WARN_ROLE_1_ID", 0))
WARN_ROLE_2_ID = int(os.getenv("WARN_ROLE_2_ID", 0))
WARN_ROLE_3_ID = int(os.getenv("WARN_ROLE_3_ID", 0))

# -------------------- РОЛИ И ПРЕФИКСЫ ДЛЯ КЛАНОВ (глобальные значения по умолчанию) --------------------
# Эти значения будут переопределяться в БД для каждой гильдии.
CLAN1_NAME = os.getenv("CLAN1_NAME", "")
CLAN1_MEMBER_ROLE_IDS = list(map(int, os.getenv("CLAN1_MEMBER_ROLE_IDS", "").split(','))) if os.getenv("CLAN1_MEMBER_ROLE_IDS") else []
CLAN1_EX_MEMBER_ROLE_IDS = list(map(int, os.getenv("CLAN1_EX_MEMBER_ROLE_IDS", "").split(','))) if os.getenv("CLAN1_EX_MEMBER_ROLE_IDS") else []
CLAN1_HIGH_RANK_ROLE_IDS = list(map(int, os.getenv("CLAN1_HIGH_RANK_ROLE_IDS", "").split(','))) if os.getenv("CLAN1_HIGH_RANK_ROLE_IDS") else []
CLAN1_NICK_PREFIX = os.getenv("CLAN1_NICK_PREFIX", "")
CLAN1_EX_NICK_PREFIX = os.getenv("CLAN1_EX_NICK_PREFIX", "")
CLAN1_COMMAND_CHANNEL_ID = int(os.getenv("CLAN1_COMMAND_CHANNEL_ID", 0))

CLAN2_NAME = os.getenv("CLAN2_NAME", "")
CLAN2_MEMBER_ROLE_IDS = list(map(int, os.getenv("CLAN2_MEMBER_ROLE_IDS", "").split(','))) if os.getenv("CLAN2_MEMBER_ROLE_IDS") else []
CLAN2_EX_MEMBER_ROLE_IDS = list(map(int, os.getenv("CLAN2_EX_MEMBER_ROLE_IDS", "").split(','))) if os.getenv("CLAN2_EX_MEMBER_ROLE_IDS") else []
CLAN2_HIGH_RANK_ROLE_IDS = list(map(int, os.getenv("CLAN2_HIGH_RANK_ROLE_IDS", "").split(','))) if os.getenv("CLAN2_HIGH_RANK_ROLE_IDS") else []
CLAN2_NICK_PREFIX = os.getenv("CLAN2_NICK_PREFIX", "")
CLAN2_EX_NICK_PREFIX = os.getenv("CLAN2_EX_NICK_PREFIX", "")
CLAN2_COMMAND_CHANNEL_ID = int(os.getenv("CLAN2_COMMAND_CHANNEL_ID", 0))

# -------------------- КАНАЛЫ ДЛЯ ЛОГОВ (глобальные значения по умолчанию) --------------------
NEW_MEMBER_LOG_CHANNEL_ID = int(os.getenv("NEW_MEMBER_LOG_CHANNEL_ID", 0))
MEMBER_CHANGE_LOG_CHANNEL_ID = int(os.getenv("MEMBER_CHANGE_LOG_CHANNEL_ID", 0))
VIOLATION_LOG_CHANNEL_ID = int(os.getenv("VIOLATION_LOG_CHANNEL_ID", 0))