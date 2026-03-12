import discord
import os
import re
import datetime
from datetime import timezone
from typing import List, Tuple
import logger
from db_client import db
from config_manager import config_manager


def _normalize_ids(values) -> List[int]:
    if not values:
        return []
    normalized = []
    for value in values:
        try:
            normalized.append(int(value))
        except (TypeError, ValueError):
            continue
    return normalized


def get_command_access(cfg, command_name: str) -> Tuple[List[int], List[int]]:
    command_name = (command_name or '').lower()
    access_map = cfg.get('COMMAND_ACCESS', {}) or {}
    command_data = access_map.get(command_name, {}) if isinstance(access_map, dict) else {}

    channel_ids = _normalize_ids(command_data.get('channel_ids', []))
    role_ids = _normalize_ids(command_data.get('role_ids', []))

    if not channel_ids:
        if command_name in {'штраф', 'варн', 'оплата', 'снять', 'список', 'редактировать_штраф'}:
            channel_ids = _normalize_ids([cfg.get('CLAN1_COMMAND_CHANNEL_ID'), cfg.get('CLAN2_COMMAND_CHANNEL_ID')])
        elif command_name in {'профиль', 'привязать', 'linklist', 'settings', 'unlink', 'изменить'}:
            channel_ids = _normalize_ids([cfg.get('LINK_CHANNEL_ID')])
        elif command_name in {'поиск'}:
            channel_ids = _normalize_ids([cfg.get('SEARCH_CHANNEL_ID')])
        else:
            channel_ids = _normalize_ids(cfg.get('COMMAND_CHANNEL_IDS', []))

    if not role_ids:
        role_ids = _normalize_ids(cfg.get('ALLOWED_ROLE_IDS', []))

    return channel_ids, role_ids

def create_message_link(guild_id: int, channel_id: int, message_id: int) -> str:
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"

async def parse_members(guild: discord.Guild, members_str: str) -> List[discord.Member]:
    member_ids = set()
    parts = re.split(r'[,\s]+', members_str.strip())
    for part in parts:
        if not part:
            continue
        match = re.search(r'(\d+)', part)
        if match:
            member_id = int(match.group(1))
            member_ids.add(member_id)
    members = []
    for mid in member_ids:
        member = guild.get_member(mid)
        if not member:
            try:
                member = await guild.fetch_member(mid)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue
        if member:
            members.append(member)
    return members

async def check_permissions(interaction: discord.Interaction, cfg=None, clan_channel_id: int = None, command_name: str = None) -> bool:
    if cfg is None:
        cfg = await config_manager.get_config(interaction.guild_id)

    resolved_command_name = command_name or (interaction.command.name if interaction.command else '')
    if resolved_command_name:
        allowed_channels, allowed_roles = get_command_access(cfg, resolved_command_name)
    else:
        allowed_channels = []
        allowed_roles = _normalize_ids(cfg.get('ALLOWED_ROLE_IDS', []))

    if clan_channel_id is not None and clan_channel_id not in allowed_channels:
        allowed_channels.append(clan_channel_id)

    if allowed_channels and interaction.channel_id not in allowed_channels:
        await interaction.response.send_message("Эта команда недоступна в этом канале.", ephemeral=True)
        return False

    member = interaction.guild.get_member(interaction.user.id)
    if not member:
        try:
            member = await interaction.guild.fetch_member(interaction.user.id)
        except discord.NotFound:
            await interaction.response.send_message("Не удалось найти вас на сервере.", ephemeral=True)
            return False
        except discord.Forbidden:
            await interaction.response.send_message("У бота нет прав на просмотр участников.", ephemeral=True)
            return False
        except Exception as e:
            await interaction.response.send_message(f"Ошибка: {e}", ephemeral=True)
            return False
    user_roles = [r.id for r in member.roles]
    if not allowed_roles:
        return True

    if not any(r in allowed_roles for r in user_roles):
        await interaction.response.send_message("У вас нет прав.", ephemeral=True)
        return False
    return True

