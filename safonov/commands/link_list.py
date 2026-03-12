import discord
from discord import app_commands
from typing import Optional
import datetime
import utils
import logger
from db_client import db
from config_manager import config_manager

@app_commands.command(name="linklist", description="Показать список привязанных пользователей и статистику по кланам")
@app_commands.describe(роль="Роль для фильтрации (упоминание)")
async def cmd_link_list(interaction: discord.Interaction, роль: Optional[discord.Role] = None):
    cfg = await config_manager.get_config(interaction.guild_id)

    allowed_channels, _ = utils.get_command_access(cfg, 'linklist')
    if allowed_channels and interaction.channel_id not in allowed_channels:
        await interaction.response.send_message("Эта команда недоступна в этом канале.", ephemeral=True)
        return

    if not await utils.check_role_only(interaction, cfg):
        return

    await interaction.response.defer(ephemeral=False)

    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch('SELECT * FROM game_links ORDER BY last_updated DESC')
            total_count = len(rows)
    except Exception as e:
        logger.send_tg_log(f"❌ Ошибка при запросе к БД в /linklist: {e}")
        await interaction.followup.send("Произошла внутренняя ошибка при получении данных.", ephemeral=True)
        return

    if not rows:
        await interaction.followup.send("Нет привязанных пользователей.")
        return

    # Получаем ID ролей кланов из конфига
    clan1_member_ids = set(cfg.get('CLAN1_MEMBER_ROLE_IDS', []))
    clan1_ex_ids = set(cfg.get('CLAN1_EX_MEMBER_ROLE_IDS', []))
    clan2_member_ids = set(cfg.get('CLAN2_MEMBER_ROLE_IDS', []))
    clan2_ex_ids = set(cfg.get('CLAN2_EX_MEMBER_ROLE_IDS', []))

    clan1_member_count = 0
    clan1_ex_count = 0
    clan2_member_count = 0
    clan2_ex_count = 0

    filtered_display = []
    for row in rows:
        member = interaction.guild.get_member(row['discord_id'])
        if member:
            # Подсчёт статистики
            if any(role.id in clan1_member_ids for role in member.roles):
                clan1_member_count += 1
            if any(role.id in clan1_ex_ids for role in member.roles):
                clan1_ex_count += 1
            if any(role.id in clan2_member_ids for role in member.roles):
                clan2_member_count += 1
            if any(role.id in clan2_ex_ids for role in member.roles):
                clan2_ex_count += 1

            # Фильтрация по роли (если указана)
            if роль is not None and роль not in member.roles:
                continue
            top_role = member.top_role if member.top_role != member.guild.default_role else None
            role_info = top_role.mention if top_role else "нет"
            member_name = member.mention
            filtered_display.append((member_name, row, role_info))
        else:
            # Пользователь покинул сервер
            if роль is not None:
                continue
            member_name = f"Неизвестный (ID: {row['discord_id']})"
            filtered_display.append((member_name, row, None))

    if not filtered_display:
        if роль:
            await interaction.followup.send(f"Нет привязанных пользователей с ролью {роль.mention}.")
        else:
            await interaction.followup.send("Не удалось отобразить список (возможно, все привязанные пользователи покинули сервер).")
        return

    # Формируем embed
    embed = discord.Embed(title="📋 Привязанные аккаунты", color=discord.Color.blue())
    if роль:
        embed.title = f"📋 Привязанные аккаунты (фильтр: {роль.name})"
        embed.description = f"Фильтр по роли {роль.mention}"

    # Статистика по кланам
    stats = f"**Всего в БД:** {total_count}\n"
    stats += f"**На сервере:** {len([m for m in rows if interaction.guild.get_member(m['discord_id'])])}\n\n"
    if cfg.get('CLAN1_NAME'):
        stats += f"**Клан {cfg.get('CLAN1_NAME').upper()}:**\n"
        stats += f"  Члены: {clan1_member_count}\n"
        stats += f"  Бывшие: {clan1_ex_count}\n"
    if cfg.get('CLAN2_NAME'):
        stats += f"**Клан {cfg.get('CLAN2_NAME').upper()}:**\n"
        stats += f"  Члены: {clan2_member_count}\n"
        stats += f"  Бывшие: {clan2_ex_count}\n"

    embed.add_field(name="📊 Статистика", value=stats, inline=False)

    # Добавляем поля с пользователями (лимит Discord: максимум 25 полей в embed)
    max_user_fields = 24
    for member_name, row, role_info in filtered_display[:max_user_fields]:
        updated = row['last_updated'].strftime("%d.%m.%Y %H:%M")
        value = f"Ник: {row['game_nick']} (регион {row['region'].upper()})\nОбновлено: {updated}"
        if role_info:
            value += f"\nРоль: {role_info}"
        embed.add_field(name=member_name, value=value, inline=False)

    if len(filtered_display) > max_user_fields:
        embed.set_footer(text=f"Показано {max_user_fields} из {len(filtered_display)} записей. Уточните фильтр роли для полного списка.")

    await interaction.followup.send(embed=embed)
