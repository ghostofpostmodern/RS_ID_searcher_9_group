import json
import time
import logging
from typing import Optional, List, Tuple

import redis.asyncio as redis

from .config import settings


class CacheManager:
    """
    Управляет:
    - кэшем SNP-результатов (JSON payload c PDF)
    - историей запросов пользователя (ZSET)
    - rate limiting (ограничение запросов/час)
    """

    def __init__(self) -> None:
        self._redis = redis.from_url(settings.redis_url, decode_responses=True)
        self._ttl = settings.cache_ttl  # TTL для SNP результата (24ч по умолчанию)

    # =====================================================================
    # 1. КЭШ SNP РЕЗУЛЬТАТОВ
    # =====================================================================

    async def get_snp_result(self, rsid: str) -> Optional[dict]:
        """
        Возвращает payload:
        {
            "rsid": ...,
            "populations": ...,
            "extended_summary": ...,
            "images": [...],
            "pdf": "/app/reports/rs123.pdf"
        }
        """
        key = f"snp:{rsid}:v1"
        data = await self._redis.get(key)
        if not data:
            logging.info("No data found in cache")
            return None

        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return None

    async def set_snp_result(self, rsid: str, payload: dict) -> None:
        """
        payload должен быть сериализуем в JSON.
        PDF-файл хранится на диске, в Redis кладётся только путь.
        """
        key = f"snp:{rsid}:v1"
        await self._redis.set(key, json.dumps(payload), ex=self._ttl)

    # =====================================================================
    # 2. ИСТОРИЯ ЗАПРОСОВ (последние 24 часа)
    # =====================================================================

    async def add_history_entry(self, user_id: int, rsid: str) -> None:
        """
        История хранится как ZSET:
            member = rsid
            score  = Unix timestamp
        """
        key = f"history:{user_id}"
        now = time.time()

        await self._redis.zadd(key, {rsid: now})
        await self._redis.expire(key, 2 * 86400)  # 2 дня
        logging.info("Cached an entry into user history")

    async def get_history(self, user_id: int) -> List[str]:
        """
        Возвращает rsID за последние 24 часа.

        Если история отсутствует в формате ZSET — пытается прочитать старый LIST.
        """
        key = f"history:{user_id}"
        now = time.time()
        day_ago = now - 86400

        logging.info("Getting user request history")
        try:
            rsids = await self._redis.zrangebyscore(key, min=day_ago, max=now)
        except Exception:
            rsids = []

        # Fallback: старый формат LIST
        if not rsids:
            try:
                legacy = await self._redis.lrange(key, 0, 9)
                return legacy
            except Exception:
                return []

        return rsids

    # =====================================================================
    # 3. RATE LIMITING (лимит N запросов в час)
    # =====================================================================

    async def register_request_and_check_limit(
        self,
        user_id: int,
        limit: int
    ) -> Tuple[bool, int]:
        """
        Инкрементирует счетчик запросов пользователя за текущий час.

        Возвращает:
            allowed: bool  — можно ли выполнять запрос
            remaining: int — сколько запросов осталось в текущем часе

        Логика:
        - ключ = rate:{user_id}:{hour_bucket}
        - hour_bucket = unix_timestamp // 3600
        - INCR увеличивает счетчик
        - если это первое увеличение — устанавливаем TTL=3600
        """
        now = int(time.time())
        hour_bucket = now // 3600
        key = f"rate:{user_id}:{hour_bucket}"

        current = await self._redis.incr(key)

        if current == 1:
            await self._redis.expire(key, 3600)  # живёт 1 час

        remaining = max(limit - current, 0)
        allowed = current <= limit

        return allowed, remaining


cache_manager = CacheManager()
