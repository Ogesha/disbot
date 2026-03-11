import discord
import datetime
from collections import defaultdict, deque
from datetime import timezone
import config
import logger

user_actions = defaultdict(lambda: deque(maxlen=5))

class AntiNuke:
    def __init__(self, bot):
        self.bot = bot

    async def check_action(self, user_id: int, action_type: str, guild: discord.Guild, cfg) -> bool:
        if not cfg.get('ANTI_NUKE_ENABLED', False):
            return False

        member = guild.get_member(user_id)
        if member:
            whitelist = cfg.get('ANTI_NUKE_WHITELIST_ROLE_IDS', [])
            if any(role.id in whitelist for role in member.roles):
                return False

        now = datetime.datetime.now(timezone.utc).timestamp()
        limit = cfg.get('ANTI_NUKE_ACTION_LIMIT', 5)
        interval = cfg.get('ANTI_NUKE_INTERVAL_SECONDS', 10)
        actions = user_actions[user_id]
        actions.append((now, action_type))

        cutoff = now - interval
        recent = [a for a in actions if a[0] > cutoff]
        if len(recent) >= limit:
            await self.apply_sanction(user_id, guild, cfg)
            return True
        return False

    async def apply_sanction(self, user_id: int, guild: discord.Guild, cfg):
        member = guild.get_member(user_id)
        if not member:
            return
        action = cfg.get('ANTI_NUKE_ACTION', 'ban')
        try:
            if action == 'ban':
                await member.ban(reason="Автоматический бан за попытку сноса сервера")
                action_text = "забанен"
            elif action == 'kick':
                await member.kick(reason="Автоматический кик за попытку сноса сервера")
                action_text = "кикнут"
            else:
                return

            log_channel = guild.get_channel(cfg.get('VIOLATION_LOG_CHANNEL_ID'))
            if log_channel:
                embed = discord.Embed(
                    title="🚨 Анти-Снос: обнаружена атака",
                    description=f"Пользователь {member.mention} {action_text}",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now(timezone.utc)
                )
                await log_channel.send(embed=embed)
            logger.send_tg_log(f"🚨 Анти-Снос: {member} ({user_id}) {action_text}")
        except Exception as e:
            logger.send_tg_log(f"❌ Ошибка при применении санкции к {user_id}: {e}")