// Конфигурация
const API_BASE_URL = ''; 
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB

// Состояние приложения
let state = {
    selectedFile: null,
    imageObj: null, 
    taskId: null,
    pollIntervalId: null,
    lastDetections: []
};

// DOM Элементы
const elements = {
    uploadSection: document.getElementById('upload-section'),
    previewSection: document.getElementById('preview-section'),
    statusSection: document.getElementById('status-section'),
    resultsSection: document.getElementById('results-section'),
    dropZone: document.getElementById('drop-zone'),
    fileInput: document.getElementById('file-input'),
    canvas: document.getElementById('image-canvas'),
    confidenceSlider: document.getElementById('confidence-slider'),
    confidenceValue: document.getElementById('confidence-value'),
    btnClear: document.getElementById('btn-clear'),
    btnDetect: document.getElementById('btn-detect'),
    statusText: document.getElementById('status-text'),
    detectionsCount: document.getElementById('detections-count'),
    detectionsList: document.getElementById('detections-list'),
    btnExportJson: document.getElementById('btn-export-json'),
    btnExportCsv: document.getElementById('btn-export-csv'),
    toastContainer: document.getElementById('toast-container')
};

// Контекст Canvas
const ctx = elements.canvas.getContext('2d');

//Инициализация и слушатели событий
function init() {
    // Проверка доступности API
    checkApiHealth();

    elements.dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        elements.dropZone.classList.add('dragover');
    });

    elements.dropZone.addEventListener('dragleave', () => {
        elements.dropZone.classList.remove('dragover');
    });

    elements.dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        elements.dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    // Клик по drop-zone для выбора файла
    elements.dropZone.addEventListener('click', () => elements.fileInput.click());
    
    // Выбор файла
    elements.fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleFileSelect(e.target.files[0]);
        }
    });

    // Изменение ползунка уверенности
    elements.confidenceSlider.addEventListener('input', (e) => {
        elements.confidenceValue.textContent = parseFloat(e.target.value).toFixed(2);
    });

    // Кнопки управления
    elements.btnClear.addEventListener('click', resetApp);
    elements.btnDetect.addEventListener('click', startDetection);

    // Кнопки экспорта
    elements.btnExportJson.addEventListener('click', exportJSON);
    elements.btnExportCsv.addEventListener('click', exportCSV);
}

function handleFileSelect(file) {
    // Валидация
    if (!file.type.match('image/jpeg') && !file.type.match('image/png')) {
        showToast('Пожалуйста, выберите изображение JPEG или PNG.', 'error');
        return;
    }
    if (file.size > MAX_FILE_SIZE) {
        showToast('Размер файла превышает 10 МБ.', 'error');
        return;
    }

    state.selectedFile = file;
    
    // Загрузка в Image объект для Canvas
    const reader = new FileReader();
    reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
            state.imageObj = img;
            drawOriginalImage();
            
            // Смена UI
            elements.uploadSection.classList.add('hidden');
            elements.previewSection.classList.remove('hidden');
            elements.resultsSection.classList.add('hidden');
            state.lastDetections = [];
        };
        img.src = e.target.result;
    };
    reader.readAsDataURL(file);
}

function drawOriginalImage() {
    if (!state.imageObj) return;
    
    // Устанавливаем реальные размеры холста (для точных координат)
    elements.canvas.width = state.imageObj.width;
    elements.canvas.height = state.imageObj.height;
    
    // Отрисовываем
    ctx.clearRect(0, 0, elements.canvas.width, elements.canvas.height);
    ctx.drawImage(state.imageObj, 0, 0);
}

// Взаимодействие с API 

async function checkApiHealth() {
    try {
        await fetch(`${API_BASE_URL}/health`);
    } catch (e) {
        showToast('Бэкенд недоступен. Проверьте подключение.', 'error');
    }
}

async function startDetection() {
    if (!state.selectedFile) return;

    const threshold = parseFloat(elements.confidenceSlider.value);
    
    // UI подготовки
    elements.btnDetect.disabled = true;
    elements.btnClear.disabled = true;
    elements.statusSection.classList.remove('hidden');
    elements.resultsSection.classList.add('hidden');
    elements.statusText.textContent = 'Отправка изображения...';
    
    drawOriginalImage(); 

    const formData = new FormData();
    formData.append('file', state.selectedFile);
    formData.append('confidence_threshold', threshold);

    try {
        const response = await fetch(`${API_BASE_URL}/detect`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'Ошибка отправки задачи');
        }

        const data = await response.json();
        state.taskId = data.task_id;
        
        // Запуск поллинга
        elements.statusText.textContent = 'Обработка моделью ИИ...';
        state.pollIntervalId = setInterval(pollResult, 1500);

    } catch (error) {
        handleError('Ошибка запуска распознавания: ' + error.message);
    }
}

async function pollResult() {
    if (!state.taskId) return;

    try {
        const response = await fetch(`${API_BASE_URL}/result/${state.taskId}`);
        
        if (!response.ok) {
            if (response.status === 404) throw new Error('Задача не найдена на сервере');
            throw new Error(`Ошибка HTTP: ${response.status}`);
        }

        const data = await response.json();

        if (data.status === 'completed') {
            stopPolling();
            handleSuccess(data.detections);
        } else if (data.status === 'failed') {
            stopPolling();
            handleError('Ошибка обработки: ' + (data.error_message || 'Неизвестная ошибка'));
        }

    } catch (error) {
        stopPolling();
        handleError('Сбой при получении результата: ' + error.message);
    }
}

