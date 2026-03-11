import asyncpg
import datetime
import json
from datetime import timezone
from typing import Optional, List, Tuple

class Database:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool = None

    async def connect(self):
        """Создаёт пул соединений и все необходимые таблицы."""
        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=10, timeout=10)
        async with self.pool.acquire() as conn:
            # Таблица пользователей (базовая информация)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    discord_id BIGINT PRIMARY KEY,
                    username TEXT NOT NULL
                )
            ''')

            # Таблица активных наказаний (штрафы и варны)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS punishments (
                    id BIGSERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL REFERENCES users(discord_id) ON DELETE CASCADE,
                    type TEXT NOT NULL CHECK (type IN ('warn', 'fine')),
                    amount INTEGER,
                    reason TEXT NOT NULL,
                    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    paid_at TIMESTAMPTZ,
                    last_reminded_at TIMESTAMPTZ,
                    status TEXT NOT NULL CHECK (status IN ('active', 'paid', 'expired', 'removed')),
                    message_id BIGINT NOT NULL,
                    channel_id BIGINT NOT NULL
                )
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS server_config (
                    guild_id BIGINT PRIMARY KEY,
                    config JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            ''')

            # Индексы для быстрого поиска
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_user_status ON punishments(user_id, status)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_status_issued ON punishments(status, issued_at)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_status_paid ON punishments(status, paid_at)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_last_reminded ON punishments(last_reminded_at) WHERE status = \'active\'')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_user_guild ON punishments(user_id, guild_id)')

            # Добавляем колонку fine_id, если её нет (связь варна со штрафом)
            await self._add_fine_id_column(conn)

            # Таблица истории наказаний (навсегда)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS punishment_history (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    type TEXT NOT NULL,
                    amount INTEGER,
                    reason TEXT NOT NULL,
                    issued_at TIMESTAMPTZ NOT NULL,
                    paid_at TIMESTAMPTZ,
                    removed_at TIMESTAMPTZ,
                    status TEXT NOT NULL,
                    guild_id BIGINT NOT NULL,
                    message_id BIGINT,
                    channel_id BIGINT,
                    fine_id BIGINT
                )
            ''')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_history_user_id ON punishment_history(user_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_history_issued ON punishment_history(issued_at)')

            # Таблица последней активности пользователя
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_reputation (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT NOT NULL,
                    last_seen TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            ''')

            # Таблица заметок о пользователях
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS notes (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    author_id BIGINT NOT NULL,
                    note TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            ''')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_notes_user_id ON notes(user_id)')

            # Таблица привязки Discord к игровому нику Stalcraft
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS game_links (
                    discord_id BIGINT PRIMARY KEY,
                    game_nick TEXT NOT NULL,
                    region TEXT NOT NULL,
                    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            ''')

    async def _add_fine_id_column(self, conn):
        """Проверяет наличие колонки fine_id в punishments и добавляет при отсутствии."""
        result = await conn.fetchrow("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='punishments' AND column_name='fine_id'
        """)
        if not result:
            await conn.execute("ALTER TABLE punishments ADD COLUMN fine_id BIGINT REFERENCES punishments(id) ON DELETE SET NULL")
            await conn.execute("CREATE INDEX idx_fine_id ON punishments(fine_id) WHERE fine_id IS NOT NULL")
            print("✅ Колонка fine_id добавлена")

    async def close(self):
        """Закрывает пул соединений."""
        await self.pool.close()

    # ---------- Работа с пользователями ----------
    async def ensure_user(self, discord_id: int, username: str):
        """Добавляет пользователя в таблицу users, если его нет, или обновляет имя."""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO users (discord_id, username) VALUES ($1, $2)
                ON CONFLICT (discord_id) DO UPDATE SET username = EXCLUDED.username
            ''', discord_id, username)

    # ---------- Работа с последней активностью ----------
    async def update_user_last_seen(self, user_id: int, username: str):
        """Обновляет время последнего появления пользователя."""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO user_reputation (user_id, username, last_seen, updated_at)
                VALUES ($1, $2, NOW(), NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    last_seen = NOW(),
                    updated_at = NOW()
            ''', user_id, username)

    # ---------- История наказаний ----------
    async def add_punishment_history(self, guild_id: int, user_id: int, username: str,
                                     p_type: str, amount: Optional[int], reason: str,
                                     issued_at: datetime.datetime, paid_at: Optional[datetime.datetime] = None,
                                     removed_at: Optional[datetime.datetime] = None,
                                     status: str = 'active', message_id: int = 0, channel_id: int = 0,
                                     fine_id: Optional[int] = None):
        """Сохраняет запись о наказании в историю (неактивные наказания)."""
        await self.ensure_user(user_id, username)
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO punishment_history
                    (user_id, type, amount, reason, issued_at, paid_at, removed_at, status, guild_id, message_id, channel_id, fine_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ''', user_id, p_type, amount, reason, issued_at, paid_at, removed_at, status, guild_id, message_id, channel_id, fine_id)

    async def get_user_history(self, user_id: int):
        """Возвращает запись из user_reputation и все записи из punishment_history для пользователя."""
        async with self.pool.acquire() as conn:
            rep = await conn.fetchrow('SELECT * FROM user_reputation WHERE user_id = $1', user_id)
            punishments = await conn.fetch('''
                SELECT * FROM punishment_history WHERE user_id = $1 ORDER BY issued_at DESC
            ''', user_id)
            return rep, punishments

    # ---------- Активные наказания (основные методы) ----------
    async def add_punishment(self, guild_id: int, user_id: int, username: str,
                             p_type: str, amount: Optional[int], reason: str,
                             message_id: int, channel_id: int, fine_id: Optional[int] = None,
                             issued_at: Optional[datetime.datetime] = None,
                             paid_at: Optional[datetime.datetime] = None) -> int:
        """Добавляет активное наказание (штраф или варн)."""
        await self.ensure_user(user_id, username)
        if issued_at is None:
            issued_at = datetime.datetime.now(timezone.utc).replace(tzinfo=None)
        async with self.pool.acquire() as conn:
            return await conn.fetchval('''
                INSERT INTO punishments
                    (guild_id, user_id, type, amount, reason, status, message_id, channel_id, fine_id, issued_at, paid_at)
                VALUES ($1, $2, $3, $4, $5, 'active', $6, $7, $8, $9, $10)
                RETURNING id
            ''', guild_id, user_id, p_type, amount, reason, message_id, channel_id, fine_id, issued_at, paid_at)

    async def update_punishment_status(self, punishment_id: int, status: str, paid_at: Optional[datetime.datetime] = None):
        """Обновляет статус активного наказания."""
        async with self.pool.acquire() as conn:
            if paid_at:
                await conn.execute('''
                    UPDATE punishments SET status = $1, paid_at = $2 WHERE id = $3
                ''', status, paid_at, punishment_id)
            else:
                await conn.execute('UPDATE punishments SET status = $1 WHERE id = $2', status, punishment_id)

    async def update_last_reminded(self, punishment_id: int):
        """Обновляет время последнего напоминания о штрафе."""
        async with self.pool.acquire() as conn:
            await conn.execute('UPDATE punishments SET last_reminded_at = NOW() WHERE id = $1', punishment_id)

    async def get_fines_for_reminder(self, interval_hours: int) -> List[asyncpg.Record]:
        """Возвращает активные штрафы, по которым давно не напоминали."""
        cutoff = datetime.datetime.now(timezone.utc).replace(tzinfo=None) - datetime.timedelta(hours=interval_hours)
        async with self.pool.acquire() as conn:
            return await conn.fetch('''
                SELECT * FROM punishments
                WHERE type = 'fine' AND status = 'active'
                  AND (last_reminded_at IS NULL OR last_reminded_at < $1)
            ''', cutoff)

    async def get_active_fines(self, user_id: Optional[int] = None) -> List[asyncpg.Record]:
        """Возвращает все активные штрафы (опционально для конкретного пользователя)."""
        async with self.pool.acquire() as conn:
            if user_id is None:
                return await conn.fetch('SELECT * FROM punishments WHERE type = $1 AND status = $2',
                                        'fine', 'active')
            else:
                return await conn.fetch('SELECT * FROM punishments WHERE user_id = $1 AND type = $2 AND status = $3',
                                        user_id, 'fine', 'active')

    async def get_active_warns(self, user_id: Optional[int] = None) -> List[asyncpg.Record]:
        """Возвращает все активные варны (опционально для конкретного пользователя)."""
        async with self.pool.acquire() as conn:
            if user_id is None:
                return await conn.fetch('SELECT * FROM punishments WHERE type = $1 AND status = $2',
                                        'warn', 'active')
            else:
                return await conn.fetch('SELECT * FROM punishments WHERE user_id = $1 AND type = $2 AND status = $3',
                                        user_id, 'warn', 'active')

    async def get_user_active_punishments(self, user_id: int) -> List[asyncpg.Record]:
        """Возвращает все активные наказания пользователя (и штрафы, и варны)."""
        async with self.pool.acquire() as conn:
            return await conn.fetch('''
                SELECT * FROM punishments WHERE user_id = $1 AND status = $2
            ''', user_id, 'active')

    async def get_old_fines(self, days: int) -> List[asyncpg.Record]:
        """Возвращает неоплаченные штрафы старше days дней."""
        cutoff = datetime.datetime.now(timezone.utc).replace(tzinfo=None) - datetime.timedelta(days=days)
        async with self.pool.acquire() as conn:
            return await conn.fetch('''
                SELECT * FROM punishments
                WHERE type = $1 AND status = $2 AND issued_at < $3
            ''', 'fine', 'active', cutoff)

    async def get_warn_count_for_fine(self, fine_id: int) -> int:
        """Количество варнов, связанных с конкретным штрафом (включая все статусы)."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval('SELECT COUNT(*) FROM punishments WHERE fine_id = $1', fine_id)

    async def get_punishments_to_auto_remove(self, p_type: str, statuses: List[str], days: int) -> List[asyncpg.Record]:
        """
        Возвращает наказания для автоматического снятия.
        Для варнов: status='active', смотрим issued_at.
        Для штрафов: status='paid', смотрим issued_at.
        """
        date_col = 'issued_at'
        cutoff = datetime.datetime.now(timezone.utc).replace(tzinfo=None) - datetime.timedelta(days=days)
        async with self.pool.acquire() as conn:
            query = f'''
                SELECT * FROM punishments
                WHERE type = $1 AND status = ANY($2::text[]) AND {date_col} < $3
            '''
            return await conn.fetch(query, p_type, statuses, cutoff)

    async def get_paid_fines_to_remove(self, days: int) -> List[asyncpg.Record]:
        """Оплаченные штрафы, выданные более days дней назад."""
        cutoff = datetime.datetime.now(timezone.utc).replace(tzinfo=None) - datetime.timedelta(days=days)
        async with self.pool.acquire() as conn:
            return await conn.fetch('''
                SELECT * FROM punishments
                WHERE type = $1 AND status = $2 AND issued_at < $3
            ''', 'fine', 'paid', cutoff)

    async def get_warn_count(self, user_id: int) -> int:
        """Количество активных варнов у пользователя."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval('''
                SELECT COUNT(*) FROM punishments
                WHERE user_id = $1 AND type = $2 AND status = $3
            ''', user_id, 'warn', 'active')

    async def get_punishment_by_id(self, punishment_id: int) -> Optional[asyncpg.Record]:
        """Возвращает наказание по его ID (из таблицы punishments)."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow('SELECT * FROM punishments WHERE id = $1', punishment_id)

    async def update_punishment(self, punishment_id: int, amount: Optional[int], reason: str):
        """Обновляет сумму и причину активного штрафа."""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE punishments SET amount = $1, reason = $2
                WHERE id = $3 AND type = $4 AND status = $5
            ''', amount, reason, punishment_id, 'fine', 'active')

    # ---------- Работа с заметками ----------
    async def add_note(self, user_id: int, author_id: int, note: str):
        """Добавляет заметку о пользователе."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval('''
                INSERT INTO notes (user_id, author_id, note, created_at, updated_at)
                VALUES ($1, $2, $3, NOW(), NOW())
                RETURNING id
            ''', user_id, author_id, note)

    async def get_user_notes(self, user_id: int):
        """Возвращает все заметки о пользователе."""
        async with self.pool.acquire() as conn:
            return await conn.fetch('''
                SELECT * FROM notes WHERE user_id = $1 ORDER BY created_at DESC
            ''', user_id)

    async def delete_note(self, note_id: int, user_id: int):
        """Удаляет заметку по ID (проверяет, что заметка принадлежит указанному пользователю)."""
        async with self.pool.acquire() as conn:
            await conn.execute('DELETE FROM notes WHERE id = $1 AND user_id = $2', note_id, user_id)

    async def update_note(self, note_id: int, user_id: int, new_text: str):
        """Обновляет текст заметки."""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE notes SET note = $1, updated_at = NOW()
                WHERE id = $2 AND user_id = $3
            ''', new_text, note_id, user_id)

    # ---------- Привязка игровых аккаунтов ----------
    async def add_game_link(self, discord_id: int, game_nick: str, region: str):
        """Сохраняет или обновляет привязку Discord -> игровой ник."""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO game_links (discord_id, game_nick, region, last_updated)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (discord_id) DO UPDATE SET
                    game_nick = EXCLUDED.game_nick,
                    region = EXCLUDED.region,
                    last_updated = NOW()
            ''', discord_id, game_nick, region)

    async def get_game_link(self, discord_id: int):
        """Возвращает привязку для указанного Discord ID."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow('SELECT * FROM game_links WHERE discord_id = $1', discord_id)

    async def remove_game_link(self, discord_id: int):
        """Удаляет привязку."""
        async with self.pool.acquire() as conn:
            await conn.execute('DELETE FROM game_links WHERE discord_id = $1', discord_id)

    async def get_server_config(self, guild_id: int) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT config FROM server_config WHERE guild_id = $1', guild_id)
            if row:
                config_data = row['config']
                if isinstance(config_data, str):
                    return json.loads(config_data)
                elif isinstance(config_data, dict):
                    return config_data
            return {}

    async def save_server_config(self, guild_id: int, config_data: dict):
        print(f"DEBUG save_server_config: type={type(config_data)}, data={config_data}")
        # если config_data не словарь, преобразуем
        if not isinstance(config_data, dict):
            try:
                config_data = dict(config_data)  # попробуем преобразовать
            except:
                print(f"❌ Не удалось преобразовать {config_data} в словарь")
                return
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO server_config (guild_id, config, updated_at)
                VALUES ($1, $2::jsonb, NOW())
                ON CONFLICT (guild_id) DO UPDATE SET
                    config = EXCLUDED.config,
                    updated_at = NOW()
            ''', guild_id, json.dumps(config_data))

    async def get_server_config_with_time(self, guild_id: int) -> Tuple[dict, Optional[datetime.datetime]]:
        """Возвращает (config, updated_at) для гильдии. config всегда словарь."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT config, updated_at FROM server_config WHERE guild_id = $1', guild_id)
            if row:
                config_data = row['config']
                # Если пришла строка JSON, парсим её
                if isinstance(config_data, str):
                    config_data = json.loads(config_data)
                elif not isinstance(config_data, dict):
                    config_data = {}
                return config_data, row['updated_at']
            return {}, None

    async def get_server_config_updated_at(self, guild_id: int) -> Optional[datetime.datetime]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT updated_at FROM server_config WHERE guild_id = $1', guild_id)
            return row['updated_at'] if row else None