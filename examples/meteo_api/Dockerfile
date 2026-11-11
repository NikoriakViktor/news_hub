# Один образ для API і для Streamlit — різні лише команди запуску (docker-compose.yml).
# Docker докладно — урок 48; тут — щоб було видно, як частини системи з'єднані.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY meteo_api ./meteo_api
COPY weather_map ./weather_map
ENV PYTHONUNBUFFERED=1
