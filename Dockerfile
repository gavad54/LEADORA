FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LEADORA_ENV=production
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN mkdir -p /app/data /data && useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
EXPOSE 8000
# Persistent hosting disks may be mounted root-owned. Fix the mounted path before
# dropping privileges so SQLite can create/update its database safely.
CMD ["sh", "-c", "chown appuser:appuser /data && if [ -f /data/leadora.db ]; then chown appuser:appuser /data/leadora.db; fi && exec gosu appuser uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
