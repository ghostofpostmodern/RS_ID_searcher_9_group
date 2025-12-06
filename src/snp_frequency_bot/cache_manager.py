import json
import time
from typing import Optional, List

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
        - score: Unix timestamp
        - member: rsid
        """
        key = f"history:{user_id}"
        now = time.time()
        await self._redis.zadd(key, {rsid: now})
        # Можно (не обязательно) поставить TTL на историю, например на 2 дня
        await self._redis.expire(key, 2 * 86400)

    async def get_history(self, user_id: int) -> List[str]:
        """
        Возвращает список rsID за последние 24 часа.
        """
        key = f"history:{user_id}"
        now = time.time()
        day_ago = now - 86400
        # Получаем все элементы с score в диапазоне [day_ago, now]
        rsids = await self._redis.zrangebyscore(key, min=day_ago, max=now)
        return rsids


cache_manager = CacheManager()
