import discord
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput
from typing import Optional
import datetime
from datetime import timezone
import config  # глобальный для гифок и т.п.
import utils
import logger
from db_client import db
from stalcraft_client import stalcraft
from config_manager import config_manager

# ---------- Функция для создания embed профиля ----------
async def create_profile_embed(target: discord.Member, cfg, link_info, game_info):
    embed = discord.Embed(
        title=f"Профиль {target.display_name}",
        color=discord.Color.purple(),
        timestamp=datetime.datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Discord ID", value=target.id, inline=False)
    embed.add_field(name="Аккаунт создан", value=target.created_at.strftime("%d.%m.%Y %H:%M"), inline=True)
    embed.add_field(name="Присоединился", value=target.joined_at.strftime("%d.%m.%Y %H:%M") if target.joined_at else "неизвестно", inline=True)
    embed.add_field(name="Роли", value=", ".join([r.mention for r in target.roles[1:]]) or "нет", inline=False)

    puns = await db.get_user_active_punishments(target.id)
    embed.add_field(name="Активные наказания", value=str(len(puns)), inline=True)

    if link_info:
        embed.add_field(name="Stalcraft ник", value=game_info.get('account_name', link_info['game_nick']) if game_info else link_info['game_nick'], inline=True)
        embed.add_field(name="Регион", value=link_info['region'].upper(), inline=True)

        if game_info:
            clan = game_info.get('clan')
            if clan:
                clan_str = f"**{clan['name']}**"
                if clan.get('rank'):
                    rank_val = clan['rank'].value if hasattr(clan['rank'], 'value') else clan['rank']
                    clan_str += f"\nРанг: {rank_val}"
                if clan.get('join_time'):
                    clan_str += f"\nВступил: {clan['join_time'].strftime('%d.%m.%Y %H:%M')}"
                embed.add_field(name="Клан", value=clan_str, inline=False)
            else:
                embed.add_field(name="Клан", value="Не состоит", inline=False)

            if game_info.get('characters'):
                char = game_info['characters'][0]
                embed.add_field(name="Персонаж", value=char['name'], inline=True)
                embed.add_field(name="PvP убийства", value=char['pvp_kills'], inline=True)
                embed.add_field(name="PvP смерти", value=char['pvp_deaths'], inline=True)
                embed.add_field(name="K/D", value=char['kd'], inline=True)

            reg_date = game_info.get('registration_date') or game_info.get('created_at')
            if reg_date:
                embed.add_field(name="Аккаунт создан (игровой)", value=reg_date.strftime("%d.%m.%Y %H:%M"), inline=True)
            if game_info.get('last_login'):
                embed.add_field(name="Последний вход", value=game_info['last_login'].strftime("%d.%m.%Y %H:%M"), inline=True)
            embed.add_field(name="Времени сыграно (ч)", value=game_info.get('total_playtime_hours', 0), inline=True)
            embed.add_field(name="Активность в день (ч)", value=game_info.get('avg_daily_hours', 0), inline=True)
        else:
            embed.add_field(name="Stalcraft", value="Игрок не найден (возможно, неверный регион)", inline=False)
    else:
        embed.add_field(name="Stalcraft", value="Не привязан", inline=False)

    return embed

# ---------- Модальное окно для смены ника ----------
class ChangeNicknameModal(Modal, title="Изменение ника на сервере"):
    new_nickname = TextInput(label="Новый никнейм", placeholder="Введите новый ник", required=True, max_length=32)

    def __init__(self, member: discord.Member, cfg):
        super().__init__()
        self.member = member
        self.cfg = cfg

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.member.id and not any(role.id in self.cfg.get('ALLOWED_ROLE_IDS', []) for role in interaction.user.roles):
            await interaction.response.send_message("Вы не можете изменять ник другого пользователя.", ephemeral=True)
            return
        try:
            old_nick = self.member.display_name
            await self.member.edit(nick=self.new_nickname.value)
            await interaction.response.send_message(f"✅ Ник изменён на `{self.new_nickname.value}`", ephemeral=True)
            embed_log = discord.Embed(
                title="✏️ Изменение ника",
                description=f"{self.member.mention} изменил ник с `{old_nick}` на `{self.new_nickname.value}`",
                color=discord.Color.light_grey(),
                timestamp=datetime.datetime.now(timezone.utc)
            )
            await utils.send_user_log(interaction.guild, embed_log, self.cfg.get('MEMBER_CHANGE_LOG_CHANNEL_ID'))
        except discord.Forbidden:
            await interaction.response.send_message("❌ Недостаточно прав для изменения ника.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

# ---------- Кнопки для привязки Stalcraft ----------
class LinkButton(Button):
    def __init__(self, user_id: int, cfg):
        super().__init__(label="Привязать аккаунт", style=discord.ButtonStyle.success)
        self.user_id = user_id
        self.cfg = cfg

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LinkModal(self.user_id, self.cfg))

class EditLinkButton(Button):
    def __init__(self, user_id: int, current_nick: str, current_region: str, cfg):
        super().__init__(label="Изменить привязку", style=discord.ButtonStyle.primary)
        self.user_id = user_id
        self.current_nick = current_nick
        self.current_region = current_region
        self.cfg = cfg

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LinkModal(self.user_id, self.cfg, self.current_nick, self.current_region))

