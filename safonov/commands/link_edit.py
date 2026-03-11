import discord
from discord import app_commands
import config
import utils
import logger
from db_client import db
from stalcraft_client import stalcraft

@app_commands.command(name="изменить", description="Изменить привязанный ник или регион")
@app_commands.describe(новый_ник="Новый ник в Stalcraft", регион="Регион (по умолчанию оставить текущий)")
@app_commands.choices(регион=[
    app_commands.Choice(name="EU", value="eu"),
    app_commands.Choice(name="RU", value="ru"),
    app_commands.Choice(name="DEV", value="dev")
])
async def cmd_link_edit(interaction: discord.Interaction, новый_ник: str, регион: str = None):
    # Проверка канала
    if interaction.channel_id != config.LINK_CHANNEL_ID:
        await interaction.response.send_message("Эта команда доступна только в специальном канале.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    # Проверяем существование игрока
    info = await stalcraft.get_player_info(новый_ник, region=регион or config.STALCRAFT_REGION)
    if not info:
        embed = discord.Embed(
            title="❌ Ошибка",
            description=f"Игрок с ником **{новый_ник}** не найден в регионе {(регион or config.STALCRAFT_REGION).upper()}.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    # Обновляем запись
    await db.add_game_link(interaction.user.id, новый_ник, регион or config.STALCRAFT_REGION)

    embed = discord.Embed(
        title="✅ Привязка обновлена",
        description=f"Ваш Discord аккаунт теперь привязан к игроку **{новый_ник}** (регион {(регион or config.STALCRAFT_REGION).upper()}).",
        color=discord.Color.green()
    )
    await interaction.followup.send(embed=embed, ephemeral=True)
    logger.send_tg_log(f"🔗 {interaction.user} изменил привязку на {новый_ник} (регион {регион or config.STALCRAFT_REGION})")