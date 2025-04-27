from fastapi import APIRouter, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.utils import (
    fetch_slack_channels,
    fetch_slack_messages,
    create_prompt,
    ask_claude,
    send_to_slack,
    SessionManager,
)
from app.settings import BASE_DIR

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

web_router = APIRouter()

session_manager = SessionManager()


@web_router.get("/", response_class=HTMLResponse)
async def show_mcp_form(request: Request):
    channels = fetch_slack_channels()
    return templates.TemplateResponse(
        "mcp.html", {"request": request, "channels": channels}
    )


def process_claude_query(input_channel: str, output_channel: str, message: str):
    messages = fetch_slack_messages(limit=10, channel_id=input_channel)
    session_manager.import_history_from_messages(messages)
    session = session_manager.get_current_session()
    prompt = create_prompt(message, session)
    answer = ask_claude(prompt)
    session_manager.add_full_history(message, answer)
    send_to_slack(answer, channel_id=output_channel)


@web_router.post("/send", response_class=HTMLResponse)
async def send_mcp(
    request: Request,
    background_tasks: BackgroundTasks,
    input_channel: str = Form(...),
    output_channel: str = Form(...),
    message: str = Form(...),
):
    # 백그라운드 작업 등록
    background_tasks.add_task(
        process_claude_query, input_channel, output_channel, message
    )

    # 바로 응답 (빠르게)
    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "prompt": "Background task started!",
            "answer": "Processing your query to Claude and sending the result to Slack...",
        },
    )
