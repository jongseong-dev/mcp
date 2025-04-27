"""
Claude-Slack Bridge
------------------
FastAPI를 통해 Claude API에 질문을 하고 응답을 Slack 채널로 전송하는 서버입니다.
샌드박스 환경에서 안전하게 동작하며 외부 유출을 방지합니다.
"""

import os

import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
import secrets
from pathlib import Path

from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    Request,
    status,
    BackgroundTasks,
    Security,
    Form,
    Body,
)
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel, Field
from dotenv import load_dotenv

import anthropic
import uvicorn
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from fastapi.templating import Jinja2Templates

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("claude_slack_bridge.log"), logging.StreamHandler()],
)
logger = logging.getLogger("claude-slack-bridge")

# 환경 변수 로드
load_dotenv()

# 환경 설정
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
DEFAULT_SLACK_CHANNEL = os.getenv("DEFAULT_SLACK_CHANNEL")

if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY 환경 변수가 설정되지 않았습니다.")
if not SLACK_BOT_TOKEN:
    raise ValueError("SLACK_BOT_TOKEN 환경 변수가 설정되지 않았습니다.")

# 보안 키 생성 (서버 시작 시마다 새로 생성)
LOCAL_API_KEY = os.getenv("LOCAL_API_KEY", secrets.token_hex(32))
logger.info(f"생성된 로컬 API 키: {LOCAL_API_KEY}")

# 디렉토리 설정
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# 디렉토리 생성
TEMPLATES_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

# 템플릿 파일 확인
TEMPLATE_FILE = TEMPLATES_DIR / "web.html"
if not TEMPLATE_FILE.exists():
    logger.warning(f"템플릿 파일이 없습니다: {TEMPLATE_FILE}")
    logger.info("web.html 템플릿 파일을 생성해주세요.")

# API 키 검증 의존성
api_key_header = APIKeyHeader(name="X-API-Key")


def validate_api_key(api_key: str = Security(api_key_header)):
    if api_key != LOCAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 API 키"
        )
    return api_key


# Pydantic 모델
class QuestionRequest(BaseModel):
    question: str
    slack_channel: Optional[str] = None
    thread_ts: Optional[str] = None
    model: str = "claude-3-7-sonnet-20250219"
    max_tokens: int = 4096
    temperature: float = 0.7
    system: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MessageRequest(BaseModel):
    messages: List[Dict[str, str]]
    slack_channel: Optional[str] = None
    thread_ts: Optional[str] = None
    model: str = "claude-3-7-sonnet-20250219"
    max_tokens: int = 4096
    temperature: float = 0.7
    system: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SlackMessage(BaseModel):
    channel: str
    text: str
    thread_ts: Optional[str] = None
    blocks: Optional[List[Any]] = None


# 클라이언트 초기화
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
slack_client = WebClient(token=SLACK_BOT_TOKEN)

# FastAPI 앱 초기화
app = FastAPI(title="Claude-Slack Bridge", docs_url="/docs", redoc_url="/redoc")

# Jinja2 템플릿 설정
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# 정적 파일 마운트
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# CORS 미들웨어 추가 (로컬 환경만 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 요청 로깅 미들웨어
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    logger.info(f"요청 시작 - ID: {request_id} - 경로: {request.url.path}")

    # 클라이언트 IP 확인 (로컬 네트워크만 허용)
    client_host = request.client.host
    if client_host not in ["127.0.0.1", "localhost", "::1"]:
        logger.warning(f"비인가 접근 시도: {client_host}")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "이 서버는 로컬 접근만 허용합니다"},
        )

    response = await call_next(request)
    logger.info(f"요청 완료 - ID: {request_id} - 상태 코드: {response.status_code}")
    return response


# Helper 함수
async def send_to_slack(message: SlackMessage):
    """Slack 채널로 메시지 전송"""
    try:
        # 텍스트 메시지 준비
        text = message.text
        blocks = message.blocks or []

        # 블록이 없는 경우 기본 텍스트 블록 추가
        if not blocks:
            blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]

        # Slack으로 전송
        response = slack_client.chat_postMessage(
            channel=message.channel,
            text=text,
            blocks=blocks,
            thread_ts=message.thread_ts,
            unfurl_links=False,
            unfurl_media=False,
        )

        logger.info(f"Slack 메시지 전송 성공: {response['ts']}")
        return response

    except SlackApiError as e:
        logger.error(f"Slack 메시지 전송 실패: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Slack 메시지 전송 실패: {str(e)}",
        )


