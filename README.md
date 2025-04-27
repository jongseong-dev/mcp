# Claude-Slack Bridge

샌드박스 환경에서 안전하게 실행되는 Claude-Slack Bridge 애플리케이션입니다. FastAPI를 통해 Claude API에 질문을 보내고 응답을 Slack 채널로 전송합니다. 추가로 Slack 채널의
메시지를 읽어 컨텍스트로 사용할 수 있습니다.

## 주요 기능

- Claude API를 통한 질문 및 응답
- Slack 채널로 응답 자동 전송
- Slack 채널 메시지를 컨텍스트로 사용 가능
- 웹 UI를 통한 쉬운 사용
- 샌드박스 환경에서 안전하게 실행 (외부 노출 방지)

## 시작하기

### 준비 사항

- Python 3.8 이상
- Anthropic API 키
- Slack 봇 토큰 (적절한 권한 필요)

### 환경 설정

1. 저장소 클론 또는 코드 다운로드

```bash
git clone https://github.com/yourusername/claude-slack-bridge.git
cd claude-slack-bridge
```

2. 가상 환경 설정 (선택 사항)

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. 필요한 패키지 설치

```bash
pip install -r requirements.txt
```

4. `.env` 파일 생성 및 API 키 설정

```
ANTHROPIC_API_KEY=your-anthropic-api-key
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
LOCAL_API_KEY=your-local-api-key-for-security
DEFAULT_SLACK_CHANNEL=#general
```

### 실행 방법

1. 서버 실행

```bash
uvicorn claude_slack_bridge:app --reload --host 127.0.0.1 --port 8000
```

2. 웹 브라우저에서 접속: http://127.0.0.1:8000/

## 사용 방법

### 웹 UI 사용하기

웹 UI는 다음 탭으로 구성되어 있습니다:

1. **간단한 질문**: 기본 옵션으로 Claude에게 빠르게 질문
2. **고급 질문**: 모델, 토큰 제한, 온도 등의 파라미터 조정
3. **대화 메시지**: 대화 컨텍스트가 있는 메시지 전송
4. **Slack 컨텍스트**: Slack 채널 메시지를 컨텍스트로 사용

### Slack 컨텍스트로 질문하기

1. "Slack 컨텍스트" 탭 선택
2. 소스 Slack 채널 ID 입력
3. 가져올 메시지 수 지정
4. 질문 입력
5. 결과를 받을 Slack 채널 지정
6. "질문하기" 버튼 클릭

### API 직접 사용하기

curl이나 다른 API 클라이언트를 사용하여 API를 직접 호출할 수 있습니다:

```bash
curl -X POST "http://127.0.0.1:8000/ask" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-local-api-key" \
  -d '{
    "question": "What is the meaning of life?",
    "slack_channel": "#general",
    "model": "claude-3-7-sonnet-20250219"
  }'
```

## 보안 고려사항

- 이 서버는 **로컬 네트워크에서만** 접근 가능하도록 설계되었습니다
- 모든 API 엔드포인트는 API 키 인증이 필요합니다
- Slack 채널 메시지는 필요할 때만 메모리에 로드되고 영구 저장되지 않습니다
- Docker를 사용하여 샌드박스 환경에서 실행할 수 있습니다

## Docker로 실행하기

```bash
# Docker 이미지 빌드
docker-compose build

# 컨테이너 실행
docker-compose up -d
```

## 폴더 구조

```
claude-slack-bridge/
├── .env                      # 환경 변수 파일
├── claude_slack_bridge.py    # 메인 서버 코드
├── slack_formatter.py        # Slack 메시지 포맷 유틸리티
├── requirements.txt          # 필요한 패키지 목록
├── Dockerfile                # Docker 설정
├── docker-compose.yml        # Docker Compose 설정
├── static/                   # 정적 파일 디렉토리
└── templates/
    └── index.html            # 웹 UI 템플릿
```

## Slack 봇 설정

1. [Slack API 웹사이트](https://api.slack.com/apps)에서 새 앱 생성
2. 다음 OAuth 스코프 추가:
    - `channels:history`
    - `channels:read`
    - `chat:write`
    - `users:read`
3. 앱을 워크스페이스에 설치
4. 봇 토큰을 `.env` 파일에 추가

## 문제 해결

- **서버 시작 실패**: 포트 충돌 여부 확인, 다른 포트로 시도
- **Slack API 오류**: 봇 토큰 권한 확인, 필요한 스코프 추가
- **Claude API 오류**: API 키 및 할당량 확인
- **응답 지연**: 대량의 메시지나 긴 컨텍스트 처리 시 시간이 더 걸릴 수 있음

## 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.