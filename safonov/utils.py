import discord
import os
import re
import datetime
from datetime import timezone
from typing import List, Tuple
import logger
from db_client import db

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

async def check_permissions(interaction: discord.Interaction, cfg, clan_channel_id: int = None) -> bool:
    if clan_channel_id is not None:
        if interaction.channel_id != clan_channel_id:
            await interaction.response.send_message("Эта команда недоступна в этом канале.", ephemeral=True)
            return False
    else:
        allowed_channels = cfg.get('COMMAND_CHANNEL_IDS', [])
        if interaction.channel_id not in allowed_channels:
            await interaction.response.send_message("Команда доступна только в специальных каналах.", ephemeral=True)
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
    allowed_roles = cfg.get('ALLOWED_ROLE_IDS', [])
    if not any(r in allowed_roles for r in user_roles):
        await interaction.response.send_message("У вас нет прав.", ephemeral=True)
        return False
    return True

async def check_role_only(interaction: discord.Interaction, cfg) -> bool:
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
    allowed_roles = cfg.get('ALLOWED_ROLE_IDS', [])
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
    elif clan_name == 'clan2':
        member_roles = [member.guild.get_role(rid) for rid in cfg.get('CLAN2_MEMBER_ROLE_IDS', []) if member.guild.get_role(rid)]
    else:
        return False
    return any(role in member.roles for role in member_roles)

async def apply_clan_status(member: discord.Member, game_info, cfg, dry_run: bool = False) -> Tuple[List[str], List[tuple]]:
    """
    Анализирует статус клана по API и возвращает:
      - text_changes: список строк для отображения в логе.
      - actions: список кортежей ('add_role', member_id, role_id) или ('remove_role', member_id, role_id) или ('edit_nick', member_id, new_nick).
    Если dry_run=False, сразу выполняет действия.
    """
    text_changes = []
    actions = []
    if not game_info:
        return text_changes, actions

    player_clan_name = game_info.get('clan', {}).get('name', '').lower() if game_info.get('clan') else None

    # Конфигурации кланов
    clans = []
    if cfg.get('CLAN1_NAME'):
        clans.append({
            'name': cfg.get('CLAN1_NAME').lower(),
            'member_roles': [member.guild.get_role(rid) for rid in cfg.get('CLAN1_MEMBER_ROLE_IDS', []) if member.guild.get_role(rid)],
            'ex_roles': [member.guild.get_role(rid) for rid in cfg.get('CLAN1_EX_MEMBER_ROLE_IDS', []) if member.guild.get_role(rid)],
            'high_roles': [member.guild.get_role(rid) for rid in cfg.get('CLAN1_HIGH_RANK_ROLE_IDS', []) if member.guild.get_role(rid)],
            'prefix': cfg.get('CLAN1_NICK_PREFIX', ''),
            'ex_prefix': cfg.get('CLAN1_EX_NICK_PREFIX', ''),
        })
    if cfg.get('CLAN2_NAME'):
        clans.append({
            'name': cfg.get('CLAN2_NAME').lower(),
            'member_roles': [member.guild.get_role(rid) for rid in cfg.get('CLAN2_MEMBER_ROLE_IDS', []) if member.guild.get_role(rid)],
            'ex_roles': [member.guild.get_role(rid) for rid in cfg.get('CLAN2_EX_MEMBER_ROLE_IDS', []) if member.guild.get_role(rid)],
            'high_roles': [member.guild.get_role(rid) for rid in cfg.get('CLAN2_HIGH_RANK_ROLE_IDS', []) if member.guild.get_role(rid)],
            'prefix': cfg.get('CLAN2_NICK_PREFIX', ''),
            'ex_prefix': cfg.get('CLAN2_EX_NICK_PREFIX', ''),
        })

    # Текущие роли
    current_role_ids = {role.id for role in member.roles}

    # Обрабатываем каждый клан
    for clan in clans:
        clan_name = clan['name']
        member_roles = clan['member_roles']
        ex_roles = clan['ex_roles']
        high_roles = clan['high_roles']

        has_member = any(role in member.roles for role in member_roles)
        has_high = any(role in member.roles for role in high_roles)
        has_ex = any(role in member.roles for role in ex_roles)

        is_in_clan = (player_clan_name == clan_name)

        if is_in_clan:
            # Состоит в этом клане
            if has_ex:
                # Снимаем роль бывшего
                for role in ex_roles:
                    if role in member.roles:
                        actions.append(('remove_role', member.id, role.id))
                text_changes.append(f"👤 {member.mention} снята роль бывшего клана {clan_name}.")

            if not has_high and not has_member and member_roles:
                # Выдаём роль члена
                actions.append(('add_role', member.id, member_roles[0].id))
                text_changes.append(f"➕ {member.mention} выдана роль клана {clan_name}.")
            elif has_high:
                text_changes.append(f"👤 {member.mention} имеет высокую роль клана {clan_name}, роль не выдана.")
        else:
            # Не состоит в этом клане
            if has_member:
                # Снимаем роль члена
                for role in member_roles:
                    if role in member.roles:
                        actions.append(('remove_role', member.id, role.id))
                text_changes.append(f"👤 {member.mention} сняты роли клана {clan_name}.")

                # Выдаём роль бывшего (если была роль члена)
                if ex_roles and not has_ex:
                    actions.append(('add_role', member.id, ex_roles[0].id))
                    text_changes.append(f"👤 {member.mention} выдана роль бывшего клана {clan_name}.")

            if has_high:
                # Снимаем высокие роли
                for role in high_roles:
                    if role in member.roles:
                        actions.append(('remove_role', member.id, role.id))
                text_changes.append(f"👤 {member.mention} сняты высокие роли клана {clan_name}.")

    # ---------- Формирование ника ----------
    current_nick = member.display_name
    new_nick = current_nick

    # Удаляем все известные префиксы
    for clan in clans:
        if new_nick.startswith(clan['prefix']):
            new_nick = new_nick[len(clan['prefix']):]
        if new_nick.startswith(clan['ex_prefix']):
            new_nick = new_nick[len(clan['ex_prefix']):]

    # Определяем, какой префикс нужно добавить
    prefix_to_add = None
    for clan in clans:
        if player_clan_name == clan['name']:
            prefix_to_add = clan['prefix']
            break

    if prefix_to_add:
        new_nick = f"{prefix_to_add}{new_nick}"
    # иначе оставляем без префикса

    if new_nick != current_nick:
        actions.append(('edit_nick', member.id, new_nick))
        if prefix_to_add:
            text_changes.append(f"✏️ {member.mention} изменён ник (добавлен префикс {prefix_to_add}).")
        else:
            text_changes.append(f"✏️ {member.mention} изменён ник (префиксы удалены).")

    # Если не dry_run – выполняем все действия сейчас
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