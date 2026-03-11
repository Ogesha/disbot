import discord
from discord import app_commands
import os
import config
import utils
import logger
from backup import backup_manager

@app_commands.command(name="backup", description="Управление бэкапами сервера")
@app_commands.describe(action="Действие (create/list/restore)")
@app_commands.choices(action=[
    app_commands.Choice(name="Создать бэкап", value="create"),
    app_commands.Choice(name="Список бэкапов", value="list"),
    app_commands.Choice(name="Восстановить", value="restore")
])
async def cmd_backup(interaction: discord.Interaction, action: str):
    # Проверка прав: только администраторы с высокой ролью
    if not await utils.check_permissions(interaction):
        return

    await interaction.response.defer(ephemeral=False)

    if action == "create":
        try:
            backup_path = await backup_manager.create_backup(interaction.guild)
            embed = discord.Embed(
                title="✅ Бэкап создан",
                description=f"Файл: {os.path.basename(backup_path)}",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка: {e}")

    elif action == "list":
        backups = []
        for filename in os.listdir(config.BACKUP_FOLDER):
            if filename.startswith(f"backup_{interaction.guild.id}_") and filename.endswith(".zip"):
                filepath = os.path.join(config.BACKUP_FOLDER, filename)
                size = os.path.getsize(filepath) / 1024
                mod_time = os.path.getmtime(filepath)
                backups.append((mod_time, filename, size))

        if not backups:
            await interaction.followup.send("Нет бэкапов для этого сервера.")
            return

        backups.sort(reverse=True)
        embed = discord.Embed(title="📋 Список бэкапов", color=discord.Color.blue())
        for mod_time, filename, size in backups:
            date = datetime.datetime.fromtimestamp(mod_time).strftime("%d.%m.%Y %H:%M")
            embed.add_field(name=filename, value=f"📅 {date}\n📦 {size:.1f} KB", inline=False)
        await interaction.followup.send(embed=embed)

    elif action == "restore":
        await interaction.followup.send("Функция восстановления в разработке.")

# Добавьте в main.py импорт и регистрацию