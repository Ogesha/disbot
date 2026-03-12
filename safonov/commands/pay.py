import discord
from discord import app_commands
import datetime
from datetime import timezone
import utils
import logger
from db_client import db
from config_manager import config_manager

@app_commands.command(name="оплата", description="Отметить оплату штрафа")
async def cmd_pay(interaction: discord.Interaction, пользователь: discord.Member):
    # Получаем конфиг гильдии
    cfg = await config_manager.get_config(interaction.guild_id)

    if not await utils.check_permissions(interaction, cfg, command_name="оплата"):
        return

    fines = await db.get_active_fines(пользователь.id)
    if not fines:
        await interaction.response.send_message("У пользователя нет активных штрафов.", ephemeral=True)
        return

    oldest = sorted(fines, key=lambda r: r['issued_at'])[0]
    fine_id = oldest['id']
    paid_at = datetime.datetime.now(timezone.utc).replace(tzinfo=None)
    await db.update_punishment_status(fine_id, 'paid', paid_at)
    await db.add_punishment_history(
        guild_id=interaction.guild_id,
        user_id=пользователь.id,
        username=пользователь.display_name,
        p_type='fine',
        amount=oldest['amount'],
        reason=oldest['reason'],
        issued_at=oldest['issued_at'],
        paid_at=paid_at,
        status='paid',
        message_id=oldest['message_id'],
        channel_id=oldest['channel_id']
    )
    # Используем cfg.get для гифки, с fallback на глобальный config
    await utils.send_dm(пользователь,
                        "Молодец Сафонов, штраф оплачен. Варн будет автоматически снят спустя 14 дней с момента его выдачи",
                        gif_filename=cfg.get('GIF_ILYA_MUROMETS', 'ilya_muromets.gif'))
    await interaction.response.send_message(f"Штраф для {пользователь.mention} оплачен.", ephemeral=True)
    logger.send_tg_log(f"✅ Штраф #{fine_id} оплачен {пользователь.display_name}")
    await utils.update_punishment_roles(пользователь, interaction.guild, db, cfg)