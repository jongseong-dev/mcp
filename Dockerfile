# Dockerfile

FROM python:3.11-slim

WORKDIR /app

# uv 설치
RUN apt-get update && apt-get install -y curl && \
    curl -LsSf https://astral.sh/uv/install.sh | sh

COPY requirements.txt ./
RUN uv pip install --no-cache-dir -r requirements.txt

COPY app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]
