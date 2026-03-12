import discord
from discord import app_commands
from discord.ext import tasks
from discord.ui import View, Button
import asyncio
import random
import datetime
from datetime import timezone
import config
import logger
import moderation
import utils
from db_client import db
from stalcraft_client import stalcraft
from config_manager import config_manager
import antinuke
import backup
from antinuke import AntiNuke
from backup import BackupManager

# Импорт команд
from commands.fine import cmd_fine
from commands.warn import cmd_warn
from commands.pay import cmd_pay
from commands.remove import cmd_remove
from commands.list import cmd_list
from commands.edit_fine import cmd_edit_fine
from commands.search import cmd_search
from commands.link_list import cmd_link_list
from commands.profile import cmd_profile
from commands.note import note_group
from commands.link import cmd_link
from commands.settings import cmd_settings

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.moderation = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


@tree.interaction_check
async def no_dm_commands(interaction: discord.Interaction) -> bool:
    """Запрещаем использовать slash-команды в ЛС с ботом."""
    if interaction.guild is None:
        if interaction.response.is_done():
            await interaction.followup.send("Эти команды доступны только на сервере.", ephemeral=True)
        else:
            await interaction.response.send_message("Эти команды доступны только на сервере.", ephemeral=True)
        return False
    return True

# Глобальные переменные
antinuke = None
backup_manager = None
pending_clan_changes = {}  # guild_id -> {'text_changes': list[str], 'actions': list[tuple], 'not_found': list[str], 'log_channel_id': int}

# ---------- Добавление команд ----------
tree.add_command(cmd_fine)
tree.add_command(cmd_warn)
tree.add_command(cmd_pay)
tree.add_command(cmd_remove)
tree.add_command(cmd_list)
tree.add_command(cmd_edit_fine)
tree.add_command(cmd_search)
tree.add_command(cmd_link_list)
tree.add_command(cmd_profile)
tree.add_command(note_group)
tree.add_command(cmd_link)
tree.add_command(cmd_settings)

# ---------- View для подтверждения изменений кланов ----------
class ConfirmClanChangesView(View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)  # 5 минут
        self.guild_id = guild_id
        self.message = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

        data = pending_clan_changes.pop(self.guild_id, None)
        if not data:
            return

        guild = bot.get_guild(self.guild_id)
        if not guild:
            return

        log_channel = guild.get_channel(data.get('log_channel_id')) if data.get('log_channel_id') else None
        if not log_channel:
            return

        not_found = data.get('not_found', [])
        embed = discord.Embed(
            title="⏱️ Проверка кланов: время подтверждения истекло",
            description="Кнопки подтверждения скрыты (5 минут без ответа).",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(timezone.utc)
        )
        if not_found:
            embed.add_field(name="Не найдено в кланах", value="\n".join(not_found[:20]), inline=False)
        else:
            embed.add_field(name="Не найдено в кланах", value="Нет", inline=False)

        await log_channel.send(embed=embed)

    @discord.ui.button(label="✅ Подтвердить", style=discord.ButtonStyle.success)
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message("Эта кнопка не для этого сервера.", ephemeral=True)
            return

        data = pending_clan_changes.pop(self.guild_id, None)
        if not data:
            await interaction.response.send_message("Нет ожидающих изменений.", ephemeral=True)
            return

        text_changes = data.get('text_changes', [])
        actions = data.get('actions', [])
        guild = interaction.guild
        success = []
        failed = []

        for action in actions:
            try:
                if action[0] == 'add_role':
                    member = guild.get_member(action[1])
                    role = guild.get_role(action[2])
                    if member and role:
                        await member.add_roles(role, reason="Подтверждение изменений клана")
                        success.append(f"➕ {member.mention} + {role.name}")
                elif action[0] == 'remove_role':
                    member = guild.get_member(action[1])
                    role = guild.get_role(action[2])
                    if member and role:
                        await member.remove_roles(role, reason="Подтверждение изменений клана")
                        success.append(f"➖ {member.mention} - {role.name}")
                elif action[0] == 'edit_nick':
                    member = guild.get_member(action[1])
                    new_nick = action[2]
                    if member:
                        await member.edit(nick=new_nick)
                        success.append(f"✏️ {member.mention} новый ник: {new_nick}")
            except Exception as e:
                failed.append(f"Ошибка при {action}: {e}")

        embed = discord.Embed(
            title="✅ Изменения применены",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(timezone.utc)
        )
        if success:
            embed.add_field(name="Успешно", value="\n".join(success[:10]), inline=False)
        if failed:
            embed.add_field(name="Ошибки", value="\n".join(failed[:5]), inline=False)
        if not success and not failed:
            embed.description = "Никаких изменений не было произведено."

        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="❌ Отмена", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message("Эта кнопка не для этого сервера.", ephemeral=True)
            return

        pending_clan_changes.pop(self.guild_id, None)
        await interaction.response.edit_message(content="❌ Изменения отменены.", embed=None, view=None)

