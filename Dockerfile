# Single-service deploy: React build served by FastAPI, results precomputed (no SQL Server needed at runtime).
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/lekha ./lekha
COPY backend/results ./results
COPY --from=web /web/dist ./static
ENV PORT=8000
CMD ["sh", "-c", "uvicorn lekha.api:app --host 0.0.0.0 --port ${PORT}"]
