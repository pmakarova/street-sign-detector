"""
Асинхронное хранилище результатов в Redis.
"""
import json
import logging
from typing import Optional, List, Dict, Any
import redis.asyncio as aioredis
from app.core.config import settings

logger = logging.getLogger(__name__)

REDIS_TTL = 3600  # 1 час


class ResultStorage:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis: aioredis.Redis | None = None

    async def connect(self):
        self.redis = await aioredis.from_url(self.redis_url, decode_responses=True)
        self._connected = True
        logger.info("Connected to Redis")

    async def close(self):
        if self.redis:
            await self.redis.close()
            self._connected = False
            logger.info("Redis connection closed")

    @property
    def is_connected(self) -> bool: 
        """Возвращает True, если Redis подключен."""
        return self._connected

    def _key(self, task_id: str, suffix: str) -> str:
        return f"task:{task_id}:{suffix}"

    async def set_task_status(self, task_id: str, status: str):
        await self.redis.set(self._key(task_id, "status"), status, ex=REDIS_TTL)

    async def set_result(self, task_id: str, detections: List[Dict[str, Any]]):
        pipe = self.redis.pipeline()
        pipe.set(self._key(task_id, "detections"), json.dumps(detections), ex=REDIS_TTL)
        pipe.set(self._key(task_id, "status"), "completed", ex=REDIS_TTL)
        await pipe.execute()

    async def set_error(self, task_id: str, error_msg: str):
        pipe = self.redis.pipeline()
        pipe.set(self._key(task_id, "error"), error_msg, ex=REDIS_TTL)
        pipe.set(self._key(task_id, "status"), "failed", ex=REDIS_TTL)
        await pipe.execute()

    async def get_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        status = await self.redis.get(self._key(task_id, "status"))
        if not status:
            return None

        result = {"task_id": task_id, "status": status}
        detections_raw = await self.redis.get(self._key(task_id, "detections"))
        error_msg = await self.redis.get(self._key(task_id, "error"))

        if detections_raw:
            result["detections"] = json.loads(detections_raw)
        if error_msg:
            result["error_message"] = error_msg
        return result