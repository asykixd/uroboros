FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UROBOROS_DATA=/data \
    UROBOROS_DOCKER=1

COPY pyproject.toml README.md LICENSE ./
COPY uroboros ./uroboros
RUN pip install --no-cache-dir .

VOLUME /data
# First-login web panel: listens on all addresses inside the container; see docker-compose.yml for outside.
EXPOSE 8080
CMD ["python", "-m", "uroboros", "--host", "0.0.0.0"]
