import json
import time
from typing import Optional, List, Tuple

import redis.asyncio as redis

from .config import settings


class CacheManager:
    def __init__(self) -> None:
        self._redis = redis.from_url(settings.redis_url, decode_responses=True)
        self._ttl = settings.cache_ttl

    # ---------- КЭШ РЕЗУЛЬТАТОВ ПО RSID ----------

    async def get_snp_result(self, rsid: str) -> Optional[dict]:
        key = f"snp:{rsid}:v1"
        data = await self._redis.get(key)
        if not data:
            return None
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return None

    async def set_snp_result(self, rsid: str, payload: dict) -> None:
        key = f"snp:{rsid}:v1"
        await self._redis.set(key, json.dumps(payload), ex=self._ttl)

    # ---------- ИСТОРИЯ ЗАПРОСОВ ПОЛЬЗОВАТЕЛЯ ----------

    async def add_history_entry(self, user_id: int, rsid: str) -> None:
        """
        Храним историю как sorted set:
        - ключ: history:{user_id}
        - score: Unix timestamp (секунды)
        - member: rsid
        """
        key = f"history:{user_id}"
        now = time.time()
        await self._redis.zadd(key, {rsid: now})
        # TTL истории — 2 суток
        await self._redis.expire(key, 2 * 86400)

    async def get_history(self, user_id: int) -> List[str]:
        """
        Возвращает список rsID за последние 24 часа.

        Если по какой-то причине ZSET пуст (или ключ не в том формате),
        пробуем старый вариант — LIST (на случай старой версии кода).
        """
        key = f"history:{user_id}"
        now = time.time()
        day_ago = now - 86400

        # сначала пробуем ZSET
        try:
            rsids = await self._redis.zrangebyscore(key, min=day_ago, max=now)
        except Exception:
            rsids = []

        if rsids:
            return rsids

        # fallback: старый формат LIST (если вдруг остался)
        try:
            rsids_list = await self._redis.lrange(key, 0, 9)
        except Exception:
            rsids_list = []

        # без фильтра по времени, просто последние до 10 штук
        return rsids_list

    # ---------- RATE LIMITING ----------

    async def register_request_and_check_limit(
        self, user_id: int, limit: int
    ) -> Tuple[bool, int]:
        """
        Инкрементирует счётчик запросов пользователя за текущий час
        и возвращает (allowed, remaining).

        Ключ: rate:{user_id}:{hour_bucket}
        """
        now = int(time.time())
        hour_bucket = now // 3600
        key = f"rate:{user_id}:{hour_bucket}"

        current = await self._redis.incr(key)
        if current == 1:
            # первый запрос в этом часе — ставим TTL
            await self._redis.expire(key, 3600)

        remaining = max(limit - current, 0)
        allowed = current <= limit
        return allowed, remaining


cache_manager = CacheManager()
