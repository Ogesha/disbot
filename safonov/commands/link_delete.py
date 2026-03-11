import discord
from discord import app_commands
import config
import utils
import logger
from db_client import db

# Используем английское имя команды
@app_commands.command(name="unlink", description="Удалить привязку вашего Discord к игровому нику")
async def cmd_link_delete(interaction: discord.Interaction):
    if interaction.channel_id != config.LINK_CHANNEL_ID:
        await interaction.response.send_message("Эта команда доступна только в специальном канале.", ephemeral=True)
        return

    await db.remove_game_link(interaction.user.id)
    await interaction.response.send_message("✅ Привязка удалена.", ephemeral=True)
    logger.send_tg_log(f"🔗 {interaction.user} удалил привязку")