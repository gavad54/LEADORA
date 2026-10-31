FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LEADORA_ENV=production LEADORA_DB=/data/leadora.db LEADORA_BACKUP_DIR=/data/backups
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh && mkdir -p /app/data /data /data/backups /control-data && useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app /control-data
EXPOSE 8000
CMD ["sh", "/entrypoint.sh"]