async def process_messages_and_send_to_slack(
    messages: List[Dict[str, str]],
    slack_channel: str,
    thread_ts: Optional[str] = None,
    model: str = "claude-3-7-sonnet-20250219",
    max_tokens: int = 4096,
    temperature: float = 0.7,
    system: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """Claude API에 메시지 목록을 전송하고 결과를 Slack으로 전송"""
    try:
        # Claude API 호출
        logger.info(f"Claude에 메시지 전송: {len(messages)}개")

        response = claude_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
        )

        # Claude 응답 추출
        claude_response = response.content[0].text
        logger.info(f"Claude 응답 수신: {len(claude_response)} 자")

        # 마지막 사용자 메시지 가져오기
        last_user_message = "대화 내용"
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content", "대화 내용")
                break

        # Slack으로 메시지 전송
        slack_message = SlackMessage(
            channel=slack_channel,
            text=f"*컨텍스트*: {last_user_message[:50]}...\n\n*Claude의 답변*:\n{claude_response}",
            thread_ts=thread_ts,
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*컨텍스트*: {last_user_message[:100]}...",
                    },
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Claude의 답변*:\n{claude_response}",
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"모델: {model} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        }
                    ],
                },
            ],
        )

        slack_response = await send_to_slack(slack_message)

        return {
            "claude_response": claude_response,
            "slack_message_ts": slack_response["ts"],
            "thread_ts": slack_response.get("thread_ts", slack_response["ts"]),
        }

    except Exception as e:
        logger.error(f"처리 중 오류 발생: {str(e)}", exc_info=True)

        # 오류 메시지를 Slack으로 전송
        error_message = SlackMessage(
            channel=slack_channel,
            text=f"*질문 처리 중 오류 발생*: {str(e)}",
            thread_ts=thread_ts,
        )

        try:
            await send_to_slack(error_message)
        except Exception as slack_error:
            logger.error(f"오류 메시지 전송 실패: {str(slack_error)}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"처리 중 오류 발생: {str(e)}",
        )


# API 엔드포인트
@app.get("/", response_class=HTMLResponse)
async def get_web_ui(request: Request):
    """웹 UI의 메인 페이지를 제공합니다"""
    # 템플릿 파일 확인
    if not TEMPLATE_FILE.exists():
        return HTMLResponse(
            content="템플릿 파일(web.html)이 없습니다. 파일을 생성해주세요.",
            status_code=500,
        )

    return templates.TemplateResponse("web.html", {"request": request})


@app.post("/messages", dependencies=[Depends(validate_api_key)])
async def process_messages(background_tasks: BackgroundTasks, request: MessageRequest):
    """Claude에게 대화 메시지를 전송하고 결과를 Slack으로 전송"""

    # Slack 채널 설정
    slack_channel = request.slack_channel or DEFAULT_SLACK_CHANNEL
    if not slack_channel:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack 채널이 지정되지 않았습니다",
        )

    # 메시지 검증
    if not request.messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="메시지가 비어 있습니다"
        )

    # 비동기로 처리 시작
    background_tasks.add_task(
        process_messages_and_send_to_slack,
        messages=request.messages,
        slack_channel=slack_channel,
        thread_ts=request.thread_ts,
        model=request.model,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        system=request.system,
        metadata=request.metadata,
    )

    return {
        "status": "processing",
        "message": f"메시지를 처리 중입니다. 결과는 Slack 채널 {slack_channel}로 전송됩니다.",
    }


