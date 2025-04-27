from fastapi import FastAPI
from app.web_router import web_router

app = FastAPI()

app.include_router(web_router)  #
