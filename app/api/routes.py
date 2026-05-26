"""Эндпоинты FastAPI."""
import uuid
import logging
from pathlib import Path
from PIL import Image
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Request, Response
from app.core.config import settings
from app.api.schemas import TaskResponse, ResultResponse, DetectionResult
from app.services.result_storage import ResultStorage
from app.services.kafka_producer import KafkaProducerManager
from app.utils.image_helpers import save_upload_file
from app.api.dependencies import get_kafka_producer, get_redis_client

# Prometheus metrics
from prometheus_client import Counter, Histogram, generate_latest

logger = logging.getLogger(__name__)
router = APIRouter()

# Метрики Prometheus
PREDICTIONS_TOTAL = Counter('predictions_total', 'Total number of prediction requests')
PREDICTION_DURATION_SECONDS = Histogram('prediction_duration_seconds', 'Prediction request duration in seconds')
ERRORS_TOTAL = Counter('errors_total', 'Total number of errors')

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}

async def _has_workers(redis: ResultStorage) -> bool:
    """Проверяет, есть ли хотя бы один активный worker."""
    count = await redis.redis.scard("workers:active")
    return count > 0

@router.post("/detect", response_model=TaskResponse, status_code=202)
async def create_detection_task(
    file: UploadFile = File(..., description="Изображение дорожного знака"),
    confidence_threshold: float = Form(settings.DEFAULT_CONFIDENCE_THRESHOLD, ge=0.0, le=1.0),
    kafka_producer: KafkaProducerManager = Depends(get_kafka_producer),
    redis_client: ResultStorage = Depends(get_redis_client)
):
    """
    Загружает изображение, создаёт задачу на детекцию и ставит её в очередь Kafka.
    """
    # Валидация типа файла
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        # Увеличиваем счётчик ошибок
        ERRORS_TOTAL.inc()
        raise HTTPException(status_code=400, detail="Unsupported file type. Only JPEG and PNG allowed.")

    if file.size and file.size > settings.MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")
    # Проверка доступности worker'ов
    if not await _has_workers(redis_client):
        ERRORS_TOTAL.inc()
        raise HTTPException(status_code=503, detail="No available workers. Please try later.")

    # Сохранение файла
    content = await file.read()
    file_bytes = content
    task_id = str(uuid.uuid4())
    file_extension = Path(file.filename).suffix if file.filename else ".jpg"
    saved_path = await save_upload_file(file_bytes, file_extension, settings.UPLOAD_DIR, task_id)

    with Image.open(saved_path) as img:
        w, h = img.size
        if w < 1280 or h < 720 or w > 2268 or h > 4032:
            raise HTTPException(status_code=400, detail="Invalid image dimensions")

    # Установка статуса pending
    await redis_client.set_task_status(task_id, "pending")

    # Отправка в Kafka
    await kafka_producer.send_request(task_id, str(saved_path), confidence_threshold)
    logger.info("Task created", extra={"task_id": task_id, "image_path": str(saved_path)})
    
    # Увеличиваем счётчик предсказаний
    PREDICTIONS_TOTAL.inc()
    return TaskResponse(task_id=task_id, status_url=f"/result/{task_id}")


@router.get("/result/{task_id}", response_model=ResultResponse)
async def get_task_result(
    task_id: str,
    redis_client: ResultStorage = Depends(get_redis_client)
):
    """
    Возвращает статус и результат обработки задачи.
    """
    result_data = await redis_client.get_result(task_id)
    if result_data is None:
        # Увеличиваем счётчик ошибок
        ERRORS_TOTAL.inc()
        raise HTTPException(status_code=404, detail="Task not found")

    task_id = result_data["task_id"]
    status = result_data["status"]
    detections_list = result_data.get("detections")
    error_msg = result_data.get("error_message")

    # Приведение детекций к схеме, если есть
    detections = None
    if detections_list:
        detections = [DetectionResult(**d) for d in detections_list]

    return ResultResponse(
        task_id=task_id,
        status=status,
        detections=detections,
        error_message=error_msg
    )


@router.get("/metrics")
async def metrics():
    """
    Эндпоинт для Prometheus метрик.
    """
    return Response(content=generate_latest().decode('utf-8'), media_type='text/plain')


@router.get("/health")
async def health():
    """Liveness probe: проверяет, жив ли процесс."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request):
    """
    Проверка готовности сервиса.
    """
    try:
        # Получаем клиенты из состояния приложения через request
        redis_client = request.app.state.redis_client
        if not redis_client.is_connected:
            return {"status": "error", "details": {"redis": "disconnected"}}

        kafka_producer = request.app.state.kafka_producer
        if not kafka_producer.is_connected():
            return {"status": "error", "details": {"kafka": "disconnected"}}

        # Проверяем, загружена ли модель
        # Предполагаем, что модель загружается в worker, и мы можем проверить это через состояние
        # В реальности это может быть более сложная проверка
        
        # Пока просто возвращаем ok, так как у нас нет прямого доступа к состоянию модели
        # В реальном приложении здесь должна быть проверка состояния модели

        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Readiness check failed: {str(e)}")