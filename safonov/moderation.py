import discord
import datetime
import re
import time
import aiohttp
from collections import defaultdict, deque
from datetime import timezone
import logger
from db_client import db
from stalcraft_client import stalcraft
import utils

# Запрещённые паттерны (ссылки, упоминания, реклама) – не зависят от конфига
FORBIDDEN_PATTERNS = [
    r'(https?://)?(www\.)?discord\.(com|gg)/[a-zA-Z0-9/?=&_-]+',
    r'(https?://)?(www\.)?discordapp\.(com|net)/[a-zA-Z0-9/?=&_-]+',
    r'(https?://)?(www\.)?canary\.discord\.com/[a-zA-Z0-9/?=&_-]+',
    r'(https?://)?(www\.)?ptb\.discord\.com/[a-zA-Z0-9/?=&_-]+',
    r'<#\d+>',
    r'(https?://)?(www\.)?t\.me/[a-zA-Z0-9_]+',
    r'(https?://)?(www\.)?telegram\.me/[a-zA-Z0-9_]+',
    r'(https?://)?(www\.)?telegram\.dog/[a-zA-Z0-9_]+',
    r'(https?://)?(www\.)?vk\.com/[a-zA-Z0-9_.-]+',
    r'(https?://)?(www\.)?instagram\.com/[a-zA-Z0-9_.-]+',
    r'(https?://)?(www\.)?youtube\.com/[a-zA-Z0-9?=&_-]+',
    r'(https?://)?(www\.)?youtu\.be/[a-zA-Z0-9_-]+',
    r'(https?://)?(www\.)?twitch\.tv/[a-zA-Z0-9_]+',
    r'(https?://)?(www\.)?twitter\.com/[a-zA-Z0-9_]+',
    r'(https?://)?(www\.)?x\.com/[a-zA-Z0-9_]+',
    r'(https?://)?(www\.)?facebook\.com/[a-zA-Z0-9_.-]+',
    r'(https?://)?(www\.)?tiktok\.com/@[a-zA-Z0-9_.-]+',
]

# Запрещённые слова (реклама, мат, спам) – можно вынести в БД, но пока оставим как есть
BAD_WORDS = [
    # Русский мат и оскорбления
    "хуй", "пизда", "блядь", "ебать", "нахер", "нахуй", "пошел нахуй", "иди нахуй",
    "сука", "падла", "гандон", "мудак", "дебил", "даун", "пидор", "пидорас",
    "шлюха", "проститутка", "мразь", "тварь", "ублюдок", "козел", "осел",
    "долбоеб", "ёбаный", "расист", "нацист", "чурка", "хач", "жид",

    # Английские аналоги
    "fuck", "shit", "asshole", "bitch", "cunt", "dick", "pussy", "bastard",
    "motherfucker", "whore", "slut", "nigger", "faggot", "retard", "spastic",

    # Реклама и спам
    "реклама", "подпишись", "заработок", "лохотрон", "развод", "кидалово",
    "бесплатно", "скачать бесплатно", "кряк", "взлом", "чит", "читы",
    "купить", "продажа", "магазин", "товар", "услуги", "работа",

    # Призывы к насилию/экстремизму
    "убить", "убиваю", "взорвать", "бомба", "теракт", "исламское государство",
    "халифат", "наци", "фашист", "скинхед", "ауе",

    "чит", "читы", "взлом", "взломать", "кряк", "крякнутый", "кейген", "таблетка",
    "бесплатные читы", "админка", "админ права", "мод меню", "моды", "донат",
    "бесплатный донат", "накрутка", "накрутить", "боты", "автокликер",
    "спам", "рассылка", "автосообщения",

    "наш сервер", "другой сервер", "новый сервер", "классный сервер",
    "заходите к нам", "приглашение", "инвайт", "invite", "discord.gg", "disboard",
    "топ сервер", "рейтинг серверов", "мониторинг", "голосуй", "голосование",
    "сервер"

    # Телефонные номера (регулярка не всегда эффективна, можно добавить паттерны)
    # r'\b8[ -]?\d{3}[ -]?\d{3}[ -]?\d{2}[ -]?\d{2}\b',  # Российские номера
    # r'\b\+7[ -]?\d{3}[ -]?\d{3}[ -]?\d{2}[ -]?\d{2}\b',
]