# ---------- Фоновые задачи ----------
@tasks.loop(minutes=30)
async def background_jobs():
    await bot.wait_until_ready()
    print("Запуск фоновых задач...")
    now = datetime.datetime.now(timezone.utc).replace(tzinfo=None)

    # Напоминания об оплате (глобальные)
    if config.REMINDER_ENABLED:
        for fine in await db.get_fines_for_reminder(config.REMINDER_INTERVAL_HOURS):
            user = bot.get_user(fine['user_id'])
            if user:
                guild = bot.get_guild(fine['guild_id'])
                if guild:
                    link = utils.create_message_link(guild.id, fine['channel_id'], fine['message_id'])
                    msg = config.REMINDER_MESSAGE.format(link=link)
                    gif = random.choice(config.GIF_REMINDER_LIST) if config.GIF_REMINDER_LIST else None
                    await utils.send_dm(user, msg, gif_filename=gif)
                    await db.update_last_reminded(fine['id'])
                    logger.send_tg_log(f"⏰ Напоминание #{fine['id']} отправлено {user.display_name}")
                    if config.REMINDER_LOG_ENABLED and config.REMINDER_LOG_CHANNEL_ID:
                        ch = guild.get_channel(config.REMINDER_LOG_CHANNEL_ID)
                        if ch:
                            role_mention = f"<@&{config.REMINDER_LOG_ROLE_ID}>" if config.REMINDER_LOG_ROLE_ID else ""
                            await ch.send(f"{role_mention} Напоминание {user.mention} по {link}")

    # Автовыдача варнов за неуплату (использует конфиг гильдии)
    for fine in await db.get_active_fines():
        guild = bot.get_guild(fine['guild_id'])
        if not guild:
            continue
        cfg = await config_manager.get_config(guild.id)
        days = (now - fine['issued_at']).days
        if days >= cfg.get('FINE_EXPIRE_DAYS', 7):
            expected_total = 1 + days // 7
            actual_total = await db.get_warn_count_for_fine(fine['id'])
            if expected_total > actual_total:
                for _ in range(expected_total - actual_total):
                    channel = bot.get_channel(fine['channel_id'])
                    if not channel:
                        continue
                    user = channel.guild.get_member(fine['user_id']) or bot.get_user(fine['user_id'])
                    if not user:
                        continue
                    reason = f"Неуплата штрафа (ID {fine['id']})"
                    embed = discord.Embed(title="Варн (автоматический)", description=f"{user.mention} – {reason}", color=discord.Color.orange())
                    msg = await channel.send(embed=embed)
                    wid = await db.add_punishment(
                        guild_id=guild.id,
                        user_id=user.id,
                        username=user.display_name if isinstance(user, discord.Member) else user.name,
                        p_type='warn',
                        amount=None,
                        reason=reason,
                        message_id=msg.id,
                        channel_id=channel.id,
                        fine_id=fine['id']
                    )
                    await db.add_punishment_history(
                        guild_id=guild.id,
                        user_id=user.id,
                        username=user.display_name if isinstance(user, discord.Member) else user.name,
                        p_type='warn',
                        amount=None,
                        reason=reason,
                        issued_at=datetime.datetime.now(timezone.utc).replace(tzinfo=None),
                        status='active',
                        message_id=msg.id,
                        channel_id=channel.id,
                        fine_id=fine['id']
                    )
                    link = utils.create_message_link(guild.id, fine['channel_id'], fine['message_id'])
                    await utils.send_dm(user, f"Ало альцгеймер? Вам выдан варн за просрочку оплаты штрафа. {link}")
                    if isinstance(user, discord.Member):
                        await utils.update_punishment_roles(user, guild, db, cfg)
                    if await db.get_warn_count(user.id) >= 3:
                        if isinstance(user, discord.Member):
                            await utils.notify_3_warns(user, guild, db, cfg)
                    logger.send_tg_log(f"🔄 Варн #{wid} за штраф #{fine['id']} для {user.display_name}")

    # Автоснятие варнов и штрафов (аналогично, опущено для краткости)
    # ...

