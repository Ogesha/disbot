import discord
from discord import app_commands
from typing import Optional
import utils
import logger
from db_client import db

class NoteGroup(app_commands.Group):
    pass

note_group = NoteGroup(name="заметка", description="Управление заметками о пользователях")

@note_group.command(name="добавить", description="Добавить заметку о пользователе")
@app_commands.describe(пользователь="Пользователь", текст="Текст заметки")
async def note_add(interaction: discord.Interaction, пользователь: discord.Member, текст: str):
    if not await utils.check_permissions(interaction):
        return
    note_id = await db.add_note(пользователь.id, interaction.user.id, текст)
    await interaction.response.send_message(f"✅ Заметка #{note_id} добавлена для {пользователь.mention}", ephemeral=True)
    logger.send_tg_log(f"📝 Заметка #{note_id} добавлена для {пользователь} от {interaction.user}")

@note_group.command(name="список", description="Показать все заметки о пользователе")
@app_commands.describe(пользователь="Пользователь")
async def note_list(interaction: discord.Interaction, пользователь: discord.Member):
    if not await utils.check_permissions(interaction):
        return
    notes = await db.get_user_notes(пользователь.id)
    if not notes:
        await interaction.response.send_message(f"У {пользователь.mention} нет заметок.", ephemeral=True)
        return
    embed = discord.Embed(title=f"Заметки о {пользователь.display_name}", color=discord.Color.green())
    for n in notes:
        created = n['created_at'].strftime("%d.%m.%Y")
        author = interaction.guild.get_member(n['author_id']) or f"ID {n['author_id']}"
        embed.add_field(name=f"#{n['id']} от {created} (автор {author})", value=n['note'][:100], inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@note_group.command(name="удалить", description="Удалить заметку")
@app_commands.describe(пользователь="Пользователь", id="ID заметки")
async def note_delete(interaction: discord.Interaction, пользователь: discord.Member, id: int):
    if not await utils.check_permissions(interaction):
        return
    await db.delete_note(id, пользователь.id)
    await interaction.response.send_message(f"✅ Заметка #{id} удалена.", ephemeral=True)
    logger.send_tg_log(f"📝 Заметка #{id} удалена для {пользователь} от {interaction.user}")

@note_group.command(name="редактировать", description="Изменить текст заметки")
@app_commands.describe(пользователь="Пользователь", id="ID заметки", новый_текст="Новый текст")
async def note_edit(interaction: discord.Interaction, пользователь: discord.Member, id: int, новый_текст: str):
    if not await utils.check_permissions(interaction):
        return
    await db.update_note(id, пользователь.id, новый_текст)
    await interaction.response.send_message(f"✅ Заметка #{id} обновлена.", ephemeral=True)
    logger.send_tg_log(f"📝 Заметка #{id} отредактирована для {пользователь} от {interaction.user}")