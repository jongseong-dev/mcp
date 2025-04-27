# --- Base Image ---
FROM python:3.10-slim

# --- Working Directory 설정 ---
WORKDIR /app

# --- 필요한 시스템 패키지 설치 ---
RUN apt-get update && apt-get install -y gcc

# --- 프로젝트 코드 복사 ---
COPY . /app

# --- python-dotenv, uvicorn, fastapi 등 설치 ---
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# --- 환경변수 로드를 위해 .env 파일도 복사 필요 ---
# (로컬 개발용이니 docker-compose로 env파일 지정하는 게 더 좋긴 해)

# --- 기본 실행 명령어 ---
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