# Хранилище для антиспама (глобальное, но лимиты берутся из cfg)
user_message_times = defaultdict(lambda: deque(maxlen=5))  # maxlen будет заменяться динамически, но оставим 5 как запас

# ---------- Антиспам ----------
async def check_spam(message: discord.Message, cfg) -> bool:
    limit = cfg.get('ANTISPAM_MESSAGES_LIMIT', 5)
    interval = cfg.get('ANTISPAM_INTERVAL_SECONDS', 10)
    user_id = message.author.id
    times = user_message_times[user_id]
    # Ограничиваем очередь до limit, если limit изменился – просто берём последние limit записей
    # (можно было бы пересоздавать deque, но для простоты не будем)
    times.append(time.time())
    # Вычисляем временной промежуток для последних limit сообщений
    if len(times) > limit:
        # оставляем только последние limit
        while len(times) > limit:
            times.popleft()
    if len(times) == limit:
        time_span = times[-1] - times[0]
        if time_span <= interval:
            return True
    return False

async def apply_antispam_action(message: discord.Message, cfg):
    action = cfg.get('ANTISPAM_ACTION', 'timeout')
    try:
        if action == "timeout":
            duration = datetime.timedelta(minutes=cfg.get('ANTISPAM_TIMEOUT_MINUTES', 10))
            await message.author.timeout(duration, reason="Спам")
            result = f"тайм-аут на {cfg.get('ANTISPAM_TIMEOUT_MINUTES', 10)} мин."
        elif action == "warn":
            # Здесь можно реализовать выдачу варна через БД, если нужно
            result = "предупреждение (варн) – требуется реализация"
        elif action == "kick":
            await message.author.kick(reason="Спам")
            result = "кик"
        else:
            result = "действие не определено"
    except discord.Forbidden:
        result = "недостаточно прав"
    except Exception as e:
        result = f"ошибка: {e}"
    return result

# ---------- Проверка текста ----------
async def check_text(message: discord.Message, cfg) -> list:
    """Проверяет текст на запрещённые паттерны и слова (пока не зависит от cfg, но можно расширить)."""
    violations = []
    if not message.content:
        return violations
    content_lower = message.content.lower()
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, content_lower, re.IGNORECASE):
            violations.append(f"запрещённый паттерн: {pattern}")
            break
    for word in BAD_WORDS:
        if word in content_lower:
            violations.append(f"запрещённое слово: {word}")
            break
    return violations

# ---------- DiscordRep (отключен, но функции оставлены) ----------
async def check_discordrep(user_id: int):
    # не использует cfg, оставляем как есть
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.discordrep.com/v1/user/{user_id}", timeout=5) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    return None
    except Exception:
        return None

def evaluate_discordrep(data):
    # ...
    return None  # упрощённо

async def apply_discordrep_action(member: discord.Member, verdict: str):
    # ...
    return None

# ---------- Обработка нового участника ----------
async def handle_new_member(member: discord.Member, cfg):
    actions = []

    # Проверка возраста аккаунта
    if cfg.get('NEW_MEMBER_VERIFICATION_ENABLED'):
        now = datetime.datetime.now(timezone.utc)
        account_age = now - member.created_at
        min_age = datetime.timedelta(hours=cfg.get('NEW_MEMBER_MIN_ACCOUNT_AGE_HOURS', 24))
        if account_age < min_age:
            if cfg.get('NEW_MEMBER_TIMEOUT_MINUTES', 0) > 0:
                try:
                    duration = datetime.timedelta(minutes=cfg.get('NEW_MEMBER_TIMEOUT_MINUTES', 60))
                    await member.timeout(duration, reason="Аккаунт слишком новый")
                    actions.append(f"тайм-аут {cfg.get('NEW_MEMBER_TIMEOUT_MINUTES', 60)} мин. (новый аккаунт)")
                except discord.Forbidden:
                    actions.append("недостаточно прав для тайм-аута (новый аккаунт)")
            else:
                actions.append("аккаунт слишком новый (без тайм-аута)")

    # Выдача ограничительной роли
    restricted_role_id = cfg.get('NEW_MEMBER_RESTRICTED_ROLE_ID')
    if restricted_role_id:
        role = member.guild.get_role(restricted_role_id)
        if role:
            try:
                await member.add_roles(role, reason="Новый участник")
                actions.append(f"выдана роль {role.name}")
            except discord.Forbidden:
                actions.append("недостаточно прав для выдачи роли")
        else:
            actions.append("роль не найдена")

    # Отправляем лог в канал
    log_channel_id = cfg.get('NEW_MEMBER_LOG_CHANNEL_ID')
    if log_channel_id:
        channel = member.guild.get_channel(log_channel_id)
        if channel:
            embed = discord.Embed(
                title="🆕 Новый участник",
                description=f"{member.mention} ({member.id})",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now(timezone.utc)
            )
            embed.add_field(name="Аккаунт создан", value=member.created_at.strftime("%d.%m.%Y %H:%M:%S"), inline=True)
            embed.add_field(name="Возраст", value=str(datetime.datetime.now(timezone.utc) - member.created_at).split('.')[0], inline=True)
            if actions:
                embed.add_field(name="Действия", value="\n".join(actions), inline=False)
            await channel.send(embed=embed)

    # Лог в Telegram (опционально)
    logger.send_tg_log(f"👤 Новый участник {member} (ID: {member.id}): " + (", ".join(actions) if actions else "без действий"))

