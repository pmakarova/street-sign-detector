"""
Точка входа для worker-процесса.
Запускает асинхронный цикл консьюмера Kafka, обрабатывает задачи детекции.
"""
import asyncio
import logging
import os
import platform
import time
from pathlib import Path

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.services.kafka_consumer import KafkaConsumerManager
from app.services.result_storage import ResultStorage
from ml.predict import predict_from_file
from ml.model import load_model, ModelLoadError
from prometheus_client import start_http_server
from app.metrics import inference_time, model_status, tasks_in_progress

setup_logging()
logger = logging.getLogger(__name__)

WORKER_ID = f"{platform.node()}-{os.getpid()}"

def cleanup_old_files(upload_dir: str, max_age_seconds: int = 1800):
    """Удаляет файлы старше max_age_seconds в upload_dir (не рекурсивно)."""
    try:
        base = Path(upload_dir)
        if not base.exists():
            return
        now = time.time()
        for path in base.iterdir():
            if path.is_file():
                age = now - path.stat().st_mtime
                if age > max_age_seconds:
                    path.unlink()
                    logger.info("Deleted old file", extra={"path": str(path), "age_seconds": age})
    except Exception as e:
        logger.warning("Error during cleanup of old files: %s", str(e))

async def heartbeat_loop(redis_client: ResultStorage):
    """Периодически отмечает воркер как активный в Redis."""
    while True:
        try:
            await redis_client.redis.sadd("workers:active", WORKER_ID)
            await redis_client.redis.expire("workers:active", 60)
        except Exception as e:
            logger.warning("Heartbeat failed: %s", str(e))
        await asyncio.sleep(10)


async def main():
    logger.info("Starting worker")

    # Очистка старых файлов (старше 30 минут)
    cleanup_old_files(settings.UPLOAD_DIR, max_age_seconds=1800)

    # Попытка загрузить модель при запуске
    try:
        load_model()
        model_status.set(1)
        start_http_server(8001)
        logger.info("Metrics server started on port 8001")
    except ModelLoadError as e:
        model_status.set(0)
        logger.critical("Cannot start worker: %s", str(e))
        await asyncio.sleep(5)
        raise SystemExit(1)

    redis_client = ResultStorage(redis_url=settings.REDIS_URL)
    await redis_client.connect()

    # Запуск фоновой задачи heartbeat
    asyncio.create_task(heartbeat_loop(redis_client))

    # Обработчик сообщений
    async def handle_message(task_id: str, image_path: str, confidence_threshold: float):
        tasks_in_progress.inc()
        t_start = time.perf_counter()
        try:
            detections = predict_from_file(image_path, confidence_threshold)
            elapsed = time.perf_counter() - t_start
            inference_time.observe(elapsed)
            await redis_client.set_result(task_id, detections)
            logger.info("Task completed", extra={"task_id": task_id, "detections_count": len(detections)})
        except Exception as e:
            logger.error("Task failed", extra={"task_id": task_id, "error": str(e)})
            await redis_client.set_error(task_id, str(e))
        finally:
            tasks_in_progress.dec()
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
                    logger.debug("Removed processed image", extra={"image_path": image_path})
            except Exception as e:
                logger.warning("Could not remove image: %s", str(e))

    consumer_manager = KafkaConsumerManager(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        topic=settings.KAFKA_TOPIC_REQUESTS,
        group_id="detection-worker-group",
        message_handler=handle_message
    )

    await consumer_manager.start()
    try:
        await asyncio.Future()
    finally:
        try:
            await redis_client.redis.srem("workers:active", WORKER_ID)
        except Exception as e:
            logger.debug("Failed to remove worker from active set: %s", str(e))
        await consumer_manager.stop()
        await redis_client.close()

if __name__ == "__main__":
    asyncio.run(main())
