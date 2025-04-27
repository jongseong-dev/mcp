# 🛠️ 1. 프로젝트 구조 확인
지금 코드는 이렇게 되어 있어:

```
프로젝트 루트/
├── app/
│   ├── main.py         # FastAPI 앱 엔트리포인트
│   ├── router.py       # API 라우터
│   ├── utils.py        # 유틸리티 (Claude 호출, Slack 전송 등)
│   ├── schemas.py      # 데이터 스키마
│   └── settings.py     # 환경 변수
├── requirements.txt
└── Dockerfile (있으면)
```

✅ `app/main.py` 가 FastAPI 서버의 진입점이야.

---

# 🛠️ 2. 로컬에서 실행하는 방법

**1) 가상환경 생성 및 활성화**

(uv를 쓴다면)
```bash
uv venv .venv --python=python3.13
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate    # Windows
```

**2) 필요한 패키지 설치**
```bash
uv pip install -r requirements.txt
```
(혹은 `pip install` 사용해도 돼)

**3) FastAPI 서버 실행**

터미널에서 프로젝트 루트로 가서:

```bash
uvicorn app.main:app --reload --port 5000
```

✅ 그러면 FastAPI 서버가 `http://localhost:5000` 에서 뜬다!

---

# 🛠️ 3. Docker로 실행하는 방법 (만약 Dockerfile 있을 때)

**1) Docker 빌드**
```bash
docker build -t mcp-server .
```

**2) Docker 실행**
```bash
docker run -d -p 5000:5000 --env-file .env mcp-server
```
> `.env` 파일에 `SLACK_TOKEN`, `CHANNEL_ID`, `CLAUDE_API_KEY` 같은 환경변수를 저장해두면 편해.

(또는 `docker-compose.yml` 있으면 `docker-compose up --build`로 바로 실행 가능)

---

# 🔥 정리
| 방법 | 명령어 |
|:---|:---|
| 로컬 실행 | `uvicorn app.main:app --reload --port 5000` |
| Docker 실행 | `docker build`, `docker run` |

---

# 📋 추가 주의사항
- `.env` 또는 환경변수 설정을 반드시 해야 해 (`SLACK_TOKEN`, `CLAUDE_API_KEY` 등)
- 실행 전에 `app` 폴더가 **패키지**로 인식되도록 루트에 `__init__.py`를 넣는 것도 좋은 습관이야 (필수는 아님)

---