async def check_role_only(interaction: discord.Interaction, cfg=None, command_name: str = None) -> bool:
    if cfg is None:
        cfg = await config_manager.get_config(interaction.guild_id)

    resolved_command_name = command_name or (interaction.command.name if interaction.command else '')
    if resolved_command_name:
        _, allowed_roles = get_command_access(cfg, resolved_command_name)
    else:
        allowed_roles = _normalize_ids(cfg.get('ALLOWED_ROLE_IDS', []))

    member = interaction.guild.get_member(interaction.user.id)
    if not member:
        try:
            member = await interaction.guild.fetch_member(interaction.user.id)
        except discord.NotFound:
            await interaction.response.send_message("Не удалось найти вас на сервере.", ephemeral=True)
            return False
        except discord.Forbidden:
            await interaction.response.send_message("У бота нет прав на просмотр участников.", ephemeral=True)
            return False
        except Exception as e:
            await interaction.response.send_message(f"Ошибка: {e}", ephemeral=True)
            return False
    user_roles = [r.id for r in member.roles]
    if not allowed_roles:
        return True

    if not any(r in allowed_roles for r in user_roles):
        await interaction.response.send_message("У вас нет прав.", ephemeral=True)
        return False
    return True

async def send_dm(user: discord.User, content: str = None, embed: discord.Embed = None, gif_filename: str = None, gif_url: str = None):
    import config
    try:
        if gif_filename:
            path = os.path.join(config.GIF_FOLDER, gif_filename)
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    file = discord.File(f, filename=gif_filename)
                    if embed:
                        embed.set_image(url=f"attachment://{gif_filename}")
                        await user.send(embed=embed, file=file)
                    else:
                        await user.send(file=file)
            else:
                if embed:
                    await user.send(embed=embed)
                elif content:
                    await user.send(content)
        elif gif_url:
            if embed:
                embed.set_image(url=gif_url)
                await user.send(embed=embed)
            else:
                embed = discord.Embed(description=content)
                embed.set_image(url=gif_url)
                await user.send(embed=embed)
        else:
            if embed:
                await user.send(embed=embed)
            elif content:
                await user.send(content)
    except discord.Forbidden:
        logger.send_tg_log(f"⚠️ Не удалось отправить ЛС {user.display_name} (ID: {user.id})")

async def update_punishment_roles(member: discord.Member, guild: discord.Guild, db, cfg):
    try:
        punishments = await db.get_user_active_punishments(member.id)
        warn_count = await db.get_warn_count(member.id)
        has_active_fine = any(p['type'] == 'fine' for p in punishments)
        current_roles = {role.id for role in member.roles}

        fine_role = cfg.get('FINE_ROLE_ID')
        if fine_role:
            if has_active_fine and fine_role not in current_roles:
                await member.add_roles(discord.Object(id=fine_role), reason="Активный штраф")
            elif not has_active_fine and fine_role in current_roles:
                await member.remove_roles(discord.Object(id=fine_role), reason="Штраф оплачен или снят")

        warn_roles = {
            1: cfg.get('WARN_ROLE_1_ID'),
            2: cfg.get('WARN_ROLE_2_ID'),
            3: cfg.get('WARN_ROLE_3_ID')
        }
        for level, role_id in warn_roles.items():
            if role_id and role_id in current_roles and warn_count != level:
                try:
                    await member.remove_roles(discord.Object(id=role_id), reason="Обновление уровня варнов")
                except:
                    pass
        if 1 <= warn_count <= 3:
            role_id = warn_roles[warn_count]
            if role_id and role_id not in current_roles:
                await member.add_roles(discord.Object(id=role_id), reason=f"Уровень варнов {warn_count}/3")
    except Exception as e:
        logger.send_tg_log(f"❌ Ошибка обновления ролей для {member.display_name}: {e}")