@app.get("/api/slack/channels", dependencies=[Depends(validate_api_key)])
async def get_slack_channels():
    """사용 가능한 Slack 채널 목록을 반환합니다"""
    if not slack_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Slack 연결이 구성되지 않았습니다",
        )

    try:
        # 공개 채널 가져오기
        response = slack_client.conversations_list(types="public_channel")

        channels = []
        for channel in response["channels"]:
            channels.append(
                {
                    "id": channel["id"],
                    "name": channel["name"],
                    "is_private": False,
                    "member_count": channel.get("num_members", 0),
                }
            )

        # 프라이빗 채널 가져오기 (봇이 초대된 채널만)
        response = slack_client.conversations_list(types="private_channel")

        for channel in response["channels"]:
            channels.append(
                {
                    "id": channel["id"],
                    "name": channel["name"],
                    "is_private": True,
                    "member_count": channel.get("num_members", 0),
                }
            )

        return {"channels": channels}

    except SlackApiError as e:
        logger.error(f"Slack 채널 목록 가져오기 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Slack 채널 목록 가져오기 실패: {str(e)}",
        )


@app.get("/api/slack/messages/{channel_id}", dependencies=[Depends(validate_api_key)])
async def get_channel_messages(channel_id: str, limit: int = 100):
    """특정 채널의 메시지를 가져옵니다"""
    messages = await get_slack_messages(channel_id, limit)

    if not messages:
        return {"messages": [], "count": 0}

    return {"messages": messages, "count": len(messages)}


@app.post("/slack_message", dependencies=[Depends(validate_api_key)])
async def send_slack_message(message: SlackMessage):
    """Slack 채널로 직접 메시지 전송"""
    try:
        response = await send_to_slack(message)
        return {
            "status": "success",
            "message_ts": response["ts"],
            "channel": response["channel"],
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Slack 메시지 전송 실패: {str(e)}",
        )


