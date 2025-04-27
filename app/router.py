from fastapi import APIRouter
from app.schemas import MCPRequest, SessionRequest, TaskRequest
from app.utils import create_prompt, ask_claude, send_to_slack, SessionManager

mcp_router = APIRouter()
session_router = APIRouter()
task_router = APIRouter()

session_manager = SessionManager()


@mcp_router.post("/mcp")
async def mcp_handler(req: MCPRequest):
    session = session_manager.get_current_session()
    prompt = create_prompt(req.message, session)
    answer = ask_claude(prompt)
    send_to_slack(answer)
    session_manager.append_history(req.message, answer)
    return {"prompt": prompt, "answer": answer, "status": "Answered and sent to Slack"}


@session_router.post("/session/start")
async def start_session(req: SessionRequest):
    session_manager.start_session(req.context, req.environment)
    return {"status": "Session started"}


@task_router.post("/task/add")
async def add_task(req: TaskRequest):
    session_manager.add_task(req.task)
    return {"status": "Task added"}
