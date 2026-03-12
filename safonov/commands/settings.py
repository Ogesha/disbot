import discord
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput, Select
import json
import os
import datetime
import config as bot_config
import utils
import logger
from db_client import db
from backup import backup_manager
from config_manager import config_manager


COMMAND_ACCESS_OPTIONS = [
    ("settings", "⚙️ settings"),
    ("профиль", "👤 профиль"),
    ("привязать", "🔗 привязать"),
    ("linklist", "📋 linklist"),
    ("поиск", "🔎 поиск"),
    ("штраф", "💸 штраф"),
    ("варн", "⚠️ варн"),
    ("оплата", "💰 оплата"),
    ("снять", "🧹 снять"),
    ("список", "📄 список"),
    ("редактировать_штраф", "✏️ редактировать_штраф"),
]


def _cfg_to_dict(cfg_obj):
    if isinstance(cfg_obj, dict):
        return dict(cfg_obj)
    data = getattr(cfg_obj, 'data', None)
    if isinstance(data, dict):
        return dict(data)
    return {}


class CommandSelect(Select):
    def __init__(self, parent_view: 'CommandAccessView'):
        options = [discord.SelectOption(label=label, value=value) for value, label in COMMAND_ACCESS_OPTIONS]
        super().__init__(placeholder="Выберите команду", min_values=1, max_values=1, options=options)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.selected_command = self.values[0]
        self.parent_view._load_selected_command()
        await self.parent_view.refresh_message(interaction)


class CommandChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, parent_view: 'CommandAccessView'):
        super().__init__(
            placeholder="Выберите каналы для команды",
            min_values=0,
            max_values=10,
            channel_types=[discord.ChannelType.text, discord.ChannelType.news, discord.ChannelType.forum],
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.channel_ids = [channel.id for channel in self.values]
        await self.parent_view.refresh_message(interaction)


class CommandLogChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, parent_view: 'CommandAccessView'):
        super().__init__(
            placeholder="Канал логов команды (опционально)",
            min_values=0,
            max_values=1,
            channel_types=[discord.ChannelType.text, discord.ChannelType.news, discord.ChannelType.forum],
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.log_channel_id = self.values[0].id if self.values else None
        await self.parent_view.refresh_message(interaction)


class CommandRoleSelect(discord.ui.RoleSelect):
    def __init__(self, parent_view: 'CommandAccessView'):
        super().__init__(placeholder="Выберите роли для команды", min_values=0, max_values=10)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.role_ids = [role.id for role in self.values]
        await self.parent_view.refresh_message(interaction)


class CommandAccessView(View):
    def __init__(self, current_config: dict):
        super().__init__(timeout=300)
        self.current_config = current_config
        self.command_access = dict(current_config.get('COMMAND_ACCESS', {}) or {})
        self.selected_command = COMMAND_ACCESS_OPTIONS[0][0]
        self.channel_ids = []
        self.role_ids = []
        self.log_channel_id = None

        self.command_select = CommandSelect(self)
        self.channel_select = CommandChannelSelect(self)
        self.log_channel_select = CommandLogChannelSelect(self)
        self.role_select = CommandRoleSelect(self)

        self.add_item(self.command_select)
        self.add_item(self.channel_select)
        self.add_item(self.log_channel_select)
        self.add_item(self.role_select)

        self._load_selected_command()

    def _load_selected_command(self):
        data = self.command_access.get(self.selected_command, {}) if isinstance(self.command_access, dict) else {}
        self.channel_ids = [int(x) for x in data.get('channel_ids', []) if str(x).isdigit()]
        self.role_ids = [int(x) for x in data.get('role_ids', []) if str(x).isdigit()]
        log_channel = data.get('log_channel_id')
        self.log_channel_id = int(log_channel) if str(log_channel).isdigit() else None

    def _create_embed(self, guild: discord.Guild):
        embed = discord.Embed(title="🎛️ Доступ к командам", color=discord.Color.blurple())
        embed.description = "Выберите команду, затем каналы и роли через выпадающие списки."

        channel_mentions = []
        for cid in self.channel_ids:
            channel = guild.get_channel(cid)
            channel_mentions.append(channel.mention if channel else f"`{cid}`")

        role_mentions = []
        for rid in self.role_ids:
            role = guild.get_role(rid)
            role_mentions.append(role.mention if role else f"`{rid}`")

        log_channel_text = "Не выбран"
        if self.log_channel_id:
            log_channel = guild.get_channel(self.log_channel_id)
            log_channel_text = log_channel.mention if log_channel else f"`{self.log_channel_id}`"

        embed.add_field(name="Команда", value=f"`/{self.selected_command}`", inline=False)
        embed.add_field(name="Каналы", value='\n'.join(channel_mentions) if channel_mentions else "Не выбраны", inline=False)
        embed.add_field(name="Роли", value='\n'.join(role_mentions) if role_mentions else "Не выбраны (доступ всем)", inline=False)
        embed.add_field(name="Канал логов", value=log_channel_text, inline=False)
        return embed

    async def refresh_message(self, interaction: discord.Interaction):
        embed = self._create_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="💾 Сохранить", style=discord.ButtonStyle.success, row=3)
    async def save_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        self.command_access[self.selected_command] = {
            'channel_ids': self.channel_ids,
            'role_ids': self.role_ids,
            'log_channel_id': self.log_channel_id,
        }
        self.current_config['COMMAND_ACCESS'] = self.command_access
        await config_manager.update_config(interaction.guild_id, self.current_config)
        logger.send_tg_log(f"⚙️ {interaction.user} изменил доступ команды /{self.selected_command}")
        embed = self._create_embed(interaction.guild)
        embed.set_footer(text="Сохранено")
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="🧹 Очистить для команды", style=discord.ButtonStyle.secondary, row=3)
    async def clear_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        self.command_access[self.selected_command] = {'channel_ids': [], 'role_ids': [], 'log_channel_id': None}
        self.current_config['COMMAND_ACCESS'] = self.command_access
        self.channel_ids = []
        self.role_ids = []
        self.log_channel_id = None
        await config_manager.update_config(interaction.guild_id, self.current_config)
        embed = self._create_embed(interaction.guild)
        embed.set_footer(text="Настройки команды очищены")
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="🔙 Назад", style=discord.ButtonStyle.danger, row=3)
    async def back_button(self, interaction: discord.Interaction, button: Button):
        cfg = await config_manager.get_config(interaction.guild_id)
        current_config = await db.get_server_config(interaction.guild_id)
        if not isinstance(current_config, dict):
            current_config = _cfg_to_dict(cfg)
        view = SettingsView(current_config)
        embed = discord.Embed(
            title="⚙️ Настройки бота",
            description="Выберите раздел для редактирования.",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)


# ---------- Модальные окна ----------


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
        current_config = await db.get_server_config(interaction.guild_id)
        if not isinstance(current_config, dict):
            current_config = _cfg_to_dict(cfg)
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

    @discord.ui.button(label="Клан 1", style=discord.ButtonStyle.secondary)
    async def clan1_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(Clan1SettingsModal(self.current_config))

    @discord.ui.button(label="Клан 2", style=discord.ButtonStyle.secondary)
    async def clan2_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(Clan2SettingsModal(self.current_config))

    @discord.ui.button(label="Защита от сноса", style=discord.ButtonStyle.danger)
    async def antinuke_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(AntiNukeSettingsModal(self.current_config))

    @discord.ui.button(label="Доступ команд", style=discord.ButtonStyle.secondary)
    async def command_access_button(self, interaction: discord.Interaction, button: Button):
        view = CommandAccessView(self.current_config)
        embed = view._create_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=view)

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
        allowed_channels, _ = utils.get_command_access(cfg, 'settings')
        if allowed_channels and interaction.channel_id not in allowed_channels:
            await interaction.response.send_message("Эта команда недоступна в этом канале.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)
        current_config = await db.get_server_config(interaction.guild_id)
        if not isinstance(current_config, dict):
            current_config = _cfg_to_dict(cfg)
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
