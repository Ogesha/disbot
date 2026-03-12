import discord
from discord import app_commands
from typing import Optional
import utils
import logger
from db_client import db
from config_manager import config_manager

FINE_AMOUNTS = ["300.000", "500.000"]
REASON_CHOICES = [
    "отсутствие на КВ",
    "отсутствие на КВ без отписки",
    "непослушание кола",
    "АФК на этапе"
]

@app_commands.command(name="редактировать_штраф", description="Изменить активный штраф")
@app_commands.describe(id="ID штрафа", новая_сумма="Новая сумма", новая_причина="Новая причина")
@app_commands.choices(новая_сумма=[app_commands.Choice(name=a, value=a) for a in FINE_AMOUNTS],
                      новая_причина=[app_commands.Choice(name=r, value=r) for r in REASON_CHOICES])
async def cmd_edit_fine(interaction: discord.Interaction, id: int,
                        новая_сумма: Optional[str] = None, новая_причина: Optional[str] = None):
    cfg = await config_manager.get_config(interaction.guild_id)

    if not await utils.check_permissions(interaction, cfg):
        return

    if not (новая_сумма or новая_причина):
        await interaction.response.send_message("Укажите хотя бы одно поле.", ephemeral=True)
        return

    pun = await db.get_punishment_by_id(id)
    if not pun or pun['type'] != 'fine' or pun['status'] != 'active':
        await interaction.response.send_message("Штраф не найден или неактивен.", ephemeral=True)
        return

    new_amount = int(новая_сумма.replace('.', '')) if новая_сумма else pun['amount']
    new_reason = новая_причина or pun['reason']

    await db.update_punishment(id, new_amount, new_reason)
    await interaction.response.send_message(f"Штраф ID {id} обновлён.", ephemeral=True)
    logger.send_tg_log(f"✏️ Штраф #{id} отредактирован {interaction.user.display_name}")