import discord
from discord import app_commands
from typing import Optional
import utils
import logger
from db_client import db
from config_manager import config_manager

@app_commands.command(name="список", description="Показать активные наказания пользователя")
@app_commands.describe(пользователь="Пользователь (по умолчанию вы)")
async def cmd_list(interaction: discord.Interaction, пользователь: Optional[discord.Member] = None):
    cfg = await config_manager.get_config(interaction.guild_id)

    # Проверяем, что команда вызвана в одном из клановых каналов
    clan1_channel = cfg.get('CLAN1_COMMAND_CHANNEL_ID')
    clan2_channel = cfg.get('CLAN2_COMMAND_CHANNEL_ID')
    if interaction.channel_id not in (clan1_channel, clan2_channel):
        await interaction.response.send_message("Эта команда недоступна в этом канале.", ephemeral=True)
        return

    if not await utils.check_permissions(interaction, cfg, clan_channel_id=interaction.channel_id):
        return

    target = пользователь or interaction.user
    punishments = await db.get_user_active_punishments(target.id)

    if not punishments:
        await interaction.response.send_message(f"У {target.mention} нет активных наказаний.", ephemeral=True)
        return

    embed = discord.Embed(title=f"Активные наказания {target.display_name}", color=discord.Color.blue())
    for p in punishments:
        issued = p['issued_at'].strftime("%d.%m.%Y")
        if p['type'] == 'fine':
            amount_str = f"{p['amount']//1000}.000" if p['amount'] else "?"
            line = f"**Штраф** {amount_str} – {p['reason']} (от {issued})"
        else:
            line = f"**Варн** – {p['reason']} (от {issued})"
            if p['paid_at']:
                paid = p['paid_at'].strftime("%d.%m.%Y")
                line += f", оплачен {paid}"
        embed.add_field(name=f"ID {p['id']}", value=line, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)
    logger.send_tg_log(f"📋 Список наказаний для {target} запросил {interaction.user}")