import aiohttp
import asyncio
from datetime import datetime, timezone
import base64
import config
import logger

class StalcraftDirectClient:
    BASE_URLS = {
        'eu': 'https://eapi.stalcraft.net',
        'ru': 'https://ru-api.stalcraft.net',  # предположительно
        'dev': 'https://dapi.stalcraft.net'
    }

    def __init__(self):
        self.access_token = None
        self.token_expires = None
        self._token_lock = asyncio.Lock()

    async def _get_app_token(self):
        """Получает AppToken через OAuth2 client credentials grant."""
        if self.access_token and self.token_expires and datetime.now(timezone.utc) < self.token_expires:
            return self.access_token

        async with self._token_lock:
            # Повторная проверка после захвата блокировки
            if self.access_token and self.token_expires and datetime.now(timezone.utc) < self.token_expires:
                return self.access_token

            auth_str = f"{config.STALCRAFT_CLIENT_ID}:{config.STALCRAFT_CLIENT_SECRET}"
            b64_auth = base64.b64encode(auth_str.encode()).decode()

            headers = {
                'Authorization': f'Basic {b64_auth}',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            data = {'grant_type': 'client_credentials'}

            async with aiohttp.ClientSession() as session:
                async with session.post('https://api.stalcraft.net/oauth/token', headers=headers, data=data) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.send_tg_log(f"❌ Failed to get token: {resp.status} - {text}")
                        return None
                    token_data = await resp.json()
                    self.access_token = token_data['access_token']
                    expires_in = token_data.get('expires_in', 3600)
                    self.token_expires = datetime.now(timezone.utc) + datetime.timedelta(seconds=expires_in - 60)  # запас 1 минута
                    return self.access_token

    async def _request(self, method, endpoint, region=None, params=None):
        """Универсальный метод для запросов к API."""
        token = await self._get_app_token()
        if not token:
            return None

        base_url = self.BASE_URLS.get(region, self.BASE_URLS['eu'])
        url = f"{base_url}{endpoint}"
        headers = {'Authorization': f'Bearer {token}'}

        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    text = await resp.text()
                    logger.send_tg_log(f"⚠️ API error {resp.status} for {url}: {text[:200]}")
                    return None

    async def get_profile(self, nickname: str, region: str = 'eu'):
        """Получить профиль игрока по нику."""
        return await self._request('GET', f'/profile/{nickname}', region=region)

    async def get_character_stats(self, character_id: str, region: str = 'eu'):
        """Получить статистику персонажа по ID."""
        return await self._request('GET', f'/character/stats/{character_id}', region=region)

    async def get_player_info(self, nickname: str, region: str = None):
        """
        Основной метод: получает профиль и статистику игрока.
        Возвращает словарь в едином формате.
        """
        if region is None:
            region = config.STALCRAFT_REGION

        profile = await self.get_profile(nickname, region)
        if not profile:
            return None

        # Извлекаем ID персонажа (предполагаем, что в профиле есть поле 'id')
        character_id = profile.get('id') or profile.get('uuid')
        if not character_id:
            logger.send_tg_log(f"⚠️ No character ID found in profile for {nickname}")
            return None

        # Получаем статистику
        stats = await self.get_character_stats(character_id, region)

        # Отладка: выводим структуру статистики
        logger.send_tg_log(f"DEBUG: stats response for {nickname}: {stats}")

        # Извлекаем убийства и смерти
        kills = 0
        deaths = 0
        if stats and isinstance(stats, dict):
            # Пытаемся найти pvp.kills / pvp.deaths
            pvp = stats.get('pvp')
            if pvp and isinstance(pvp, dict):
                kills = pvp.get('kills', 0)
                deaths = pvp.get('deaths', 0)
            else:
                # Возможно, другой путь
                kills = stats.get('kills', 0)
                deaths = stats.get('deaths', 0)

        # Вычисляем K/D
        if kills > 0 and deaths > 0:
            kd = round(kills / deaths, 2)
        elif kills > 0:
            kd = kills
        else:
            kd = 0.0

        # Извлекаем клан и дату создания из профиля
        clan_name = None
        clan_obj = profile.get('clan')
        if clan_obj:
            clan_name = clan_obj.get('name') if isinstance(clan_obj, dict) else str(clan_obj)

        created_at_str = profile.get('createdAt')
        created_at = None
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            except:
                pass

        return {
            'account_name': nickname,
            'account_id': character_id,
            'created_at': created_at,
            'characters': [
                {
                    'name': nickname,  # имя персонажа (обычно совпадает с ником)
                    'id': character_id,
                    'clan': clan_name,
                    'pvp_kills': kills,
                    'pvp_deaths': deaths,
                    'kd': kd
                }
            ]
        }

# Глобальный экземпляр
stalcraft = StalcraftDirectClient()