function stopPolling() {
    if (state.pollIntervalId) {
        clearInterval(state.pollIntervalId);
        state.pollIntervalId = null;
    }
    elements.statusSection.classList.add('hidden');
    elements.btnDetect.disabled = false;
    elements.btnClear.disabled = false;
}

// Вспомогательная функция для вычисления пересечения рамок (IoU)
function calculateIoU(box1, box2) {
    const [x1, y1, w1, h1] = box1;
    const [x2, y2, w2, h2] = box2;

    const x_overlap = Math.max(0, Math.min(x1 + w1, x2 + w2) - Math.max(x1, x2));
    const y_overlap = Math.max(0, Math.min(y1 + h1, y2 + h2) - Math.max(y1, y2));
    const overlap_area = x_overlap * y_overlap;

    const area1 = w1 * h1;
    const area2 = w2 * h2;
    const union_area = area1 + area2 - overlap_area;

    return overlap_area / union_area;
}

// Функция для удаления дубликатов
function filterDuplicates(detections, threshold = 0.5) {
    const sorted = [...detections].sort((a, b) => b.confidence - a.confidence);
    const result = [];

    while (sorted.length > 0) {
        const best = sorted.shift();
        result.push(best);

        for (let i = 0; i < sorted.length; i++) {
            if (calculateIoU(best.bbox, sorted[i].bbox) > threshold) {
                sorted.splice(i, 1);
                i--;
            }
        }
    }
    return result;
}


function handleSuccess(detections) {
    // Убираем дубликаты по координатам
    let filtered = filterDuplicates(detections || [], 0.5);

    state.lastDetections = filtered;
    elements.resultsSection.classList.remove('hidden');
    elements.detectionsCount.textContent = filtered.length;
    
    renderDetectionsList(filtered);
    drawBoundingBoxes(filtered);
    showToast(`Готово! Найдено объектов: ${filtered.length}`);
}

function renderDetectionsList(detections) {
    elements.detectionsList.innerHTML = '';
    
    if (detections.length === 0) {
        elements.detectionsList.innerHTML = '<div class="detection-item">Знаки не найдены</div>';
        return;
    }

    detections.forEach(d => {
        const confPercent = (d.confidence * 100).toFixed(1);
        const item = document.createElement('div');
        item.className = 'detection-item';
        item.innerHTML = `
            <span class="detection-class">${escapeHTML(d.class_name)}</span>
            <span class="detection-conf">${confPercent}%</span>
        `;
        elements.detectionsList.appendChild(item);
    });
}

function drawBoundingBoxes(detections) {
    if (!state.imageObj) return;

    const canvasWidth = elements.canvas.width;
    const strokeWidth = Math.max(3, canvasWidth / 400); 
    const fontSize = Math.max(16, canvasWidth / 100);

    ctx.font = `600 ${fontSize}px Inter, sans-serif`;
    ctx.textBaseline = 'top';

    detections.forEach(d => {
        const [x, y, w, h] = d.bbox;
        
        const shortName = d.class_name.split(' - ')[0];
        
        const text = `${shortName} ${(d.confidence * 100).toFixed(0)}%`;
        
        ctx.strokeStyle = '#ef4444';
        ctx.lineWidth = strokeWidth;
        ctx.strokeRect(x, y, w, h);

        const textMetrics = ctx.measureText(text);
        const textWidth = textMetrics.width;
        const textHeight = fontSize * 1.2;
        const padding = strokeWidth * 2;

        let labelY = y - textHeight - padding;
        if (labelY < 0) labelY = y + strokeWidth;

        ctx.fillStyle = '#ef4444'; 
        ctx.fillRect(x - strokeWidth/2, labelY, textWidth + padding * 2, textHeight + padding);

        ctx.fillStyle = '#ffffff';
        ctx.fillText(text, x + padding - strokeWidth/2, labelY + padding/2);
    });
}

// Экспорт данных

function exportJSON() {
    if (!state.lastDetections.length) return showToast('Нет данных для экспорта', 'error');
    
    const dataStr = JSON.stringify(state.lastDetections, null, 2);
    downloadFile(dataStr, 'detections.json', 'application/json');
}

function exportCSV() {
    if (!state.lastDetections.length) return showToast('Нет данных для экспорта', 'error');
    
    // Заголовки
    let csvContent = 'class_name,x,y,width,height,confidence\n';
    
    // Строки
    state.lastDetections.forEach(d => {
        const safeClassName = `"${d.class_name.replace(/"/g, '""')}"`;
        const row = [
            safeClassName,
            d.bbox[0], d.bbox[1], d.bbox[2], d.bbox[3],
            d.confidence.toFixed(4)
        ].join(',');
        csvContent += row + '\n';
    });

    downloadFile(csvContent, 'detections.csv', 'text/csv;charset=utf-8;');
}

function downloadFile(content, fileName, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

// Утилиты

function resetApp() {
    stopPolling();
    state.selectedFile = null;
    state.imageObj = null;
    state.taskId = null;
    state.lastDetections = [];
    
    elements.fileInput.value = '';
    
    elements.uploadSection.classList.remove('hidden');
    elements.previewSection.classList.add('hidden');
    elements.resultsSection.classList.add('hidden');
    elements.statusSection.classList.add('hidden');
}

function handleError(msg) {
    stopPolling();
    showToast(msg, 'error');
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    
    elements.toastContainer.appendChild(toast);
    
    // Анимация появления
    requestAnimationFrame(() => {
        toast.classList.add('show');
    });

    // Удаление через 3 секунды
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300); 
    }, 3000);
}

function escapeHTML(str) {
    return str.replace(/[&<>'"]/g, 
        tag => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            "'": '&#39;',
            '"': '&quot;'
        }[tag])
    );
}

init();