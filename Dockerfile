FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BBREW_DATA_DIR=/data

WORKDIR /app

COPY requirements.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && apt-get clean \
    && pip install --no-cache-dir -r requirements.txt

COPY . .
COPY docker/entrypoint.sh /usr/local/bin/bbrew-entrypoint

RUN groupadd --system --gid 10001 bbrew \
    && useradd --system --uid 10001 --gid bbrew --home-dir /app --no-create-home bbrew \
    && chmod 755 /usr/local/bin/bbrew-entrypoint \
    && mkdir -p /data \
    && DJANGO_DEBUG=0 python manage.py collectstatic --noinput

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/accounts/login/', timeout=3)"

ENTRYPOINT ["/usr/local/bin/bbrew-entrypoint"]
CMD ["gunicorn", "bbrew.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
