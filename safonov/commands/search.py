import discord
from discord import app_commands
import config  # глобальный для STALCRAFT_REGION по умолчанию (но может быть переопределён cfg)
import utils
import logger
from stalcraft_client import stalcraft
from config_manager import config_manager

@app_commands.command(name="поиск", description="Найти игрока в Stalcraft")
@app_commands.describe(ник="Игровой ник", регион="Регион (по умолчанию из конфига)")
@app_commands.choices(регион=[
    app_commands.Choice(name="EU", value="eu"),
    app_commands.Choice(name="RU", value="ru"),
    app_commands.Choice(name="DEV", value="dev")
])
async def cmd_search(interaction: discord.Interaction, ник: str, регион: str = None):
    # Получаем конфиг гильдии (нужен для проверки канала и прав, а также для региона по умолчанию)
    cfg = await config_manager.get_config(interaction.guild_id)

    allowed_channels, _ = utils.get_command_access(cfg, 'поиск')
    if allowed_channels and interaction.channel_id not in allowed_channels:
        await interaction.response.send_message("Эта команда недоступна в этом канале.", ephemeral=True)
        return

    # Проверка прав (роль из ALLOWED_ROLE_IDS) – используем cfg
    if not await utils.check_role_only(interaction, cfg, command_name="поиск"):
        return

    await interaction.response.defer()
    region_to_use = регион if регион else cfg.get('STALCRAFT_REGION', config.STALCRAFT_REGION)
    info = await stalcraft.get_player_info(ник, region=region_to_use)
    if not info:
        embed = discord.Embed(
            title="❌ Игрок не найден",
            description=f"Пользователь с ником **{ник}** не найден в регионе {region_to_use.upper()}.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)
        return

    embed = discord.Embed(
        title=f"Информация об игроке {info['account_name']}",
        color=discord.Color.blue()
    )
    embed.add_field(name="ID аккаунта", value=info['account_id'], inline=False)

    if info.get('registration_date') or info.get('created_at'):
        reg_date = info.get('registration_date') or info.get('created_at')
        embed.add_field(name="Аккаунт создан", value=reg_date.strftime("%d.%m.%Y %H:%M"), inline=True)

    clan = info.get('clan')
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

    if info.get('characters'):
        char = info['characters'][0]
        embed.add_field(name="Персонаж", value=char['name'], inline=True)
        embed.add_field(name="PvP убийства", value=char['pvp_kills'], inline=True)
        embed.add_field(name="PvP смерти", value=char['pvp_deaths'], inline=True)
        embed.add_field(name="K/D", value=char['kd'], inline=True)

    if info.get('last_login'):
        embed.add_field(name="Последний вход", value=info['last_login'].strftime("%d.%m.%Y %H:%M"), inline=True)
    embed.add_field(name="Времени сыграно (ч)", value=info['total_playtime_hours'], inline=True)
    embed.add_field(name="Активность в день (ч)", value=info['avg_daily_hours'], inline=True)

    await interaction.followup.send(embed=embed)
    logger.send_tg_log(f"🔍 Поиск игрока {ник} в {region_to_use.upper()} выполнен {interaction.user}")