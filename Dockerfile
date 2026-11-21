# The website and its API in one image: build the React site, then serve it with FastAPI.
#   docker build -t delhi-pm25 .
#   docker run --rm -p 8000:8000 delhi-pm25      # then open http://localhost:8000
# Hosting platforms pass the port in $PORT; locally it defaults to 8000.

FROM node:24-slim AS site
WORKDIR /site
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt
COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir --no-deps .
COPY config/stations.csv config/stations.csv
COPY serving/ serving/
COPY --from=site /site/dist frontend/dist
ENV REPLAY_PARQUET=/app/serving/replay_2025.parquet \
    STATIONS_CSV=/app/config/stations.csv \
    FRONTEND_DIST=/app/frontend/dist
RUN useradd --create-home app
USER app
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn delhi_pm25.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
