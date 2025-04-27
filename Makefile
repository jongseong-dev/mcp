# Makefile

APP_DIR=app
HOST=127.0.0.1
PORT=8000

.PHONY: dev

dev:
	uvicorn $(APP_DIR).main:app --reload --host $(HOST) --port $(PORT)
