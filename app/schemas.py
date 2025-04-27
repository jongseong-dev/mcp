from pydantic import BaseModel


class MCPRequest(BaseModel):
    message: str


class SessionRequest(BaseModel):
    context: str
    environment: str


class TaskRequest(BaseModel):
    task: str
