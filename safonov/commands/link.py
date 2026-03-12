import discord
from discord import app_commands
from typing import Optional
import utils
import logger
from db_client import db
from stalcraft_client import stalcraft
from config_manager import config_manager

@app_commands.command(name="привязать", description="Привязать игровой ник к Discord (для себя или другого пользователя)")
@app_commands.describe(
    пользователь="Пользователь, которому привязываем (по умолчанию вы)",
    ник="Ник в Stalcraft"
)
async def cmd_link(interaction: discord.Interaction, ник: str, пользователь: Optional[discord.Member] = None):
    cfg = await config_manager.get_config(interaction.guild_id)

    allowed_channels, _ = utils.get_command_access(cfg, 'привязать')
    if allowed_channels and interaction.channel_id not in allowed_channels:
        await interaction.response.send_message("Эта команда недоступна в этом канале.", ephemeral=True)
        return

    if not await utils.check_role_only(interaction, cfg, command_name="привязать"):
        return

    target = пользователь or interaction.user

    await interaction.response.defer(ephemeral=True)
    info = await stalcraft.get_player_info(ник, region="ru")
    if not info:
        embed = discord.Embed(
            title="❌ Ошибка",
            description=f"Игрок с ником **{ник}** не найден в регионе RU.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    await db.add_game_link(target.id, ник, "ru")

    changes, _ = await utils.apply_clan_status(target, info, cfg, dry_run=False)
    if changes:
        embed_log = discord.Embed(
            title="📌 Обновление после привязки",
            description="\n".join(changes),
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        log_channel_id = utils.get_command_log_channel_id(cfg, 'привязать', fallback_key='MEMBER_CHANGE_LOG_CHANNEL_ID')
        await utils.send_user_log(interaction.guild, embed_log, channel_id=log_channel_id)

    embed = discord.Embed(
        title="✅ Привязка успешна",
        description=f"Пользователь {target.mention} теперь привязан к игроку **{ник}** (регион RU).",
        color=discord.Color.green()
    )
    await interaction.followup.send(embed=embed, ephemeral=True)

    logger.send_tg_log(f"🔗 {interaction.user} {'привязал' if target.id == interaction.user.id else f'привязал для {target}'} ник {ник} (регион ru)")
