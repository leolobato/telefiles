FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY telefiles ./telefiles
RUN pip install --no-cache-dir .

# config.yaml and .env are provided at runtime via mounts/env
ENV DATA_DIR=/data
VOLUME ["/data"]

CMD ["python", "-m", "telefiles"]
