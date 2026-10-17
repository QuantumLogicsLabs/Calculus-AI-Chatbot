FROM node:22-bookworm-slim AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --legacy-peer-deps --no-audit --no-fund
COPY frontend/public ./public
COPY frontend/src ./src
ENV CI=true REACT_APP_API_URL="" REACT_APP_CHAT_URL=""
RUN npm run build

FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PORT=10000 FRONTEND_BUILD_DIR=/app/frontend/build CALCVOYAGER_PREVIEW=True
COPY backend/requirements.txt /tmp/backend-requirements.txt
COPY aiService/requirements.txt /tmp/ai-requirements.txt
RUN pip install --no-cache-dir -r /tmp/backend-requirements.txt -r /tmp/ai-requirements.txt
COPY backend ./backend
COPY aiService ./aiService
COPY scripts ./scripts
COPY --from=frontend /web/build ./frontend/build
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 10000
CMD ["python", "-m", "scripts.serve_render"]
