import discord
import json
import os
import datetime
import shutil
import zipfile
from datetime import timezone
import config  # глобальный конфиг для BACKUP_FOLDER, BACKUP_MAX_KEEP и т.д.
import logger

class BackupManager:
    def __init__(self, bot):
        self.bot = bot

    async def create_backup(self, guild: discord.Guild) -> str:
        """
        Создаёт полный бэкап структуры сервера.
        Возвращает путь к созданному ZIP-архиву.
        """
        if not os.path.exists(config.BACKUP_FOLDER):
            os.makedirs(config.BACKUP_FOLDER)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{guild.id}_{timestamp}"
        backup_folder = os.path.join(config.BACKUP_FOLDER, backup_name)
        os.makedirs(backup_folder)

        backup_data = {
            "guild_id": guild.id,
            "guild_name": guild.name,
            "guild_icon": str(guild.icon.url) if guild.icon else None,
            "guild_banner": str(guild.banner.url) if guild.banner else None,
            "guild_description": guild.description,
            "created_at": datetime.datetime.now(timezone.utc).isoformat(),
            "channels": [],
            "categories": [],
            "roles": []
        }

        # Сохраняем роли
        for role in guild.roles:
            if role.name != "@everyone":
                role_data = {
                    "id": role.id,
                    "name": role.name,
                    "color": role.color.value,
                    "hoist": role.hoist,
                    "mentionable": role.mentionable,
                    "permissions": role.permissions.value,
                    "position": role.position
                }
                backup_data["roles"].append(role_data)

        # Сохраняем категории и каналы
        for category in guild.categories:
            cat_data = {
                "id": category.id,
                "name": category.name,
                "position": category.position,
                "channels": []
            }

            for channel in category.channels:
                chan_data = {
                    "id": channel.id,
                    "name": channel.name,
                    "type": str(channel.type),
                    "position": channel.position,
                    "topic": getattr(channel, 'topic', None),
                    "nsfw": getattr(channel, 'nsfw', False),
                    "slowmode_delay": getattr(channel, 'slowmode_delay', 0)
                }
                cat_data["channels"].append(chan_data)

            backup_data["categories"].append(cat_data)

        # Сохраняем каналы без категории
        for channel in guild.channels:
            if channel.category is None and not isinstance(channel, discord.CategoryChannel):
                chan_data = {
                    "id": channel.id,
                    "name": channel.name,
                    "type": str(channel.type),
                    "position": channel.position,
                    "topic": getattr(channel, 'topic', None),
                    "nsfw": getattr(channel, 'nsfw', False),
                    "slowmode_delay": getattr(channel, 'slowmode_delay', 0)
                }
                backup_data["channels"].append(chan_data)

        # Сохраняем в JSON
        json_path = os.path.join(backup_folder, "structure.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)

        # Создаём архив
        zip_path = os.path.join(config.BACKUP_FOLDER, f"{backup_name}.zip")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(json_path, arcname="structure.json")

        # Удаляем временную папку
        shutil.rmtree(backup_folder)

        # Ротация старых бэкапов
        await self.rotate_backups(guild)

        return zip_path

    async def rotate_backups(self, guild: discord.Guild):
        """Удаляет старые бэкапы, оставляя только BACKUP_MAX_KEEP последних."""
        backups = []
        for filename in os.listdir(config.BACKUP_FOLDER):
            if filename.startswith(f"backup_{guild.id}_") and filename.endswith(".zip"):
                filepath = os.path.join(config.BACKUP_FOLDER, filename)
                backups.append((os.path.getmtime(filepath), filepath))

        backups.sort(reverse=True)  # сначала новые

        # Удаляем старые
        for i, (_, filepath) in enumerate(backups):
            if i >= config.BACKUP_MAX_KEEP:
                os.remove(filepath)
                logger.send_tg_log(f"🗑️ Удалён старый бэкап: {os.path.basename(filepath)}")

    async def restore_backup(self, guild: discord.Guild, backup_file: str):
        """
        Восстанавливает сервер из бэкапа.
        Внимание: это удалит все текущие каналы и создаст новые!
        Функция пока в разработке.
        """
        # TODO: реализовать восстановление
        pass

# Глобальный экземпляр (будет инициализирован в main.py)
backup_manager = None