async def notify_3_warns(user: discord.User, guild: discord.Guild, db, cfg):
    log_channel = guild.get_channel(cfg.get('NEW_MEMBER_LOG_CHANNEL_ID') or cfg.get('VIOLATION_LOG_CHANNEL_ID'))
    if log_channel:
        role_mentions = " ".join([f"<@&{rid}>" for rid in cfg.get('NOTIFICATION_ROLE_IDS', [])]) if cfg.get('NOTIFICATION_ROLE_IDS') else "@everyone"
        await log_channel.send(f"{role_mentions} Пользователь {user.mention} получил 3 варна! Необходимо засунуть палку в жопу!")
    await send_dm(user, "Вы получили 3 варна.")
    logger.send_tg_log(f"⚠️ 3 варна у {user.display_name} (ID: {user.id})")

async def send_user_log(guild: discord.Guild, embed: discord.Embed, channel_id: int):
    channel = guild.get_channel(channel_id)
    if channel:
        await channel.send(embed=embed)
    else:
        logger.send_tg_log(f"⚠️ Канал {channel_id} не найден на сервере {guild.name}")

# ---------- Функции для работы с кланами ----------
def get_user_clans_by_high_roles(member: discord.Member, cfg) -> list:
    clans = []
    high_roles_clan1 = [member.guild.get_role(rid) for rid in cfg.get('CLAN1_HIGH_RANK_ROLE_IDS', []) if member.guild.get_role(rid)]
    high_roles_clan2 = [member.guild.get_role(rid) for rid in cfg.get('CLAN2_HIGH_RANK_ROLE_IDS', []) if member.guild.get_role(rid)]
    if any(role in member.roles for role in high_roles_clan1):
        clans.append('clan1')
    if any(role in member.roles for role in high_roles_clan2):
        clans.append('clan2')
    return clans

def is_member_of_clan(member: discord.Member, clan_name: str, cfg) -> bool:
    if clan_name == 'clan1':
        member_roles = [member.guild.get_role(rid) for rid in cfg.get('CLAN1_MEMBER_ROLE_IDS', []) if member.guild.get_role(rid)]
        high_roles = [member.guild.get_role(rid) for rid in cfg.get('CLAN1_HIGH_RANK_ROLE_IDS', []) if member.guild.get_role(rid)]
    elif clan_name == 'clan2':
        member_roles = [member.guild.get_role(rid) for rid in cfg.get('CLAN2_MEMBER_ROLE_IDS', []) if member.guild.get_role(rid)]
        high_roles = [member.guild.get_role(rid) for rid in cfg.get('CLAN2_HIGH_RANK_ROLE_IDS', []) if member.guild.get_role(rid)]
    else:
        return False
    clan_roles = member_roles + high_roles
    return any(role in member.roles for role in clan_roles)

