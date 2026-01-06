# ===========================================
# Dockerfile для Railway
# ===========================================

FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY bot.py .
COPY config.py .

# Создаем директорию для БД
RUN mkdir -p /tmp

# Запускаем бота
CMD ["python", "bot.py"]
