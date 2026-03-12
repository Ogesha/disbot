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
FINE_AMOUNTS = ["300.000", "500.000"]

@app_commands.command(name="штраф", description="Выписать штраф одному или нескольким пользователям")
@app_commands.describe(пользователи="Упоминания/ID", сумма="Сумма", причина="Причина")
@app_commands.choices(сумма=[app_commands.Choice(name=a, value=a) for a in FINE_AMOUNTS],
                      причина=[app_commands.Choice(name=r, value=r) for r in REASON_CHOICES])
async def cmd_fine(interaction: discord.Interaction, пользователи: str, сумма: str, причина: str):
    cfg = await config_manager.get_config(interaction.guild_id)

    if not await utils.check_permissions(interaction, cfg):
        return

    targets = await utils.parse_members(interaction.guild, пользователи)
    if not targets:
        await interaction.response.send_message("Не найдено пользователей.", ephemeral=True)
        return

    # Отладка: определяем кланы инициатора
    initiator_clans = utils.get_user_clans_by_high_roles(interaction.user, cfg)
    if initiator_clans:
        for target in targets:
            # Для каждого целевого пользователя проверяем членство в каждом клане инициатора
            member_of = [utils.is_member_of_clan(target, clan, cfg) for clan in initiator_clans]
            if not any(member_of):
                await interaction.response.send_message(
                    f"Пользователь {target.mention} не является членом вашего клана.",
                    ephemeral=True
                )
                return

    amount_int = int(сумма.replace('.', ''))
    mentions = ", ".join([m.mention for m in targets])
    embed = discord.Embed(
        title="Штраф",
        description=f"{mentions} **{сумма}** на куру Шизик_Секс – {причина}",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()

    success_count = 0
    for t in targets:
        try:
            now = datetime.datetime.now(timezone.utc).replace(tzinfo=None)
            fine_id = await db.add_punishment(
                guild_id=interaction.guild_id,
                user_id=t.id,
                username=t.display_name,
                p_type='fine',
                amount=amount_int,
                reason=причина,
                message_id=msg.id,
                channel_id=interaction.channel_id,
                fine_id=None,
                issued_at=now,
                paid_at=None
            )
            warn_id = await db.add_punishment(
                guild_id=interaction.guild_id,
                user_id=t.id,
                username=t.display_name,
                p_type='warn',
                amount=None,
                reason=f"В связи со штрафом: {причина}",
                message_id=msg.id,
                channel_id=interaction.channel_id,
                fine_id=fine_id,
                issued_at=now,
                paid_at=None
            )
            await db.add_punishment_history(
                guild_id=interaction.guild_id,
                user_id=t.id,
                username=t.display_name,
                p_type='fine',
                amount=amount_int,
                reason=причина,
                issued_at=now,
                status='active',
                message_id=msg.id,
                channel_id=interaction.channel_id
            )
            await db.add_punishment_history(
                guild_id=interaction.guild_id,
                user_id=t.id,
                username=t.display_name,
                p_type='warn',
                amount=None,
                reason=f"В связи со штрафом: {причина}",
                issued_at=now,
                status='active',
                message_id=msg.id,
                channel_id=interaction.channel_id,
                fine_id=fine_id
            )
            link = utils.create_message_link(interaction.guild_id, interaction.channel_id, msg.id)
            await utils.send_dm(t,
                                f"Вам выдан штраф {link}\nСрок оплаты – неделя, после чего будут выдаваться дополнительные варны.",
                                gif_filename=cfg.get('GIF_SAFONOV_OPLATIT', 'safonov_oplatit.gif'))
            logger.send_tg_log(f"🟢 Штраф #{fine_id} и связанный варн #{warn_id} выданы {t.display_name} ({t.id}) на {сумма}")
            await utils.update_punishment_roles(t, interaction.guild, db, cfg)
            success_count += 1
        except Exception as e:
            logger.send_tg_log(f"❌ Ошибка при выдаче штрафа {t.display_name}: {e}")

    if success_count < len(targets):
        await interaction.followup.send(f"Штраф выдан {success_count} из {len(targets)}.", ephemeral=True)