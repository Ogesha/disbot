import datetime
import config
from db_client import db

class GuildConfig:
    def __init__(self, guild_id: int, data: dict, updated_at: datetime.datetime = None):
        print(f"GuildConfig.__init__ для {guild_id}, data keys: {list(data.keys())}")
        self.guild_id = guild_id
        self.data = data
        self.updated_at = updated_at or datetime.datetime.now(datetime.timezone.utc)
        self.last_checked = datetime.datetime.now(datetime.timezone.utc)
        print("GuildConfig.__init__ завершён")

    def get(self, key, default=None):
        """Возвращает значение из БД, если есть, иначе из config.py (глобальный fallback)."""
        if key in self.data:
            return self.data[key]
        if hasattr(config, key):
            return getattr(config, key)
        return default

    def set(self, key, value):
        self.data[key] = value

class ConfigManager:
    def __init__(self, check_interval_seconds=60):
        self.guild_configs = {}
        self.check_interval = datetime.timedelta(seconds=check_interval_seconds)

    async def load_guild(self, guild_id: int) -> GuildConfig:
        try:
            print(f"load_guild({guild_id}): запрос к БД...")
            data, updated_at = await db.get_server_config_with_time(guild_id)
            print(f"load_guild({guild_id}): получены данные, создаём объект GuildConfig")
            print(f"load_guild({guild_id}): data keys: {list(data.keys()) if data else 'None'}")
            cfg = GuildConfig(guild_id, data, updated_at)
            print(f"load_guild({guild_id}): объект создан, сохраняем в кэш")
            self.guild_configs[guild_id] = cfg
            print(f"load_guild({guild_id}): конфиг загружен в кэш")
            return cfg
        except Exception as e:
            print(f"❌ Ошибка в load_guild: {type(e).__name__}: {e}")
            raise

    async def load_all_guilds(self, guild_ids):
        print(f"load_all_guilds: начинаем загрузку для {len(guild_ids)} гильдий")
        for gid in guild_ids:
            print(f"Загружаем конфиг для гильдии {gid}...")
            await self.load_guild(gid)
            print(f"Конфиг для {gid} загружен")
        print("load_all_guilds: все конфиги загружены")

    async def get_config(self, guild_id: int) -> GuildConfig:
        """Возвращает конфиг для гильдии, при необходимости обновляя кэш."""
        cfg = self.guild_configs.get(guild_id)
        now = datetime.datetime.now(datetime.timezone.utc)

        if not cfg:
            return await self.load_guild(guild_id)

        if now - cfg.last_checked > self.check_interval:
            db_updated = await db.get_server_config_updated_at(guild_id)
            if db_updated and (not cfg.updated_at or db_updated > cfg.updated_at):
                cfg = await self.load_guild(guild_id)
            else:
                cfg.last_checked = now
        return cfg

    async def update_config(self, guild_id: int, new_data: dict):
        print(f"DEBUG update_config: type={type(new_data)}")
        await db.save_server_config(guild_id, new_data)
        await self.load_guild(guild_id)

    async def reload_guild(self, guild_id: int):
        """Принудительная перезагрузка конфига гильдии из БД."""
        await self.load_guild(guild_id)

# Глобальный экземпляр
config_manager = ConfigManager()