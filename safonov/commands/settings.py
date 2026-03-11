import discord
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput
import json
import os
import datetime
import config as bot_config
import utils
import logger
from db_client import db
from backup import backup_manager
from config_manager import config_manager

# ---------- Модальные окна ----------
class GeneralSettingsModal(Modal, title="Общие настройки"):
    allowed_roles = TextInput(label="ID ролей (через запятую)", placeholder="123,456", required=False)
    link_channel = TextInput(label="ID канала профиля", required=False)
    command_channels = TextInput(label="ID каналов команд (через запятую)", required=False)
    fine_expire_days = TextInput(label="Дней до первого варна за неуплату", required=False)
    punishment_expire_days = TextInput(label="Дней до автоснятия наказания", required=False)

    def __init__(self, current_config: dict):
        super().__init__()
        self.current_config = current_config
        self.allowed_roles.default = ','.join(str(x) for x in current_config.get('ALLOWED_ROLE_IDS', []))
        self.link_channel.default = str(current_config.get('LINK_CHANNEL_ID', ''))
        self.command_channels.default = ','.join(str(x) for x in current_config.get('COMMAND_CHANNEL_IDS', []))
        self.fine_expire_days.default = str(current_config.get('FINE_EXPIRE_DAYS', 7))
        self.punishment_expire_days.default = str(current_config.get('PUNISHMENT_EXPIRE_DAYS', 14))

    async def on_submit(self, interaction: discord.Interaction):
        new_config = self.current_config.copy()
        try:
            if self.allowed_roles.value:
                new_config['ALLOWED_ROLE_IDS'] = [int(x.strip()) for x in self.allowed_roles.value.split(',') if x.strip()]
            if self.link_channel.value:
                new_config['LINK_CHANNEL_ID'] = int(self.link_channel.value)
            if self.command_channels.value:
                new_config['COMMAND_CHANNEL_IDS'] = [int(x.strip()) for x in self.command_channels.value.split(',') if x.strip()]
            if self.fine_expire_days.value:
                new_config['FINE_EXPIRE_DAYS'] = int(self.fine_expire_days.value)
            if self.punishment_expire_days.value:
                new_config['PUNISHMENT_EXPIRE_DAYS'] = int(self.punishment_expire_days.value)
        except ValueError:
            await interaction.response.send_message("Неверный формат числа. Проверьте ввод.", ephemeral=True)
            return

        await db.save_server_config(interaction.guild_id, new_config)
        await config_manager.update_config(interaction.guild_id, new_config)
        embed = discord.Embed(title="✅ Общие настройки сохранены", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.send_tg_log(f"⚙️ {interaction.user} изменил общие настройки")

class ChannelSettingsModal(Modal, title="Настройка каналов логов"):
    log_channel = TextInput(label="ID канала логов (общий)", placeholder="123456789012345678", required=False)
    new_member_log = TextInput(label="ID канала новых участников", required=False)
    member_change_log = TextInput(label="ID канала изменений ролей", required=False)
    violation_log = TextInput(label="ID канала нарушений", required=False)

    def __init__(self, current_config: dict):
        super().__init__()
        self.current_config = current_config
        self.log_channel.default = str(current_config.get('LOG_CHANNEL_ID', ''))
        self.new_member_log.default = str(current_config.get('NEW_MEMBER_LOG_CHANNEL_ID', ''))
        self.member_change_log.default = str(current_config.get('MEMBER_CHANGE_LOG_CHANNEL_ID', ''))
        self.violation_log.default = str(current_config.get('VIOLATION_LOG_CHANNEL_ID', ''))

    async def on_submit(self, interaction: discord.Interaction):
        new_config = self.current_config.copy()
        try:
            if self.log_channel.value:
                new_config['LOG_CHANNEL_ID'] = int(self.log_channel.value)
            if self.new_member_log.value:
                new_config['NEW_MEMBER_LOG_CHANNEL_ID'] = int(self.new_member_log.value)
            if self.member_change_log.value:
                new_config['MEMBER_CHANGE_LOG_CHANNEL_ID'] = int(self.member_change_log.value)
            if self.violation_log.value:
                new_config['VIOLATION_LOG_CHANNEL_ID'] = int(self.violation_log.value)
        except ValueError:
            await interaction.response.send_message("ID каналов должны быть числами.", ephemeral=True)
            return

        await db.save_server_config(interaction.guild_id, new_config)
        await config_manager.update_config(interaction.guild_id, new_config)
        embed = discord.Embed(title="✅ Настройки каналов сохранены", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.send_tg_log(f"⚙️ {interaction.user} изменил настройки каналов логов")

class Clan1SettingsModal(Modal, title="Настройки клана 1"):
    clan_name = TextInput(label="Название клана", required=True)
    member_role_ids = TextInput(label="ID ролей членов (через запятую)", required=False)
    ex_role_ids = TextInput(label="ID ролей бывших (через запятую)", required=False)
    high_role_ids = TextInput(label="ID высоких ролей (через запятую)", required=False)
    nick_prefix = TextInput(label="Префикс члена", required=False)

    def __init__(self, current_config: dict):
        super().__init__()
        self.current_config = current_config
        self.clan_name.default = current_config.get('CLAN1_NAME', 'геймер')
        self.member_role_ids.default = ','.join(str(x) for x in current_config.get('CLAN1_MEMBER_ROLE_IDS', []))
        self.ex_role_ids.default = ','.join(str(x) for x in current_config.get('CLAN1_EX_MEMBER_ROLE_IDS', []))
        self.high_role_ids.default = ','.join(str(x) for x in current_config.get('CLAN1_HIGH_RANK_ROLE_IDS', []))
        self.nick_prefix.default = current_config.get('CLAN1_NICK_PREFIX', '[АЛЬЦ]')

    async def on_submit(self, interaction: discord.Interaction):
        new_config = self.current_config.copy()
        new_config['CLAN1_NAME'] = self.clan_name.value
        try:
            if self.member_role_ids.value:
                new_config['CLAN1_MEMBER_ROLE_IDS'] = [int(x.strip()) for x in self.member_role_ids.value.split(',') if x.strip()]
            if self.ex_role_ids.value:
                new_config['CLAN1_EX_MEMBER_ROLE_IDS'] = [int(x.strip()) for x in self.ex_role_ids.value.split(',') if x.strip()]
            if self.high_role_ids.value:
                new_config['CLAN1_HIGH_RANK_ROLE_IDS'] = [int(x.strip()) for x in self.high_role_ids.value.split(',') if x.strip()]
        except ValueError:
            await interaction.response.send_message("ID должны быть числами, разделёнными запятыми.", ephemeral=True)
            return
        new_config['CLAN1_NICK_PREFIX'] = self.nick_prefix.value or ''

        await db.save_server_config(interaction.guild_id, new_config)
        await config_manager.update_config(interaction.guild_id, new_config)
        embed = discord.Embed(title="✅ Настройки клана 1 сохранены", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.send_tg_log(f"⚙️ {interaction.user} изменил настройки клана 1")

class Clan2SettingsModal(Modal, title="Настройки клана 2"):
    clan_name = TextInput(label="Название клана", required=True)
    member_role_ids = TextInput(label="ID ролей членов (через запятую)", required=False)
    ex_role_ids = TextInput(label="ID ролей бывших (через запятую)", required=False)
    high_role_ids = TextInput(label="ID высоких ролей (через запятую)", required=False)
    nick_prefix = TextInput(label="Префикс члена", required=False)

    def __init__(self, current_config: dict):
        super().__init__()
        self.current_config = current_config
        self.clan_name.default = current_config.get('CLAN2_NAME', '')
        self.member_role_ids.default = ','.join(str(x) for x in current_config.get('CLAN2_MEMBER_ROLE_IDS', []))
        self.ex_role_ids.default = ','.join(str(x) for x in current_config.get('CLAN2_EX_MEMBER_ROLE_IDS', []))
        self.high_role_ids.default = ','.join(str(x) for x in current_config.get('CLAN2_HIGH_RANK_ROLE_IDS', []))
        self.nick_prefix.default = current_config.get('CLAN2_NICK_PREFIX', '')

    async def on_submit(self, interaction: discord.Interaction):
        new_config = self.current_config.copy()
        new_config['CLAN2_NAME'] = self.clan_name.value
        try:
            if self.member_role_ids.value:
                new_config['CLAN2_MEMBER_ROLE_IDS'] = [int(x.strip()) for x in self.member_role_ids.value.split(',') if x.strip()]
            if self.ex_role_ids.value:
                new_config['CLAN2_EX_MEMBER_ROLE_IDS'] = [int(x.strip()) for x in self.ex_role_ids.value.split(',') if x.strip()]
            if self.high_role_ids.value:
                new_config['CLAN2_HIGH_RANK_ROLE_IDS'] = [int(x.strip()) for x in self.high_role_ids.value.split(',') if x.strip()]
        except ValueError:
            await interaction.response.send_message("ID должны быть числами, разделёнными запятыми.", ephemeral=True)
            return
        new_config['CLAN2_NICK_PREFIX'] = self.nick_prefix.value or ''

        await db.save_server_config(interaction.guild_id, new_config)
        await config_manager.update_config(interaction.guild_id, new_config)
        embed = discord.Embed(title="✅ Настройки клана 2 сохранены", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.send_tg_log(f"⚙️ {interaction.user} изменил настройки клана 2")

class AntiNukeSettingsModal(Modal, title="Защита от сноса"):
    enabled = TextInput(label="Включить? (true/false)", required=False)
    action_limit = TextInput(label="Лимит действий за интервал", required=False)
    interval = TextInput(label="Интервал (секунд)", required=False)
    action = TextInput(label="Действие (ban/kick)", required=False)
    whitelist_roles = TextInput(label="ID ролей в белом списке (через запятую)", required=False)

    def __init__(self, current_config: dict):
        super().__init__()
        self.current_config = current_config
        self.enabled.default = str(current_config.get('ANTI_NUKE_ENABLED', False)).lower()
        self.action_limit.default = str(current_config.get('ANTI_NUKE_ACTION_LIMIT', 5))
        self.interval.default = str(current_config.get('ANTI_NUKE_INTERVAL_SECONDS', 10))
        self.action.default = current_config.get('ANTI_NUKE_ACTION', 'ban')
        self.whitelist_roles.default = ','.join(str(x) for x in current_config.get('ANTI_NUKE_WHITELIST_ROLE_IDS', []))

    async def on_submit(self, interaction: discord.Interaction):
        new_config = self.current_config.copy()
        try:
            if self.enabled.value:
                new_config['ANTI_NUKE_ENABLED'] = self.enabled.value.lower() == 'true'
            if self.action_limit.value:
                new_config['ANTI_NUKE_ACTION_LIMIT'] = int(self.action_limit.value)
            if self.interval.value:
                new_config['ANTI_NUKE_INTERVAL_SECONDS'] = int(self.interval.value)
            if self.action.value:
                new_config['ANTI_NUKE_ACTION'] = self.action.value
            if self.whitelist_roles.value:
                new_config['ANTI_NUKE_WHITELIST_ROLE_IDS'] = [int(x.strip()) for x in self.whitelist_roles.value.split(',') if x.strip()]
        except ValueError:
            await interaction.response.send_message("Неверный формат числа. Проверьте ввод.", ephemeral=True)
            return

        await db.save_server_config(interaction.guild_id, new_config)
        await config_manager.update_config(interaction.guild_id, new_config)
        embed = discord.Embed(title="✅ Настройки защиты сохранены", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.send_tg_log(f"⚙️ {interaction.user} изменил настройки анти-сноса")

class BackupSettingsModal(Modal, title="Настройки бэкапов"):
    interval = TextInput(label="Интервал (часы)", required=False)
    max_keep = TextInput(label="Максимум хранимых копий", required=False)
    notify_channel = TextInput(label="ID канала уведомлений", required=False)

    def __init__(self, current_config: dict):
        super().__init__()
        self.current_config = current_config
        self.interval.default = str(current_config.get('BACKUP_INTERVAL_HOURS', 24))
        self.max_keep.default = str(current_config.get('BACKUP_MAX_KEEP', 5))
        self.notify_channel.default = str(current_config.get('BACKUP_NOTIFY_CHANNEL_ID', ''))

    async def on_submit(self, interaction: discord.Interaction):
        new_config = self.current_config.copy()
        try:
            if self.interval.value:
                new_config['BACKUP_INTERVAL_HOURS'] = int(self.interval.value)
            if self.max_keep.value:
                new_config['BACKUP_MAX_KEEP'] = int(self.max_keep.value)
            if self.notify_channel.value:
                new_config['BACKUP_NOTIFY_CHANNEL_ID'] = int(self.notify_channel.value)
        except ValueError:
            await interaction.response.send_message("Неверный формат числа.", ephemeral=True)
            return

        await db.save_server_config(interaction.guild_id, new_config)
        await config_manager.update_config(interaction.guild_id, new_config)
        embed = discord.Embed(title="✅ Настройки бэкапов сохранены", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.send_tg_log(f"⚙️ {interaction.user} изменил настройки бэкапов")

# ---------- View для управления бэкапами ----------
class BackupActionView(View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="📁 Создать бэкап", style=discord.ButtonStyle.success)
    async def create_backup(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=False)
        try:
            backup_path = await backup_manager.create_backup(interaction.guild)
            embed = discord.Embed(
                title="✅ Бэкап создан",
                description=f"Файл: {os.path.basename(backup_path)}\nРазмер: {os.path.getsize(backup_path) / 1024:.2f} KB",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=False)
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=False)

    @discord.ui.button(label="📋 Список бэкапов", style=discord.ButtonStyle.secondary)
    async def list_backups(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=False)
        backups = []
        for filename in os.listdir(bot_config.BACKUP_FOLDER):
            if filename.startswith(f"backup_{interaction.guild.id}_") and filename.endswith(".zip"):
                filepath = os.path.join(bot_config.BACKUP_FOLDER, filename)
                size = os.path.getsize(filepath) / 1024
                mod_time = os.path.getmtime(filepath)
                backups.append((mod_time, filename, size))

        if not backups:
            await interaction.followup.send("Нет бэкапов для этого сервера.")
            return

        backups.sort(reverse=True)
        embed = discord.Embed(title="📋 Список бэкапов", color=discord.Color.blue())
        for mod_time, filename, size in backups[:10]:
            date = datetime.datetime.fromtimestamp(mod_time).strftime("%d.%m.%Y %H:%M")
            embed.add_field(name=filename, value=f"📅 {date}\n📦 {size:.1f} KB", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=False)

    @discord.ui.button(label="🔙 Назад", style=discord.ButtonStyle.danger)
    async def back(self, interaction: discord.Interaction, button: Button):
        cfg = await config_manager.get_config(interaction.guild_id)
        current_config = await db.get_server_config(interaction.guild_id) or cfg
        if not isinstance(current_config, dict):
            current_config = cfg
        view = SettingsView(current_config)
        embed = discord.Embed(
            title="⚙️ Настройки бота",
            description="Выберите раздел для редактирования.",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

# ---------- Главное меню настроек ----------
class SettingsView(View):
    def __init__(self, current_config: dict):
        super().__init__(timeout=180)
        self.current_config = current_config

    @discord.ui.button(label="Общие", style=discord.ButtonStyle.primary)
    async def general_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(GeneralSettingsModal(self.current_config))

    @discord.ui.button(label="Каналы логов", style=discord.ButtonStyle.primary)
    async def channels_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ChannelSettingsModal(self.current_config))

    @discord.ui.button(label="Клан 1", style=discord.ButtonStyle.secondary)
    async def clan1_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(Clan1SettingsModal(self.current_config))

    @discord.ui.button(label="Клан 2", style=discord.ButtonStyle.secondary)
    async def clan2_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(Clan2SettingsModal(self.current_config))

    @discord.ui.button(label="Защита от сноса", style=discord.ButtonStyle.danger)
    async def antinuke_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(AntiNukeSettingsModal(self.current_config))

    @discord.ui.button(label="Бэкапы", style=discord.ButtonStyle.success)
    async def backup_button(self, interaction: discord.Interaction, button: Button):
        view = BackupActionView()
        embed = discord.Embed(
            title="💾 Управление бэкапами",
            description="Выберите действие",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Закрыть", style=discord.ButtonStyle.danger)
    async def close_button(self, interaction: discord.Interaction, button: Button):
        await interaction.message.delete()

# ---------- Команда /settings ----------
@app_commands.command(name="settings", description="Настройка параметров бота (доступно в канале профиля)")
async def cmd_settings(interaction: discord.Interaction):
    try:
        cfg = await config_manager.get_config(interaction.guild_id)
        if interaction.channel_id != cfg.get('LINK_CHANNEL_ID'):
            await interaction.response.send_message("Эта команда доступна только в канале профиля.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)
        current_config = await db.get_server_config(interaction.guild_id) or cfg
        if not isinstance(current_config, dict):
            current_config = cfg
        view = SettingsView(current_config)
        embed = discord.Embed(
            title="⚙️ Настройки бота",
            description="Выберите раздел для редактирования.",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed, view=view)
    except Exception as e:
        print(f"❌ Ошибка в /settings: {type(e).__name__}: {e}")
        if interaction.response.is_done():
            await interaction.followup.send("Произошла внутренняя ошибка.", ephemeral=True)
        else:
            await interaction.response.send_message("Произошла внутренняя ошибка.", ephemeral=True)
