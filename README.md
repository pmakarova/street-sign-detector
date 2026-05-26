# Stret Sign Detection (RTSD)

Веб-приложение для обнаружения дорожных знаков на изображениях.  
Использует YOLO-модель, FastAPI-бэкенд, Kafka и Redis.

## Команда

* **ML-разработчик** — Бадашкеев Андрей
* **Backend-разработчик** — Емельянов Александр
* **Frontend-разработчик** — Макарова Полина
* **DevOps** — Копац Алексей

## Структура проекта

```
street-sign-detector/
├── app/                          # Backend-приложение (FastAPI + Worker)
│   ├── main.py                   # точка входа API (uvicorn)
│   ├── worker.py                 # точка входа воркера (Kafka consumer)
│   ├── api/                      # эндпоинты, Pydantic-схемы, зависимости
│   ├── core/                     # конфигурация, логирование, исключения
│   ├── services/                 # работа с Kafka, Redis, управление задачами
│   └── utils/                    # вспомогательные утилиты (сохранение файлов)
├── ml/                           # Изолированная ML-часть
│   ├── model.py                  # загрузка YOLO-модели
│   ├── predict.py                # функция инференса predict_from_file()
│   ├── utils.py                  # вспомогательные ML-функции
│   └── models/                   # каталог для файлов весов (Git LFS)
│       └── model_weights.pt      # обученная модель (добавляется отдельно)
├── frontend/                     # Frontend-часть приложения
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
├── data/                         # Общее хранилище (shared volume)
│   └── uploads/                  # временные загруженные изображения
├── Dockerfile.api                # образ FastAPI
├── Dockerfile.worker             # образ воркера
├── Dockerfile.worker-gpu         # образ воркера с поддержкой GPU
├── Dockerfile.frontend           # Nginx
├── docker-compose.yml            # локальный запуск всех сервисов
├── prometheus.yml                # сбор метрик
├── .env.example                  # образец переменных окружения
├── requirements.txt              # Python-зависимости
├── start_linux.sh                # Файл запуска из Linux Bash
├── start_windows.ps1             # Файл запуска из Windows PowerShell
└── README.md
```

## Быстрый старт

### 1. Подготовка локального репозитория для работы
1. Необходимо создать форк репозитория у себя в GitHub (нажать Fork)
Форк - это точная копия основного репозитория на вашем аккаунте GitHub. Но в процессе Вы можете изменять его независимо от родительского репозитория. Для комфортной работы рекомендуется поддерживать форк идентичным основе (делать регулярный git push origin)
2. Склонировать себе репозиторий на локальную машину. Так как после создания форка он идентичен основному репозиторию, клонировать можно любой из них.
```bash
git lfs install          # если ещё не установлен Git LFS
git clone https://github.com/Timeyan/street-sign-detector
cd street-sign-detector
git lfs pull             # загрузить файлы моделей, когда они появятся
```
3. Задать связи локального репозитория с основным и с форком.
```bash
git remote add upstream git@github.com:Timeyan/street-sign-detector.git
git remote add origin git@github.com:<user_name>/street-sign-detector.git
```
Origin – связь с форком. Через origin Вы будете заливать свои изменения на GitHub.
Upstream – связь с main-репозиторием. Push в него делать запрещено, можно только забирать из него свежие апдейты. Перед внедрением изменений необходимо обязательно актуализировать репозиторий через pull upstream.

Посмотреть текущие связи можно командой 
```bash
git remote -v
```
#### Пример добавления своих изменений (полный цикл)

```bash
git status                       # Мы сейчас в main и убеждаемся в этом
git pull upstream main           # Актуализируем изменения из main основного репозитория
git push origin main             # Добавляем изменения в свой форк, чтобы он совпадал с upstream
git checkout -b <название_ветки> # Создание новой ветки для фичи и переход в нее

# Тут происходит магия написания кода

git add .                        # Добавление измененных файлов для дальнейшего коммита
git commit -m "<message>"        # Коммит (фиксация) изменений в локальном репозитории
git push origin <название_ветки> # Отправка изменений в форк
# Лучше добавлять изменения в аналогичную ветку в форке и не коммитить в main
# Тогда репозитоий будет всегда чистым (без лишних веток)

# Здесь происходит pull request и pull ваших изменений в upstream

git checkout main                # Возвращаемся в main
git pull upstream main           # Забираем свои изменения из upstream в локальный репозиторий 
                                 # (они же изначально были в рабочей ветке, а нужны в main, да-да)
git push origin main             # ну и актуализируем наш origin (форк)

```

### 2. Переменные окружения
Создайте .env из примера:
```bash
cp .env.example .env
```
В .env по необходимости можно добавлять/удалять переменные окружения. Они остаются у Вас локально. Все пароли и секреты добавляются сюда.

### 3. Зависимости для ML/Backend
```bash
pip install -r requirements.txt
```
Для разработки (тесты, линтеры) дополнительно:
```bash
pip install -r requirements-dev.txt
```
requirements-dev.txt используется ТОЛЬКО для разработки. Для прода нужен чистый (без библиотечного мусора) requirements.txt.

### 3. Запуск ПО
**Автоматический запуск (выбирает CPU или GPU в зависимости от конфигурациии машины)**
* Linux/macOS/WSL: `bash start.sh`
* Windows PowerShell: `.\start.ps1`
**Запуск вручную**

Первый запуск (сборка + 2 воркера)
```bash
docker compose up --build --scale worker=2
```
Будут загружены образы Kafka и Redis, собраны образы API и worker’ов.

Последующие запуски (без пересборки)
```bash
docker compose up --scale worker=2
```
Запуск с одним воркером
```bash
docker compose up --scale worker=1
```

Остановка
```bash
docker compose down
```
Запуск без Docker (только для разработки)
```bash
uvicorn app.main:app --reload
```

После запуска:
* 🖼️ **Фронтенд**: http://localhost
* 📘 **Swagger UI**: http://localhost:8000/docs
* 📊 **Prometheus**: http://localhost:9090
* 📈 **Grafana**: http://localhost:3000 (admin / admin)
* ♨️ **Kafka**: http://localhost:9092
* 💾 **Redis**: http://localhost:6379

### Локальный запуск без Docker (для отладки)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload        # API
python -m app.worker                  # Worker (нужны Kafka и Redis)
```

### Тестирование

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
mypy .
```

## ПОЛЬЗОВАТЕЛЬСКОЕ ИСПОЛЬЗОВАНИЕ

1. Откройте http://localhost
2. Перетащите изображение или выберите файл (JPEG/PNG, до 10 МБ)
3. Настройте порог уверенности (слайдер)
4. Нажмите «Распознать»
5. Просмотрите результат (рамки и названия знаков)
6. Сохраните в JSON или CSV

## Мониторинг

* **Prometheus**: http://localhost:9090
* **Grafana**: http://localhost:3000 (admin / admin)

Метрики:
* `detection_inference_seconds` — гистограмма времени инференса
* `model_loaded` — статус загрузки модели (1/0)
* `worker_tasks_in_progress` — количество активных задач
* `predictions_total`, `prediction_duration_seconds` — HTTP-метрики API

---

*Для вопросов по настройке окружения обращайтесь к @timeyann*