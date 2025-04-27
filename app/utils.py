import json

import anthropic
import requests
from app.settings import (
    SLACK_TOKEN,
    CHANNEL_ID,
    RESULT_CHANNEL_ID,
    CLAUDE_API_KEY,
    CLAUDE_API_URL,
    CLAUDE_MODEL,
)

import os
import json
from pathlib import Path
from app.settings import STORAGE_DIR

SESSION_FILE = STORAGE_DIR / "session.json"

claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)


class SessionManager:
    def __init__(self):
        self.context = ""
        self.environment = ""
        self.tasks = []
        self.history = []
        self.load_session()

    def load_session(self):
        """앱 시작할 때 파일에서 세션 불러오기"""
        if SESSION_FILE.exists():
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.context = data.get("context", "")
                self.environment = data.get("environment", "")
                self.tasks = data.get("tasks", [])
                self.history = data.get("history", [])
        else:
            print("저장된 세션 파일이 없습니다. 새로 시작합니다.")

    def save_session(self):
        """세션을 파일로 저장"""
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "context": self.context,
                    "environment": self.environment,
                    "tasks": self.tasks,
                    "history": self.history,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    def start_session(self, context: str, environment: str):
        self.context = context
        self.environment = environment
        self.tasks = []
        self.history = []
        self.save_session()

    def add_task(self, task: str):
        self.tasks.append(task)
        self.save_session()

    def append_history(self, user_message: str, assistant_response: str):
        self.history.append({"user": user_message, "assistant": assistant_response})
        self.save_session()

    def import_history_from_messages(self, messages: list[str]):
        f"""Slack 메시지를 히스토리로 변환해서 추가"""
        for message in reversed(messages):
            self.history.append({"user": message, "assistant": "아직 답변 없음"})
        self.save_session()

    def get_current_session(self):
        return {
            "context": self.context,
            "environment": self.environment,
            "tasks": self.tasks,
            "history": self.history,
        }

    def add_full_history(self, user_message: str, assistant_response: str):
        """사용자 메시지와 Claude 답변을 세트로 history에 추가"""
        self.history.append({"user": user_message, "assistant": assistant_response})
        self.save_session()


def create_prompt(message_text: str, session: dict) -> str:
    mcp_json = json.dumps(session, indent=2, ensure_ascii=False)
    prompt = f"""
[MCP Session]
{mcp_json}

[User Query]
{message_text}

Please answer based on the session and tasks above.
"""
    return prompt


def ask_claude(
    prompt: str,
    model: str = "claude-3-7-sonnet-20250219",
) -> str:
    try:
        response = claude_client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        # response.content 는 바로 Claude의 답변 텍스트야!
        return response.content[0].text

    except Exception as e:
        print("Claude API 호출 에러:", str(e))
        return "Claude API 호출 실패"


def send_to_slack(text: str, channel_id: str = RESULT_CHANNEL_ID):
    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer " + SLACK_TOKEN,
        "Content-Type": "application/json",
    }

    if channel_id is None:
        channel_id = CHANNEL_ID

    parts = split_text(text, limit=2900)  # 안전하게 2900자씩

    thread_ts = None  # 스레드 시작 ts

    for idx, part in enumerate(parts):
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Claude Answer Part {idx+1}:*\n{part}",
                },
            },
            {"type": "divider"},
        ]
        data = {
            "channel": channel_id,
            "blocks": blocks,
        }
        if thread_ts:
            data["thread_ts"] = thread_ts  # 스레드로 이어붙이기

        response = requests.post(url, headers=headers, json=data)

        if not response.ok:
            print(f"Slack 전송 실패 (파트 {idx+1}):", response.text)
        else:
            if idx == 0:
                # 첫 번째 메시지에서 thread_ts를 확보
                thread_ts = response.json().get("ts")


def fetch_slack_messages(limit=10, channel_id=CHANNEL_ID):
    """Slack 채널 최근 메시지 가져오기"""
    url = "https://slack.com/api/conversations.history"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    params = {"channel": channel_id, "limit": limit}
    response = requests.get(url, headers=headers, params=params)
    if response.ok:
        return [msg["text"] for msg in response.json().get("messages", [])]
    else:
        print("Slack 메시지 가져오기 실패:", response.text)
        return []


def fetch_slack_channels():
    url = "https://slack.com/api/conversations.list"
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    params = {"types": "public_channel,private_channel"}
    response = requests.get(url, headers=headers, params=params)
    if response.ok:
        channels = response.json().get("channels", [])
        return [(ch["id"], ch["name"]) for ch in channels]
    else:
        print("Slack 채널 가져오기 실패:", response.text)
        return []


def split_text(text: str, limit: int = 3000) -> list[str]:
    """
    Slack 메시지 3000자 제한에 맞춰 텍스트를 나눈다.
    문장 단위로 나누되, 문장이 너무 길면 강제로 자른다.
    """
    chunks = []
    current_chunk = ""

    for line in text.splitlines(keepends=True):  # 줄 단위로 먼저 분리
        if len(current_chunk) + len(line) > limit:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk += line

    if current_chunk:
        chunks.append(current_chunk)

    # 혹시라도 한 줄이 너무 길어서 3000자를 넘는 경우를 위해 다시 한 번 체크
    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= limit:
            final_chunks.append(chunk)
        else:
            # 너무 긴 chunk는 강제로 자른다
            for i in range(0, len(chunk), limit):
                final_chunks.append(chunk[i : i + limit])

    return final_chunks
