FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# Security updates of the Debian base (Trivy, finding H-12).
RUN apt-get update \
    && apt-get -y upgrade \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# pip (and the libraries it vendors) is not needed at runtime: remove it after installing.
RUN pip install -r requirements.txt \
    && python -m pip uninstall -y pip

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN useradd --system --uid 10001 --no-create-home neurophobia \
    && chmod 0755 /usr/local/bin/entrypoint.sh
USER neurophobia

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
