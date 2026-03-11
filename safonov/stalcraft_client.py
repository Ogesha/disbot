import asyncio
from scapi import AppClient
from scapi.exceptions import NotFoundError
from datetime import datetime, timezone
import config
import logger

class StalcraftClient:
    def __init__(self):
        self.clients = {}
        self._init_clients()

    def _init_clients(self):
        if not config.STALCRAFT_CLIENT_ID or not config.STALCRAFT_CLIENT_SECRET:
            logger.send_tg_log("⚠️ Stalcraft API credentials not configured")
            return
        regions = ['eu', 'ru', 'dev']
        for region in regions:
            try:
                self.clients[region] = AppClient(
                    client_id=str(config.STALCRAFT_CLIENT_ID),
                    client_secret=config.STALCRAFT_CLIENT_SECRET,
                    region=region
                )
                logger.send_tg_log(f"✅ Stalcraft client created for region {region}")
            except Exception as e:
                logger.send_tg_log(f"❌ Stalcraft client init error for {region}: {e}")

    def get_client(self, region=None):
        if region is None:
            region = config.STALCRAFT_REGION
        region_key = region.lower()
        return self.clients.get(region_key)

    def _get_attr(self, obj, name):
        if hasattr(obj, name):
            return getattr(obj, name)
        elif isinstance(obj, dict):
            return obj.get(name)
        return None

    async def get_player_info(self, nickname: str, region: str = None):
        client = self.get_client(region)
        if not client:
            logger.send_tg_log(f"⚠️ No Stalcraft client for region {region or config.STALCRAFT_REGION}")
            return None

        logger.send_tg_log(
            f"🔍 Stalcraft request: profile {nickname} in region {(region or config.STALCRAFT_REGION).upper()}")
        try:
            profile = await client.profile(nickname)
            if not profile:
                logger.send_tg_log(f"⚠️ Stalcraft profile {nickname} returned empty")
                return None

            logger.send_tg_log(f"✅ Stalcraft profile {nickname} received")

            acc_id = self._get_attr(profile, 'uuid') or self._get_attr(profile, 'id')
            acc_name = self._get_attr(profile, 'name') or nickname

            created_at_str = self._get_attr(profile, 'createdAt')
            created_at = None
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                except:
                    pass

            last_login = self._get_attr(profile, 'last_login')
            if isinstance(last_login, datetime):
                last_login = last_login.astimezone(timezone.utc)

            # Информация о клане (исправлено)
            clan_info = None
            clan_obj = self._get_attr(profile, 'clan')
            if clan_obj:
                # Пробуем получить название клана
                clan_name = None
                # Вариант 1: через info (как в реальных данных)
                info_obj = self._get_attr(clan_obj, 'info')
                if info_obj:
                    clan_name = self._get_attr(info_obj, 'name')
                # Вариант 2: прямой name
                if not clan_name:
                    clan_name = self._get_attr(clan_obj, 'name')
                # Вариант 3: запасной
                if not clan_name and hasattr(clan_obj, '__dict__'):
                    clan_name = clan_obj.__dict__.get('name')

                # Получаем информацию об участнике
                member_info = self._get_attr(clan_obj, 'member')
                join_time = None
                rank = None
                if member_info:
                    join_time = self._get_attr(member_info, 'join_time')
                    if isinstance(join_time, datetime):
                        join_time = join_time.astimezone(timezone.utc)
                    rank_obj = self._get_attr(member_info, 'rank')
                    if rank_obj:
                        rank = rank_obj.value if hasattr(rank_obj, 'value') else str(rank_obj)

                clan_info = {
                    'name': clan_name,
                    'join_time': join_time,
                    'rank': rank
                }

            stats = self._get_attr(profile, 'stats')
            kills = 0
            deaths = 0
            total_playtime_ms = 0
            registration_date = None

            if stats and isinstance(stats, list):
                for stat in stats:
                    if hasattr(stat, 'id'):
                        if stat.id == 'kil':
                            kills = stat.value
                        elif stat.id == 'dea':
                            deaths = stat.value
                        elif stat.id == 'pla-tim':
                            total_playtime_ms = stat.value
                        elif stat.id == 'reg-tim' and hasattr(stat, 'value'):
                            try:
                                registration_date = datetime.fromisoformat(stat.value.replace('Z', '+00:00'))
                            except:
                                pass

            if not registration_date:
                registration_date = created_at

            if kills > 0 and deaths > 0:
                kd = round(kills / deaths, 2)
            elif kills > 0:
                kd = float(kills)
            else:
                kd = 0.0

            total_playtime_hours = total_playtime_ms / (1000 * 3600) if total_playtime_ms else 0

            avg_daily_hours = 0
            if total_playtime_hours > 0 and registration_date:
                end_date = last_login if last_login else datetime.now(timezone.utc)
                days_active = (end_date - registration_date).days
                if days_active > 0:
                    avg_daily_hours = round(total_playtime_hours / days_active, 2)

            result = {
                'account_name': acc_name,
                'account_id': acc_id,
                'registration_date': registration_date,
                'created_at': created_at,
                'last_login': last_login,
                'total_playtime_hours': round(total_playtime_hours, 2),
                'avg_daily_hours': avg_daily_hours,
                'clan': clan_info,
                'characters': [
                    {
                        'name': acc_name,
                        'id': acc_id,
                        'pvp_kills': kills,
                        'pvp_deaths': deaths,
                        'kd': kd
                    }
                ]
            }
            logger.send_tg_log(f"✅ Stalcraft data prepared for {nickname}")
            return result

        except NotFoundError as e:
            logger.send_tg_log(
                f"⚠️ Stalcraft 404: player {nickname} not found in region {(region or config.STALCRAFT_REGION).upper()}")
            return None
        except Exception as e:
            logger.send_tg_log(f"⚠️ Stalcraft API error (profile): {type(e).__name__}: {e}")
            return None

stalcraft = StalcraftClient()