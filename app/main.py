from fastapi import FastAPI
from app.router import mcp_router, session_router, task_router
from app.web_router import web_router

app = FastAPI()

app.include_router(mcp_router)
app.include_router(session_router)
app.include_router(task_router)
app.include_router(web_router)  #