@background_jobs.before_loop
async def before_bg():
    await bot.wait_until_ready()

# ---------- Задача проверки кланов (с подтверждением) ----------
@tasks.loop(minutes=10)
async def clan_check_loop():
    await bot.wait_until_ready()
    print("Запуск проверки кланов...")
    for guild in bot.guilds:
        cfg = await config_manager.get_config(guild.id)
        if not cfg:
            continue

        # Собираем все ID ролей, связанных с кланами (члены, бывшие, высокие)
        clan_role_ids = set()
        # Клан 1
        clan_role_ids.update(cfg.get('CLAN1_MEMBER_ROLE_IDS', []))
        clan_role_ids.update(cfg.get('CLAN1_HIGH_RANK_ROLE_IDS', []))
        # Клан 2
        clan_role_ids.update(cfg.get('CLAN2_MEMBER_ROLE_IDS', []))
        clan_role_ids.update(cfg.get('CLAN2_HIGH_RANK_ROLE_IDS', []))

        if not clan_role_ids:
            continue  # нет ролей клана – нечего проверять

        all_text_changes = []
        all_actions = []
        not_found_in_clans = []

        async with db.pool.acquire() as conn:
            rows = await conn.fetch('SELECT DISTINCT ON (discord_id) * FROM game_links ORDER BY discord_id, last_updated DESC')
        for row in rows:
            member = guild.get_member(row['discord_id'])
            if not member:
                continue

            # Пользователи без клановой/высокой роли автоматической проверке не подлежат
            if not any(role.id in clan_role_ids for role in member.roles):
                continue

            info = await stalcraft.get_player_info(row['game_nick'], region=row['region'])
            if not info:
                continue

            player_clan = (info.get('clan') or {}).get('name', '').lower()
            valid_clans = {str(cfg.get('CLAN1_NAME', '')).lower(), str(cfg.get('CLAN2_NAME', '')).lower()}
            valid_clans.discard('')
            if player_clan not in valid_clans:
                not_found_in_clans.append(member.mention)

            text_changes, actions = await utils.apply_clan_status(member, info, cfg, dry_run=True)
            all_text_changes.extend(text_changes)
            all_actions.extend(actions)

        if all_text_changes:
            log_channel_id = cfg.get('AUTO_CLAN_CHECK_LOG_CHANNEL_ID') or cfg.get('MEMBER_CHANGE_LOG_CHANNEL_ID')
            pending_clan_changes[guild.id] = {
                'text_changes': all_text_changes,
                'actions': all_actions,
                'not_found': not_found_in_clans,
                'log_channel_id': log_channel_id,
            }
            embed = discord.Embed(
                title="📋 Результаты проверки кланов (требуется подтверждение)",
                description="\n".join(all_text_changes[:20]) + ("\n..." if len(all_text_changes) > 20 else ""),
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now(timezone.utc)
            )
            embed.set_footer(text="Нажмите Подтвердить, чтобы применить изменения, или Отмена для отмены.")

            view = ConfirmClanChangesView(guild.id)
            log_channel = guild.get_channel(cfg.get('AUTO_CLAN_CHECK_LOG_CHANNEL_ID') or cfg.get('MEMBER_CHANGE_LOG_CHANNEL_ID'))
            if log_channel:
                msg = await log_channel.send(embed=embed, view=view)
                view.message = msg
            else:
                logger.send_tg_log(f"⚠️ Не найден канал логов для сервера {guild.name}")