class UnlinkButton(Button):
    def __init__(self, user_id: int, cfg):
        super().__init__(label="Удалить привязку", style=discord.ButtonStyle.danger)
        self.user_id = user_id
        self.cfg = cfg

    async def callback(self, interaction: discord.Interaction):
        member = interaction.guild.get_member(self.user_id)
        if not member:
            await interaction.response.send_message("Пользователь не найден на сервере.", ephemeral=True)
            return

        await db.remove_game_link(self.user_id)

        # При удалении привязки вызываем мягкий режим (только клановые роли)
        changes, _ = await utils.apply_clan_status(member, {'clan': None}, self.cfg, dry_run=False)

        embed = discord.Embed(title="✅ Привязка удалена", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

        embed_log = discord.Embed(
            title="🗑️ Удаление привязки Stalcraft",
            description="\n".join(changes) if changes else f"Пользователь {member.mention} удалил привязку.",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(timezone.utc)
        )
        await utils.send_user_log(interaction.guild, embed_log, self.cfg.get('MEMBER_CHANGE_LOG_CHANNEL_ID'))

# ---------- Кнопка обновления данных ----------
class RefreshButton(Button):
    def __init__(self, target_user: discord.Member, current_user: discord.Member, link_info, can_moderate: bool, game_info, cfg):
        super().__init__(label="🔄 Обновить", style=discord.ButtonStyle.primary)
        self.target_user = target_user
        self.current_user = current_user
        self.link_info = link_info
        self.can_moderate = can_moderate
        self.game_info = game_info
        self.cfg = cfg

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        new_game_info = None
        if self.link_info:
            info = await stalcraft.get_player_info(self.link_info['game_nick'], region=self.link_info['region'])
            if info:
                new_game_info = info
                # Жёсткий режим при ручном обновлении (полный сброс)
                changes, _ = await utils.apply_clan_status(self.target_user, new_game_info, self.cfg, dry_run=False)
                if changes:
                    embed_log = discord.Embed(
                        title="🔄 Ручное обновление профиля",
                        description="\n".join(changes),
                        color=discord.Color.blue(),
                        timestamp=datetime.datetime.now(timezone.utc)
                    )
                    await utils.send_user_log(interaction.guild, embed_log, self.cfg.get('MEMBER_CHANGE_LOG_CHANNEL_ID'))
        new_embed = await create_profile_embed(self.target_user, self.cfg, self.link_info, new_game_info)
        can_moderate = any(role.id in self.cfg.get('ALLOWED_ROLE_IDS', []) for role in interaction.user.roles)
        new_view = ProfileView(self.target_user, self.current_user, self.link_info, can_moderate, new_game_info, self.cfg)
        await interaction.edit_original_response(embed=new_embed, view=new_view)

# ---------- Кнопка истории наказаний ----------
class PunishmentHistoryButton(Button):
    def __init__(self, user_id: int, cfg):
        super().__init__(label="История наказаний", style=discord.ButtonStyle.secondary)
        self.user_id = user_id
        self.cfg = cfg

    async def callback(self, interaction: discord.Interaction):
        rep, punishments = await db.get_user_history(self.user_id)
        if not punishments:
            embed = discord.Embed(title="История наказаний", description="Нет записей", color=discord.Color.blue())
        else:
            embed = discord.Embed(title=f"История наказаний {interaction.user.display_name}", color=discord.Color.blue())
            for p in punishments[:10]:
                issued = p['issued_at'].strftime("%d.%m.%Y")
                status = p['status']
                if status == 'active':
                    status_str = "активно"
                elif status == 'paid':
                    status_str = f"оплачен {p['paid_at'].strftime('%d.%m.%Y') if p['paid_at'] else ''}"
                elif status == 'removed':
                    status_str = f"снят {p['removed_at'].strftime('%d.%m.%Y') if p['removed_at'] else ''}"
                else:
                    status_str = status
                line = f"**{issued}** {p['type']}: {p['reason'][:50]} ({status_str})"
                embed.add_field(name=f"ID {p['id']}", value=line, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------- Модальное окно для снятия наказания ----------
class RemovePunishmentModal(Modal, title="Снять наказание"):
    punishment_id = TextInput(label="ID наказания", placeholder="Введите ID из /список", required=True)

    def __init__(self, target_user_id: int, cfg):
        super().__init__()
        self.target_user_id = target_user_id
        self.cfg = cfg

    async def on_submit(self, interaction: discord.Interaction):
        if not await utils.check_permissions(interaction, self.cfg):
            return
        try:
            pid = int(self.punishment_id.value)
        except ValueError:
            await interaction.response.send_message("ID должен быть числом.", ephemeral=True)
            return
        pun = await db.get_punishment_by_id(pid)
        if not pun or pun['user_id'] != self.target_user_id or pun['status'] != 'active':
            await interaction.response.send_message("Наказание не найдено или неактивно.", ephemeral=True)
            return
        await db.update_punishment_status(pid, 'removed')
        await utils.send_dm(interaction.guild.get_member(self.target_user_id), f"Наказание ID {pid} снято.")
        await interaction.response.send_message(f"✅ Наказание ID {pid} снято.", ephemeral=True)
        embed_log = discord.Embed(
            title="🔻 Снятие наказания",
            description=f" {interaction.user.mention} снял наказание ID {pid} для пользователя <@{self.target_user_id}>.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(timezone.utc)
        )
        await utils.send_user_log(interaction.guild, embed_log, self.cfg.get('MEMBER_CHANGE_LOG_CHANNEL_ID'))

class RemovePunishmentButton(Button):
    def __init__(self, target_user_id: int, cfg):
        super().__init__(label="Снять наказание", style=discord.ButtonStyle.danger)
        self.target_user_id = target_user_id
        self.cfg = cfg

    async def callback(self, interaction: discord.Interaction):
        if not await utils.check_permissions(interaction, self.cfg):
            return
        await interaction.response.send_modal(RemovePunishmentModal(self.target_user_id, self.cfg))

class CloseButton(Button):
    def __init__(self):
        super().__init__(label="Закрыть", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.message.delete()

# ---------- Модальное окно для привязки (LinkModal) ----------
class LinkModal(Modal, title="Привязка игрового аккаунта"):
    nickname = TextInput(label="Ник в Stalcraft", placeholder="Введите ваш ник", required=True)
    region = TextInput(label="Регион (eu/ru/dev)", placeholder="ru", required=False, default="ru")

    def __init__(self, user_id: int, cfg, original_nick: str = None, original_region: str = None):
        super().__init__()
        self.user_id = user_id
        self.cfg = cfg
        if original_nick:
            self.nickname.default = original_nick
        if original_region:
            self.region.default = original_region
        self.is_edit = original_nick is not None

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        region = self.region.value.lower()
        info = await stalcraft.get_player_info(self.nickname.value, region=region)
        if not info:
            embed = discord.Embed(
                title="❌ Ошибка",
                description=f"Игрок с ником **{self.nickname.value}** не найден в регионе {region.upper()}.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        await db.add_game_link(self.user_id, self.nickname.value, region)

        member = interaction.guild.get_member(self.user_id)
        if member:
            # Жёсткий режим при привязке (полный сброс, как при ручном обновлении)
            changes, _ = await utils.apply_clan_status(member, info, self.cfg, dry_run=False)
            if changes:
                embed_log = discord.Embed(
                    title="📌 Обновление после привязки",
                    description="\n".join(changes),
                    color=discord.Color.blue(),
                    timestamp=datetime.datetime.now(timezone.utc)
                )
                await utils.send_user_log(interaction.guild, embed_log, self.cfg.get('MEMBER_CHANGE_LOG_CHANNEL_ID'))

        embed = discord.Embed(
            title="✅ Привязка успешна",
            description=f"Пользователь <@{self.user_id}> привязан к игроку **{self.nickname.value}** (регион {region.upper()}).",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        embed_log = discord.Embed(
            title="📌 Привязка Stalcraft" + (" (изменение)" if self.is_edit else ""),
            description=f"{interaction.user.mention} {'изменил привязку' if self.is_edit else 'привязал'} для <@{self.user_id}>: ник **{self.nickname.value}** (регион {region.upper()})",
            color=discord.Color.green() if not self.is_edit else discord.Color.blue(),
            timestamp=datetime.datetime.now(timezone.utc)
        )
        await utils.send_user_log(interaction.guild, embed_log, self.cfg.get('MEMBER_CHANGE_LOG_CHANNEL_ID'))

# ---------- Кнопка изменения ника ----------
class ChangeNicknameButton(Button):
    def __init__(self, member: discord.Member, cfg):
        super().__init__(label="Изменить ник", style=discord.ButtonStyle.secondary)
        self.member = member
        self.cfg = cfg

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ChangeNicknameModal(self.member, self.cfg))

# ---------- Основное View профиля ----------
class ProfileView(View):
    def __init__(self, target_user: discord.Member, current_user: discord.Member, link_info, can_moderate: bool, game_info, cfg):
        super().__init__(timeout=180)
        self.target_user = target_user
        self.cfg = cfg
        # Кнопки привязки показываем, если это владелец или модератор
        if target_user.id == current_user.id or can_moderate:
            if link_info:
                self.add_item(EditLinkButton(target_user.id, link_info['game_nick'], link_info['region'], cfg))
                self.add_item(UnlinkButton(target_user.id, cfg))
            else:
                self.add_item(LinkButton(target_user.id, cfg))
        # Кнопка изменения ника (для себя или модератора)
        if target_user.id == current_user.id or can_moderate:
            self.add_item(ChangeNicknameButton(target_user, cfg))
        # Кнопка обновления данных (для всех)
        self.add_item(RefreshButton(target_user, current_user, link_info, can_moderate, game_info, cfg))
        self.add_item(PunishmentHistoryButton(target_user.id, cfg))
        if can_moderate:
            self.add_item(RemovePunishmentButton(target_user.id, cfg))
        self.add_item(CloseButton())

# ---------- Команда /профиль ----------
@app_commands.command(name="профиль", description="Показать профиль пользователя")
@app_commands.describe(пользователь="Пользователь (по умолчанию вы)")
async def cmd_profile(interaction: discord.Interaction, пользователь: Optional[discord.Member] = None):
    cfg = await config_manager.get_config(interaction.guild_id)

    # Проверка канала – используем LINK_CHANNEL_ID из конфига гильдии
    if interaction.channel_id != cfg.get('LINK_CHANNEL_ID'):
        await interaction.response.send_message("Эта команда доступна только в специальном канале для управления привязкой.", ephemeral=True)
        return

    if not await utils.check_role_only(interaction, cfg):
        return

    # Сразу подтверждаем команду, чтобы избежать "Приложение не отвечает"
    # при медленном ответе API Stalcraft.
    await interaction.response.defer(ephemeral=False)

    target = пользователь or interaction.user
    link = await db.get_game_link(target.id)
    game_info = None
    if link:
        info = await stalcraft.get_player_info(link['game_nick'], region=link['region'])
        if info:
            game_info = info

    embed = await create_profile_embed(target, cfg, link, game_info)
    can_moderate = any(role.id in cfg.get('ALLOWED_ROLE_IDS', []) for role in interaction.user.roles)
    view = ProfileView(target, interaction.user, link, can_moderate, game_info, cfg)
    await interaction.followup.send(embed=embed, view=view)
