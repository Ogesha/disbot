import discord
from discord import app_commands
import datetime
from datetime import timezone
import utils
import logger
from db_client import db
from config_manager import config_manager

REASON_CHOICES = [
    "отсутствие на КВ",
    "отсутствие на КВ без отписки",
    "непослушание кола",
    "АФК на этапе"
]

@app_commands.command(name="варн", description="Выдать предупреждение одному или нескольким пользователям")
@app_commands.describe(пользователи="Упоминания/ID", причина="Причина")
@app_commands.choices(причина=[app_commands.Choice(name=r, value=r) for r in REASON_CHOICES])
async def cmd_warn(interaction: discord.Interaction, пользователи: str, причина: str):
    cfg = await config_manager.get_config(interaction.guild_id)

    clan1_channel = cfg.get('CLAN1_COMMAND_CHANNEL_ID')
    clan2_channel = cfg.get('CLAN2_COMMAND_CHANNEL_ID')
    if interaction.channel_id not in (clan1_channel, clan2_channel):
        await interaction.response.send_message("Эта команда недоступна в этом канале.", ephemeral=True)
        return

    if not await utils.check_permissions(interaction, cfg, clan_channel_id=interaction.channel_id):
        return

    targets = await utils.parse_members(interaction.guild, пользователи)
    if not targets:
        await interaction.response.send_message("Не найдено пользователей.", ephemeral=True)
        return

    # Отладка: определяем кланы инициатора
    initiator_clans = utils.get_user_clans_by_high_roles(interaction.user, cfg)
    if initiator_clans:
        for target in targets:
            member_of = [utils.is_member_of_clan(target, clan, cfg) for clan in initiator_clans]
            if not any(member_of):
                await interaction.response.send_message(
                    f"Пользователь {target.mention} не является членом вашего клана.",
                    ephemeral=True
                )
                return

    mentions = ", ".join([m.mention for m in targets])
    embed = discord.Embed(
        title="Варн",
        description=f"{mentions} – {причина}",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()

    success_count = 0
    now = datetime.datetime.now(timezone.utc).replace(tzinfo=None)
    for t in targets:
        try:
            pid = await db.add_punishment(
                guild_id=interaction.guild_id,
                user_id=t.id,
                username=t.display_name,
                p_type='warn',
                amount=None,
                reason=причина,
                message_id=msg.id,
                channel_id=interaction.channel_id,
                issued_at=now
            )
            await db.add_punishment_history(
                guild_id=interaction.guild_id,
                user_id=t.id,
                username=t.display_name,
                p_type='warn',
                amount=None,
                reason=причина,
                issued_at=now,
                status='active',
                message_id=msg.id,
                channel_id=interaction.channel_id
            )
            link = utils.create_message_link(interaction.guild_id, interaction.channel_id, msg.id)
            await utils.send_dm(t, f"Вам выдан варн {link}\nОн будет автоматически снят через 2 недели.")
            await utils.update_punishment_roles(t, interaction.guild, db, cfg)
            if await db.get_warn_count(t.id) >= 3:
                await utils.notify_3_warns(t, interaction.guild, db, cfg)
            logger.send_tg_log(f"🟡 Варн #{pid} выдан {t.display_name} ({t.id})")
            success_count += 1
        except Exception as e:
            logger.send_tg_log(f"❌ Ошибка при выдаче варна {t.display_name}: {e}")

    if success_count < len(targets):
        await interaction.followup.send(f"Варн выдан {success_count} из {len(targets)}.", ephemeral=True)