import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 경로 설정
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

# .env 파일 로드
load_dotenv(dotenv_path=ENV_PATH)

STORAGE_DIR = BASE_DIR / "storage"

# 환경변수 읽기
SLACK_TOKEN = os.getenv("SLACK_BOT_TOKEN")
CHANNEL_ID: str = str(os.getenv("CHANNEL_ID"))
RESULT_CHANNEL_ID: str = str(os.getenv("RESULT_CHANNEL_ID"))
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-3-opus-20240229"
