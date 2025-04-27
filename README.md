좋아, 요청 아주 명확해!

---

# 📦 프로젝트 구조
```
/
├── app/
│   ├── main.py
│   ├── router.py
│   ├── utils.py
│   ├── settings.py
│   └── schemas.py
├── templates/
│   ├── base.html
│   ├── mcp.html
│   ├── result.html
├── storage/
│   └── session.json
├── .env
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── README.md
```


---

## 📦 설치 방법

### 1. 프로젝트 클론

```bash
git clone https://github.com/your-repo/mcp-slack-claude.git
cd mcp-slack-claude
```

### 2. Python 가상환경 생성

(uv 사용을 추천합니다)

```bash
uv venv
```

또는 일반 venv:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 패키지 설치

```bash
uv pip install -r requirements.txt
```

또는

```bash
pip install -r requirements.txt
```

### 4. 환경 변수(.env) 파일 생성

루트에 `.env` 파일을 만들어 다음 내용을 입력하세요.

```dotenv
SLACK_BOT_TOKEN=xoxb-XXXXXXXXXXXXXXXX
CLAUDE_API_KEY=sk-ant-XXXXXXXXXXXXXXXX
# 기본값, UI 에서 설정 가능
CHANNEL_ID=CXXXXXXXX
# 기본값, UI 에서 설정 가능
RESULT_CHANNEL_ID=CXXXXXXXX

```

✅ 이 `.env` 파일은 서버 실행 시 자동으로 로드됩니다.

---

## 🚀 프로젝트 실행 방법

### 방법 1. Makefile로 로컬 개발 서버 실행

로컬에서 개발용으로 실행할 때:

```bash
make dev
```

- FastAPI 서버가 `http://localhost:8000/` 에서 실행됩니다.
- 소스 코드 변경 시 자동으로 리로드됩니다 (hot-reload).

**필요사항:**  
- Python 3.10+
- uvicorn
- uv 또는 venv

---

### 방법 2. Docker + Docker Compose로 실행

프로덕션 배포 또는 일관된 환경이 필요할 때:

1. Docker 설치 (필수)  
2. Docker Compose 설치 (또는 docker compose 지원되는 버전)

3. 실행

```bash
docker-compose up --build
```

- Docker 이미지가 자동으로 빌드되고 컨테이너가 실행됩니다.
- 서버는 `http://localhost:8000/` 에서 동일하게 접근할 수 있습니다.

**필요사항:**  
- Docker
- Docker Compose
