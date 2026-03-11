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

    # Проверяем, что команда вызвана в одном из клановых каналов
    clan1_channel = cfg.get('CLAN1_COMMAND_CHANNEL_ID')
    clan2_channel = cfg.get('CLAN2_COMMAND_CHANNEL_ID')
    if interaction.channel_id not in (clan1_channel, clan2_channel):
        await interaction.response.send_message("Эта команда недоступна в этом канале.", ephemeral=True)
        return

    # Проверяем права (роль из ALLOWED_ROLE_IDS) и канал (передаём clan_channel_id)
    if not await utils.check_permissions(interaction, cfg, clan_channel_id=interaction.channel_id):
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