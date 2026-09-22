FROM node:22-bookworm-slim AS assets
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY frontend/ ./frontend/
COPY scripts/ ./scripts/
COPY tailwind.config.cjs ./
RUN npm run build && npm prune --omit=dev

FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY --from=assets /usr/local/bin/node /usr/local/bin/node
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home appuser
COPY --from=assets /app/node_modules ./node_modules
COPY --from=assets /app/dist ./dist
COPY backend/ ./backend/
COPY pipeline.py ./
USER appuser
CMD ["python", "-m", "backend.run"]