# ---------- Основная функция модерации сообщений ----------
async def handle_moderation(message: discord.Message, cfg):
    if message.author.bot:
        return False

    violations = []

    # Проверка текста
    text_violations = await check_text(message, cfg)
    if text_violations:
        violations.extend(text_violations)

    # Проверка вложений (исполняемые файлы)
    for attachment in message.attachments:
        if any(ext in attachment.filename.lower() for ext in ['.exe', '.scr', '.bat', '.cmd', '.vbs', '.js']):
            violations.append("подозрительное вложение (исполняемый файл)")
            break

    # Проверка на спам
    if await check_spam(message, cfg):
        violations.append("спам (превышение лимита сообщений)")

    if not violations:
        return False

    # Удаление сообщения (если включено)
    deleted_info = ""
    if cfg.get('MODERATION_DELETE_MESSAGE', True):
        try:
            await message.delete()
            deleted_info = "сообщение удалено"
        except discord.Forbidden:
            deleted_info = "не удалось удалить (недостаточно прав)"
        except discord.NotFound:
            deleted_info = "сообщение уже удалено"
        except Exception as e:
            deleted_info = f"ошибка удаления: {e}"
    else:
        deleted_info = "удаление отключено"

    # Применение действий
    timeout_info = ""
    if "спам" in violations:
        timeout_info = await apply_antispam_action(message, cfg)
    else:
        timeout_minutes = cfg.get('MODERATION_TIMEOUT_MINUTES', 15)
        if timeout_minutes > 0:
            try:
                duration = datetime.timedelta(minutes=timeout_minutes)
                await message.author.timeout(duration, reason="Нарушение правил")
                timeout_info = f"выдан тайм-аут на {timeout_minutes} мин."
            except discord.Forbidden:
                timeout_info = "не удалось выдать тайм-аут (недостаточно прав)"
            except Exception as e:
                timeout_info = f"ошибка тайм-аута: {e}"

    # Логирование в Discord
    log_channel_id = cfg.get('VIOLATION_LOG_CHANNEL_ID')
    if log_channel_id:
        log_channel = message.guild.get_channel(log_channel_id)
        if log_channel:
            embed = discord.Embed(
                title="Обнаружено нарушение",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now(timezone.utc)
            )
            embed.add_field(name="Пользователь", value=message.author.mention, inline=True)
            embed.add_field(name="Канал", value=message.channel.mention, inline=True)
            embed.add_field(name="ID сообщения", value=message.id, inline=False)
            embed.add_field(name="Текст сообщения", value=message.content or "нет текста", inline=False)
            embed.add_field(name="Причина", value=", ".join(violations), inline=False)
            embed.add_field(name="Действия", value=f"{deleted_info}\n{timeout_info}", inline=False)
            if message.attachments:
                files = ", ".join([f.filename for f in message.attachments])
                embed.add_field(name="Вложения", value=files, inline=False)
            await log_channel.send(embed=embed)

    # Логирование в Telegram
    logger.send_tg_log(f"🚫 Нарушение в #{message.channel.name}: {message.author} ({message.author.id}) - {violations}")

    return True