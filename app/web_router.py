from fastapi import APIRouter, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.utils import (
    fetch_slack_channels,
    fetch_slack_messages,
    create_prompt,
    ask_claude,
    SessionManager,
    process_claude_and_send_to_slack,
)
from app.settings import BASE_DIR, CLAUDE_MODEL

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

web_router = APIRouter()

session_manager = SessionManager()


@web_router.get("/", response_class=HTMLResponse)
async def show_mcp_form(request: Request):
    channels = fetch_slack_channels()
    return templates.TemplateResponse(
        "mcp.html", {"request": request, "channels": channels}
    )


@web_router.post("/send", response_class=HTMLResponse)
async def send_mcp(
    request: Request,
    background_tasks: BackgroundTasks,
    input_channel: str = Form(...),
    output_channel: str = Form(...),
    period_days: int = Form(...),
    message_limit: int = Form(...),
    message: str = Form(...),
):

    # 1. 사용자가 입력한 기간, 개수로 Slack 문맥 가져오기
    slack_messages = fetch_slack_messages(
        channel_id=input_channel,
        limit=message_limit,
        days_ago=period_days,
    )

    # 2. 사용자 질문을 세션에 기록 (assistant 답변은 이후 기록)
    session_manager.add_full_history(user_message=message, assistant_response="")

    # 3. MCP 세션 준비
    session = session_manager.get_current_session()

    # 4. 프롬프트 생성
    prompt = create_prompt(message, session, slack_messages=slack_messages)

    # 5. Claude 호출 + Slack 전송 (백그라운드)
    background_tasks.add_task(
        process_claude_and_send_to_slack,
        question=prompt,
        slack_channel=output_channel,
        thread_ts=None,
        model=CLAUDE_MODEL,
    )

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "prompt": prompt,
            "answer": "답변 생성 및 Slack 전송이 백그라운드에서 진행 중입니다.",
        },
    )