@clan_check_loop.before_loop
async def before_clan_check():
    await bot.wait_until_ready()

# ---------- Задача автоматического бэкапа ----------
@tasks.loop(hours=config.BACKUP_INTERVAL_HOURS)
async def backup_loop():
    await bot.wait_until_ready()
    if not config.BACKUP_ENABLED:
        return
    for guild in bot.guilds:
        try:
            backup_path = await backup_manager.create_backup(guild)
            if config.BACKUP_NOTIFY_CHANNEL_ID:
                channel = guild.get_channel(config.BACKUP_NOTIFY_CHANNEL_ID)
                if channel:
                    embed = discord.Embed(
                        title="💾 Автоматический бэкап создан",
                        description=f"Бэкап сервера **{guild.name}** успешно создан",
                        color=discord.Color.green(),
                        timestamp=datetime.datetime.now(timezone.utc)
                    )
                    embed.add_field(name="Файл", value=os.path.basename(backup_path), inline=False)
                    embed.add_field(name="Размер", value=f"{os.path.getsize(backup_path) / 1024:.2f} KB", inline=True)
                    await channel.send(embed=embed)
        except Exception as e:
            logger.send_tg_log(f"❌ Ошибка бэкапа для {guild.name}: {e}")

@backup_loop.before_loop
async def before_backup():
    await bot.wait_until_ready()

# ---------- Обработчики событий ----------
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Бот не обрабатывает личные сообщения
    if message.guild is None:
        return

    await db.update_user_last_seen(message.author.id, message.author.display_name)
    if config.MODERATION_ENABLED:
        cfg = await config_manager.get_config(message.guild.id)
        if message.channel.id in cfg.get('MODERATION_CHANNELS', []):
            await moderation.handle_moderation(message, cfg)
    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    await db.update_user_last_seen(member.id, member.display_name)

@bot.event
async def on_member_join(member):
    cfg = await config_manager.get_config(member.guild.id)
    await moderation.handle_new_member(member, cfg)

@bot.event
async def on_member_remove(member):
    cfg = await config_manager.get_config(member.guild.id)
    async with db.pool.acquire() as conn:
        active = await conn.fetch('SELECT * FROM punishments WHERE user_id = $1 AND guild_id = $2', member.id, member.guild.id)
        count = len(active)
        for pun in active:
            await db.add_punishment_history(
                guild_id=member.guild.id,
                user_id=member.id,
                username=member.display_name,
                p_type=pun['type'],
                amount=pun['amount'],
                reason=pun['reason'],
                issued_at=pun['issued_at'],
                paid_at=pun['paid_at'],
                removed_at=datetime.datetime.now(timezone.utc).replace(tzinfo=None),
                status='removed',
                message_id=pun['message_id'],
                channel_id=pun['channel_id'],
                fine_id=pun['fine_id']
            )
        await conn.execute('DELETE FROM punishments WHERE user_id = $1 AND guild_id = $2', member.id, member.guild.id)

    embed = discord.Embed(
        title="👋 Пользователь покинул сервер",
        description=f"{member.mention} ({member.id})",
        color=discord.Color.orange(),
        timestamp=datetime.datetime.now(timezone.utc)
    )
    embed.add_field(name="Активных наказаний перенесено в историю", value=str(count))
    if member.joined_at:
        embed.add_field(name="Присоединился", value=member.joined_at.strftime("%d.%m.%Y %H:%M"))

    await utils.send_user_log(member.guild, embed, cfg.get('NEW_MEMBER_LOG_CHANNEL_ID'))
    logger.send_tg_log(f"👋 Пользователь {member.display_name} (ID: {member.id}) покинул {member.guild.name}, наказаний перенесено: {count}")

