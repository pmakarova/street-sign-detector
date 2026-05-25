from prometheus_client import Histogram, Gauge

inference_time = Histogram(
    'detection_inference_seconds',
    'Time spent on model inference per image',
    buckets=(0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 2.0, float('inf'))
)

model_status = Gauge(
    'model_loaded',
    'Whether the model is currently loaded (1) or not (0)'
)

tasks_in_progress = Gauge(
    'worker_tasks_in_progress',
    'Number of detection tasks currently being processed'
)