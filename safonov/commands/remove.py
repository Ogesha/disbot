import discord
from discord import app_commands
from typing import Optional, List
import datetime
from datetime import timezone
import utils
import logger
from db_client import db
from config_manager import config_manager

PUNISHMENT_NAMES = {'warn': 'Варн', 'fine': 'Штраф'}

async def punishment_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> List[app_commands.Choice]:
    пользователь: Optional[discord.Member] = interaction.namespace.пользователь
    тип: Optional[str] = interaction.namespace.тип

    if not пользователь or not тип:
        return []

    if тип == 'warn':
        puns = await db.get_active_warns(пользователь.id)
    elif тип == 'fine':
        puns = await db.get_active_fines(пользователь.id)
    else:
        return []

    choices = []
    for p in puns:
        issued = p['issued_at'].strftime("%d.%m.%Y")
        reason = p['reason'][:50]
        if p['type'] == 'fine':
            amount = p['amount'] // 1000
            label = f"{issued} - {amount}.000 - {reason}"
        else:
            label = f"{issued} - {reason}"
        if current.lower() in label.lower() or not current:
            choices.append(app_commands.Choice(name=label, value=p['id']))
    return choices[:25]

@app_commands.command(name="снять", description="Снять наказание вручную (можно выбрать конкретное)")
@app_commands.describe(
    пользователь="Пользователь, у которого снимаем наказание",
    тип="Тип наказания",
    id="ID конкретного наказания (если не указано, снимается последнее)"
)
@app_commands.choices(тип=[
    app_commands.Choice(name="варн", value="warn"),
    app_commands.Choice(name="штраф", value="fine")
])
@app_commands.autocomplete(id=punishment_autocomplete)
async def cmd_remove(interaction: discord.Interaction, пользователь: discord.Member, тип: str, id: Optional[int] = None):
    cfg = await config_manager.get_config(interaction.guild_id)

    # Проверяем, что команда вызвана в одном из клановых каналов
    if not await utils.check_permissions(interaction, cfg):
        return

    if тип == 'warn':
        puns = await db.get_active_warns(пользователь.id)
        if not puns:
            await interaction.response.send_message(f"Нет активных варнов.", ephemeral=True)
            return
        if id is not None:
            target = next((p for p in puns if p['id'] == id), None)
            if not target:
                await interaction.response.send_message(f"Варн с ID {id} не найден или неактивен.", ephemeral=True)
                return
        else:
            target = sorted(puns, key=lambda r: r['issued_at'], reverse=True)[0]

        await db.update_punishment_status(target['id'], 'removed')
        issued = target['issued_at'].strftime("%d.%m.%Y")
        reason = target['reason']
        now_str = datetime.datetime.now(timezone.utc).replace(tzinfo=None).strftime("%d.%m.%Y")
        await db.add_punishment_history(
            guild_id=interaction.guild_id,
            user_id=пользователь.id,
            username=пользователь.display_name,
            p_type='warn',
            amount=None,
            reason=reason,
            issued_at=target['issued_at'],
            removed_at=datetime.datetime.now(timezone.utc).replace(tzinfo=None),
            status='removed',
            message_id=target['message_id'],
            channel_id=target['channel_id']
        )
        dm_message = f"Варн от {issued} за \"{reason}\" снят (дата снятия: {now_str}). Fisting за 300 Bucks пройден успешно."
        await utils.send_dm(пользователь, dm_message)
        embed = discord.Embed(
            title="Снято наказание",
            description=f"Варн (ID {target['id']}) для {пользователь.mention} снят.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)
        logger.send_tg_log(f"🔻 Варн #{target['id']} снят с {пользователь.display_name}")

    else:  # штраф
        fines = await db.get_active_fines(пользователь.id)
        if not fines:
            await interaction.response.send_message(f"Нет активных штрафов.", ephemeral=True)
            return
        if id is not None:
            target_fine = next((f for f in fines if f['id'] == id), None)
            if not target_fine:
                await interaction.response.send_message(f"Штраф с ID {id} не найден или неактивен.", ephemeral=True)
                return
        else:
            target_fine = sorted(fines, key=lambda r: r['issued_at'], reverse=True)[0]

        fine_id = target_fine['id']
        fine_issued = target_fine['issued_at'].strftime("%d.%m.%Y")
        fine_reason = target_fine['reason']

        await db.update_punishment_status(fine_id, 'removed')
        await db.add_punishment_history(
            guild_id=interaction.guild_id,
            user_id=пользователь.id,
            username=пользователь.display_name,
            p_type='fine',
            amount=target_fine['amount'],
            reason=fine_reason,
            issued_at=target_fine['issued_at'],
            removed_at=datetime.datetime.now(timezone.utc).replace(tzinfo=None),
            status='removed',
            message_id=target_fine['message_id'],
            channel_id=target_fine['channel_id']
        )

        async with db.pool.acquire() as conn:
            related_warn = await conn.fetchrow(
                'SELECT id, issued_at FROM punishments WHERE fine_id = $1 AND status = $2 ORDER BY issued_at ASC LIMIT 1',
                fine_id, 'active'
            )

        warn_message = ""
        if related_warn:
            await db.update_punishment_status(related_warn['id'], 'removed')
            warn_data = await db.get_punishment_by_id(related_warn['id'])
            await db.add_punishment_history(
                guild_id=interaction.guild_id,
                user_id=пользователь.id,
                username=пользователь.display_name,
                p_type='warn',
                amount=None,
                reason=f"В связи со штрафом: {fine_reason}",
                issued_at=warn_data['issued_at'],
                removed_at=datetime.datetime.now(timezone.utc).replace(tzinfo=None),
                status='removed',
                message_id=warn_data['message_id'],
                channel_id=warn_data['channel_id'],
                fine_id=fine_id
            )
            warn_issued = warn_data['issued_at'].strftime("%d.%m.%Y")
            warn_message = f" и соответствующий варн от {warn_issued}"
            logger.send_tg_log(f"🔻 Связанный варн #{related_warn['id']} снят с {пользователь.display_name}")

        now_str = datetime.datetime.now(timezone.utc).replace(tzinfo=None).strftime("%d.%m.%Y")
        dm_message = f"Штраф от {fine_issued} за \"{fine_reason}\" снят{warn_message} (дата снятия: {now_str}). Fisting за 300 Bucks пройден успешно."
        await utils.send_dm(пользователь, dm_message)

        embed = discord.Embed(
            title="Снято наказание",
            description=f"Штраф (ID {fine_id}) для {пользователь.mention} снят{warn_message}.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)
        logger.send_tg_log(f"🔻 Штраф #{fine_id} снят с {пользователь.display_name}")

    await utils.update_punishment_roles(пользователь, interaction.guild, db, cfg)