@app.get("/health", dependencies=[Depends(validate_api_key)])
async def health_check():
    """서버 상태 확인"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "slack_connected": slack_client is not None,
        "claude_connected": True,
    }


DEFAULT_SYSTEM_PROMPT = """당신은 슬랙 채널의 대화 내용을 분석하고 질문에 답변하는 도우미입니다.
제공된 메시지 컨텍스트를 철저히 분석하고, 가능한 한 정확하고 유용한 답변을 제공해주세요.
구체적인 정보가 필요하다면 메시지 내용을 인용하여 답변할 수 있습니다.
답변은 명확하고 간결하게 유지하되, 충분한 세부 정보를 포함해야 합니다.
확실하지 않은 정보는 추측하지 말고, 알 수 없다고 솔직하게 말해주세요.
메시지 내용과 질문 사이에 모순이 있으면 그 점을 지적해주세요."""


class SlackQuestionRequest(BaseModel):
    channel_id: str
    message_limit: int = 100
    question: str
    slack_output_channel: str
    thread_ts: Optional[str] = None
    model: str = "claude-3-7-sonnet-20250219"
    max_tokens: int = 4096
    temperature: float = 0.7
    system: Optional[str] = Field(default=DEFAULT_SYSTEM_PROMPT)


# ask_with_slack 엔드포인트 수정
# @app.post("/ask_with_slack", dependencies=[Depends(validate_api_key)])
@app.post("/ask_with_slack")
async def ask_claude_with_slack_context(
    background_tasks: BackgroundTasks, request: SlackQuestionRequest
):
    """Slack 메시지 컨텍스트를 포함하여 Claude에게 질문하고 결과를 Slack으로 전송합니다"""
    # 채널 ID에서 가능한 접두사 제거 (#, @)
    channel_id = request.channel_id.lstrip("#@")
    slack_output_channel = request.slack_output_channel.lstrip("#@")

    # Slack 채널 메시지 가져오기
    slack_messages = await get_slack_messages(channel_id, request.message_limit)

    if not slack_messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"채널 {channel_id}에서 메시지를 가져올 수 없습니다",
        )

    # Slack 메시지를 Claude 프롬프트로 변환
    prompt = format_slack_messages_for_claude(slack_messages, request.question)

    # 비동기로 처리 시작
    background_tasks.add_task(
        process_claude_and_send_to_slack,
        question=prompt,
        slack_channel=slack_output_channel,
        thread_ts=request.thread_ts,
        model=request.model,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        system=request.system,
        metadata={
            "source_channel": channel_id,
            "message_count": len(slack_messages),
            "original_question": request.question,
        },
    )

    return {
        "status": "processing",
        "message": f"Slack 채널 {channel_id}의 {len(slack_messages)}개 메시지를 컨텍스트로 사용해 질문을 처리 중입니다. 결과는 {slack_output_channel} 채널로 전송됩니다.",
    }


# process_claude_and_send_to_slack 함수 수정 (메타데이터 출력 추가)
async def process_claude_and_send_to_slack(
    question: str,
    slack_channel: str,
    thread_ts: Optional[str] = None,
    model: str = "claude-3-7-sonnet-20250219",
    max_tokens: int = 4096,
    temperature: float = 0.7,
    system: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """Claude API에 질문하고 결과를 Slack으로 전송"""
    try:
        # Claude API 호출
        logger.info(f"Claude에 질문 전송: '{question[:200]}...'")

        response = claude_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": question}],
        )

        # Claude 응답 추출
        claude_response = response.content[0].text
        logger.info(f"Claude 응답 수신: {len(claude_response)} 자")

        # 메타데이터에서 필요한 정보 추출
        source_info = ""
        original_question = ""
        if metadata:
            source_channel = metadata.get("source_channel", "")
            message_count = metadata.get("message_count", 0)
            original_question = metadata.get("original_question", "")

            if source_channel and message_count:
                source_info = f"*소스 정보*: 채널 `{source_channel}`의 {message_count}개 메시지를 참조"

        # 원본 질문이 있으면 표시, 없으면 전체 질문 사용
        display_question = original_question if original_question else question

        # 만약 질문이 너무 길면 잘라내기
        if len(display_question) > 300:
            display_question = display_question[:297] + "..."

        # Slack으로 메시지 전송
        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*질문*: {display_question}"},
            }
        ]

        # 소스 정보가 있으면 추가
        if source_info:
            blocks.append(
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": source_info}],
                }
            )

        blocks.extend(
            [
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Claude의 답변*:\n{claude_response}",
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"모델: {model} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        }
                    ],
                },
            ]
        )

        slack_message = SlackMessage(
            channel=slack_channel,
            text=f"*질문*: {display_question}\n\n*Claude의 답변*:\n{claude_response}",
            thread_ts=thread_ts,
            blocks=blocks,
        )

        slack_response = await send_to_slack(slack_message)

        return {
            "claude_response": claude_response,
            "slack_message_ts": slack_response["ts"],
            "thread_ts": slack_response.get("thread_ts", slack_response["ts"]),
        }

    except Exception as e:
        logger.error(f"처리 중 오류 발생: {str(e)}", exc_info=True)

        # 오류 메시지를 Slack으로 전송
        error_message = SlackMessage(
            channel=slack_channel,
            text=f"*질문 처리 중 오류 발생*: {str(e)}",
            thread_ts=thread_ts,
        )

        try:
            await send_to_slack(error_message)
        except Exception as slack_error:
            logger.error(f"오류 메시지 전송 실패: {str(slack_error)}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"처리 중 오류 발생: {str(e)}",
        )


# get_slack_messages 함수 수정 (채널 ID로 채널명 찾기 지원)
async def get_slack_messages(
    channel_id: str,
    limit: int = 100,
    oldest: Optional[str] = None,
    latest: Optional[str] = None,
):
    """Slack 채널에서 메시지를 가져옵니다. 채널명 또는 ID를 처리합니다."""
    if not slack_client:
        logger.warning("Slack 클라이언트가 초기화되지 않았습니다.")
        return []

    # 만약 채널 ID가 #으로 시작하면 채널명일 수 있음
    # 실제 채널 ID로 변환 시도
    if channel_id.startswith("#"):
        channel_name = channel_id[1:]  # # 제거
        try:
            # 채널 목록 가져오기
            response = slack_client.conversations_list(
                types="public_channel,private_channel"
            )
            for channel in response["channels"]:
                if channel["name"] == channel_name:
                    channel_id = channel["id"]
                    logger.info(
                        f"채널명 '{channel_name}'을(를) ID '{channel_id}'로 변환했습니다."
                    )
                    break
        except SlackApiError as e:
            logger.warning(f"채널명을 ID로 변환 중 오류 발생: {e}")

    try:
        # 채널 기록 가져오기
        logger.info(f"채널 {channel_id}에서 메시지 {limit}개를 가져오는 중...")
        response = slack_client.conversations_history(
            channel=channel_id, limit=limit, oldest=oldest, latest=latest
        )

        messages = response["messages"]

        # 메시지 처리 및 포맷팅
        formatted_messages = []
        for msg in messages:
            if "user" in msg and "text" in msg:
                try:
                    # 사용자 정보 가져오기
                    user_info = slack_client.users_info(user=msg["user"])["user"]
                    username = user_info.get(
                        "real_name", user_info.get("name", "Unknown User")
                    )

                    # 메시지 객체 생성
                    formatted_msg = {
                        "user": username,
                        "text": msg["text"],
                        "ts": msg["ts"],
                        "timestamp": datetime.fromtimestamp(float(msg["ts"])).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                    }

                    # 첨부 파일이 있는 경우
                    if "files" in msg:
                        formatted_msg["has_files"] = True
                        formatted_msg["file_count"] = len(msg["files"])

                    formatted_messages.append(formatted_msg)
                except SlackApiError as e:
                    logger.warning(f"사용자 정보 가져오기 실패: {e}")
                    # 최소한의 정보로 메시지 추가
                    formatted_messages.append(
                        {
                            "user": msg.get("user", "Unknown"),
                            "text": msg["text"],
                            "ts": msg["ts"],
                            "timestamp": datetime.fromtimestamp(
                                float(msg["ts"])
                            ).strftime("%Y-%m-%d %H:%M:%S"),
                        }
                    )

        # 오래된 메시지가 먼저 오도록 정렬 (시간 순서)
        formatted_messages.reverse()

        logger.info(
            f"채널 {channel_id}에서 {len(formatted_messages)}개의 메시지를 가져왔습니다."
        )
        return formatted_messages

    except SlackApiError as e:
        logger.error(f"Slack API 오류: {e}")
        return []


# format_slack_messages_for_claude 함수 향상 (포맷팅 개선)
def format_slack_messages_for_claude(
    messages: List[Dict[str, Any]], context_message: Optional[str] = None
):
    """Slack 메시지를 Claude 프롬프트 형식으로 변환합니다"""

    if not messages:
        return "Slack 채널에서 메시지를 가져오지 못했습니다."

    # 헤더 추가
    prompt = "다음은 Slack 채널에서 가져온 대화 내용입니다:\n\n"

    # 대화 형식으로 메시지를 텍스트로 변환
    for i, msg in enumerate(messages):
        # 이름 형식 처리
        name = msg["user"]

        # 메시지 구분을 위한 서식
        if i > 0:
            prompt += "\n"

        prompt += f"{name} ({msg['timestamp']}): {msg['text']}\n"

        # 첨부 파일이 있는 경우
        if msg.get("has_files", False):
            prompt += f"[첨부 파일 {msg.get('file_count', 1)}개]\n"

    # 컨텍스트 메시지 추가
    if context_message:
        prompt += (
            f"\n\n위 대화 내용을 바탕으로 다음 질문에 답변해주세요: {context_message}"
        )

    return prompt


# 채널 검색 기능 추가
# @app.get("/api/slack/search_channels", dependencies=[Depends(validate_api_key)])
@app.get("/api/slack/search_channels")
async def search_slack_channels(query: str):
    """채널명으로 Slack 채널 검색"""
    if not slack_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Slack 연결이 구성되지 않았습니다",
        )

    if not query or len(query) < 2:
        return {"channels": []}

    try:
        # 채널 목록 가져오기
        response = slack_client.conversations_list(
            types="public_channel,private_channel"
        )

        # 검색어로 필터링
        query = query.lower()
        matched_channels = []

        for channel in response["channels"]:
            if query in channel["name"].lower():
                matched_channels.append(
                    {
                        "id": channel["id"],
                        "name": channel["name"],
                        "is_private": channel["is_private"],
                        "member_count": channel.get("num_members", 0),
                    }
                )

        return {"channels": matched_channels}

    except SlackApiError as e:
        logger.error(f"Slack 채널 검색 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Slack 채널 검색 실패: {str(e)}",
        )


# 메인 함수
if __name__ == "__main__":
    logger.info("Claude-Slack Bridge 서버 시작 중...")
    logger.info("이 서버는 로컬 네트워크에서만 접근 가능합니다.")
    try:
        # 로컬 호스트에서만 실행
        uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
    except Exception as e:
        logger.error(f"서버 실행 중 오류 발생: {str(e)}", exc_info=True)
