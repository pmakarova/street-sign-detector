"""
Точка входа для FastAPI приложения.
Инициализирует приложение, lifespan для Kafka продюсера и запускает uvicorn.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.api.routes import router
from app.services.kafka_producer import KafkaProducerManager
from app.services.result_storage import ResultStorage
from prometheus_fastapi_instrumentator import Instrumentator

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: инициализация продюсера Kafka и Redis клиента
    logger.info("Starting up API")
    kafka_producer = KafkaProducerManager(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS, topic=settings.KAFKA_TOPIC_REQUESTS)
    await kafka_producer.start()
    redis_client = ResultStorage(redis_url=settings.REDIS_URL)
    await redis_client.connect()

    # Сохраняем в app.state для использования в зависимостях
    app.state.kafka_producer = kafka_producer
    app.state.redis_client = redis_client
    yield
    # Shutdown
    logger.info("Shutting down API")
    await kafka_producer.stop()
    await redis_client.close()

app = FastAPI(title="Street Sign Detector API", version="0.1.0", lifespan=lifespan)

# Инструментируем приложение – метрики будут доступны на /metrics
Instrumentator().instrument(app).expose(app)

app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)