async def apply_clan_status(member: discord.Member, game_info, cfg, dry_run: bool = False) -> Tuple[List[str], List[tuple]]:
    """
    Синхронизация ролей/префикса по API:
    - если игрок в одном из 2 кланов: снимаем роли/префиксы другого клана, убираем "друга",
      оставляем высокую роль или выдаём основную роль нужного клана;
    - если игрок не в кланах: снимаем все клановые/высокие роли, выдаём роль бывшего (друга).
    """
    text_changes: List[str] = []
    actions: List[tuple] = []

    if game_info is None:
        return text_changes, actions

    player_clan_name = ((game_info.get('clan') or {}).get('name') or '').lower()

    clans = []
    for idx in (1, 2):
        name = str(cfg.get(f'CLAN{idx}_NAME', '')).strip()
        if not name:
            continue
        clans.append({
            'name': name.lower(),
            'display': name,
            'member_roles': [member.guild.get_role(rid) for rid in cfg.get(f'CLAN{idx}_MEMBER_ROLE_IDS', []) if member.guild.get_role(rid)],
            'ex_roles': [member.guild.get_role(rid) for rid in cfg.get(f'CLAN{idx}_EX_MEMBER_ROLE_IDS', []) if member.guild.get_role(rid)],
            'high_roles': [member.guild.get_role(rid) for rid in cfg.get(f'CLAN{idx}_HIGH_RANK_ROLE_IDS', []) if member.guild.get_role(rid)],
            'prefix': cfg.get(f'CLAN{idx}_NICK_PREFIX', '') or '',
            'ex_prefix': cfg.get(f'CLAN{idx}_EX_NICK_PREFIX', '') or '',
        })

    target_clan = next((c for c in clans if c['name'] == player_clan_name), None)

    def add_action(action):
        if action not in actions:
            actions.append(action)

    if target_clan:
        for clan in clans:
            has_member = any(r in member.roles for r in clan['member_roles'])
            has_high = any(r in member.roles for r in clan['high_roles'])
            has_ex = any(r in member.roles for r in clan['ex_roles'])

            if clan is target_clan:
                for role in clan['ex_roles']:
                    if role in member.roles:
                        add_action(('remove_role', member.id, role.id))
                if has_ex:
                    text_changes.append(f"👤 {member.mention} снята роль бывшего клана {clan['display']}.")

                if not has_member and not has_high and clan['member_roles']:
                    add_action(('add_role', member.id, clan['member_roles'][0].id))
                    text_changes.append(f"➕ {member.mention} выдана роль клана {clan['display']}.")
            else:
                removed_any = False
                for role in clan['member_roles'] + clan['high_roles'] + clan['ex_roles']:
                    if role in member.roles:
                        add_action(('remove_role', member.id, role.id))
                        removed_any = True
                if removed_any:
                    text_changes.append(f"👤 {member.mention} сняты роли клана {clan['display']}.")
    else:
        friend_role_given = False
        for clan in clans:
            had_member_or_high = any(r in member.roles for r in (clan['member_roles'] + clan['high_roles']))

            for role in clan['member_roles'] + clan['high_roles']:
                if role in member.roles:
                    add_action(('remove_role', member.id, role.id))

            for role in clan['ex_roles']:
                if role in member.roles:
                    add_action(('remove_role', member.id, role.id))

            if had_member_or_high and clan['ex_roles']:
                add_action(('add_role', member.id, clan['ex_roles'][0].id))
                friend_role_given = True

        if friend_role_given:
            text_changes.append(f"👤 {member.mention} сняты клановые роли и выдана роль друга.")

    current_nick = member.display_name
    new_nick = current_nick

    changed = True
    while changed:
        changed = False
        for clan in clans:
            for pref in (clan['prefix'], clan['ex_prefix']):
                if pref and new_nick.startswith(pref):
                    new_nick = new_nick[len(pref):].lstrip()
                    changed = True

    if target_clan and target_clan['prefix']:
        new_nick = f"{target_clan['prefix']} {new_nick}".strip()

    if new_nick != current_nick:
        add_action(('edit_nick', member.id, new_nick))
        text_changes.append(f"✏️ {member.mention} изменён ник.")

    if not dry_run:
        for action in actions:
            try:
                if action[0] == 'add_role':
                    m = member.guild.get_member(action[1])
                    r = member.guild.get_role(action[2])
                    if m and r:
                        await m.add_roles(r, reason="Автоматическое обновление статуса клана")
                elif action[0] == 'remove_role':
                    m = member.guild.get_member(action[1])
                    r = member.guild.get_role(action[2])
                    if m and r:
                        await m.remove_roles(r, reason="Автоматическое обновление статуса клана")
                elif action[0] == 'edit_nick':
                    m = member.guild.get_member(action[1])
                    if m:
                        await m.edit(nick=action[2])
            except Exception as e:
                logger.send_tg_log(f"❌ Ошибка при выполнении действия {action}: {e}")

    return text_changes, actions