@bot.event
async def on_member_update(before, after):
    cfg = await config_manager.get_config(after.guild.id)
    if before.nick != after.nick:
        embed_log = discord.Embed(
            title="✏️ Изменение ника (вручную)",
            description=f"{after.mention} изменил ник с `{before.nick or 'отсутствует'}` на `{after.nick or 'отсутствует'}`",
            color=discord.Color.light_grey(),
            timestamp=datetime.datetime.now(timezone.utc)
        )
        await utils.send_user_log(after.guild, embed_log, cfg.get('MEMBER_CHANGE_LOG_CHANNEL_ID'))

    before_role_ids = {role.id for role in before.roles}
    after_role_ids = {role.id for role in after.roles}
    added_clan_roles = set(cfg.get('CLAN1_MEMBER_ROLE_IDS', []) + cfg.get('CLAN2_MEMBER_ROLE_IDS', [])) & (after_role_ids - before_role_ids)
    if added_clan_roles:
        roles_list = ", ".join([f"<@&{rid}>" for rid in added_clan_roles])
        embed_log = discord.Embed(
            title="➕ Добавлена роль клана",
            description=f"{after.mention} получил роль(и): {roles_list}",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(timezone.utc)
        )
        await utils.send_user_log(after.guild, embed_log, cfg.get('MEMBER_CHANGE_LOG_CHANNEL_ID'))

    removed_clan_roles = set(cfg.get('CLAN1_MEMBER_ROLE_IDS', []) + cfg.get('CLAN2_MEMBER_ROLE_IDS', [])) & (before_role_ids - after_role_ids)
    if removed_clan_roles:
        roles_list = ", ".join([f"<@&{rid}>" for rid in removed_clan_roles])
        embed_log = discord.Embed(
            title="➖ Удалена роль клана",
            description=f"{after.mention} лишился роли(ей): {roles_list}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(timezone.utc)
        )
        await utils.send_user_log(after.guild, embed_log, cfg.get('MEMBER_CHANGE_LOG_CHANNEL_ID'))

# ---------- Обработчики анти-рейд защиты (кратко) ----------
@bot.event
async def on_guild_channel_delete(channel):
    if not config.ANTI_NUKE_ENABLED:
        return
    cfg = await config_manager.get_config(channel.guild.id)
    async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
        await antinuke.check_action(entry.user.id, 'channel_delete', channel.guild, cfg)

# ... аналогично для других событий (опущено для краткости)

# ---------- Обработчик готовности ----------
@bot.event
async def on_ready():
    print("✅ on_ready начат")
    print(f"Бот {bot.user} запущен")
    print("▶️ Загружаем конфиги гильдий...")
    await config_manager.load_all_guilds([guild.id for guild in bot.guilds])
    print("✅ Конфиги загружены")
    print("▶️ Инициализируем AntiNuke...")
    global antinuke, backup_manager
    antinuke = AntiNuke(bot)
    print("✅ AntiNuke инициализирован")
    print("▶️ Инициализируем BackupManager...")
    backup_manager = BackupManager(bot)
    print("✅ BackupManager инициализирован")
    print("▶️ Синхронизируем команды...")
    await tree.sync()
    print("✅ Команды синхронизированы")
    print("▶️ Запускаем фоновые задачи...")
    background_jobs.start()
    clan_check_loop.start()
    if config.BACKUP_ENABLED:
        backup_loop.start()
    print("✅ Все задачи запущены")
    logger.send_tg_log(f"🤖 Бот {bot.user} запущен и готов к работе")

async def main():
    await db.connect()
    print("✅ База данных подключена")
    try:
        await bot.start(config.DISCORD_TOKEN)
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())
