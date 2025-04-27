import json
import time
from datetime import datetime

import anthropic
import requests
from app.settings import (
    SLACK_TOKEN,
    CHANNEL_ID,
    RESULT_CHANNEL_ID,
    CLAUDE_API_KEY,
    CLAUDE_API_URL,
    CLAUDE_MODEL,
    SLACK_TEXT_LIMIT,
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
        """최근 3개의 history만 포함한 세션 반환"""
        return {
            "context": self.context,
            "environment": self.environment,
            "tasks": self.tasks,
            "history": self.history[-3:],  # 최근 3개만
        }

    def add_full_history(self, user_message: str, assistant_response: str):
        """사용자 질문과 Claude 답변을 함께 기록"""
        self.history.append({"user": user_message, "assistant": assistant_response})
        self.save_session()


def create_prompt(
    user_question: str, session: dict, slack_messages: list[str] = None
) -> str:
    mcp_json = json.dumps(session, indent=2, ensure_ascii=False)

    slack_context = ""
    if slack_messages:
        slack_context = "\n".join(f"- {msg}" for msg in slack_messages)

    prompt = f"""
[MCP Session]
{mcp_json}

[Slack Channel Context]
{slack_context}

[User Query]
{user_question}

Please answer based on the session, slack context, and tasks above.
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


def split_long_message(message: str, max_length: int = 2900) -> list[str]:
    if len(message) <= max_length:
        return [message]

    chunks = []
    current_chunk = ""

    paragraphs = message.split("\n\n")

    for paragraph in paragraphs:
        if len(paragraph) > max_length:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""

            lines = paragraph.split("\n")
            for line in lines:
                if len(line) > max_length:
                    words = line.split(" ")
                    for word in words:
                        if len(current_chunk) + len(word) + 1 > max_length:
                            chunks.append(current_chunk)
                            current_chunk = word + " "
                        else:
                            current_chunk += word + " "
                elif len(current_chunk) + len(line) + 1 > max_length:
                    chunks.append(current_chunk)
                    current_chunk = line + "\n"
                else:
                    current_chunk += line + "\n"
        elif len(current_chunk) + len(paragraph) + 2 > max_length:
            chunks.append(current_chunk)
            current_chunk = paragraph + "\n\n"
        else:
            current_chunk += paragraph + "\n\n"

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def send_block_to_slack(blocks: list, channel_id: str, thread_ts: str = None):
    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {SLACK_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "channel": channel_id,
        "blocks": blocks,
    }
    if thread_ts:
        data["thread_ts"] = thread_ts

    response = requests.post(url, headers=headers, json=data)
    if not response.ok:
        print("Slack 전송 실패:", response.text)
    return response.json()


def process_claude_and_send_to_slack(
    question: str,
    slack_channel: str = CHANNEL_ID,
    thread_ts: str | None = None,
    model: str = CLAUDE_MODEL,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    system: str = CLAUDE_MODEL,
    metadata: dict | None = None,
):
    """Claude에 질문하고 Slack에 스레드로 답변 보내기"""

    # 1. Claude 호출
    response = claude_client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": question}],
    )
    claude_response = response.content[0].text
    print(f"Claude 응답 {len(claude_response)}자 수신 완료")

    # 2. (Optional) 메타데이터 표시
    source_info = ""
    if metadata:
        source_channel = metadata.get("source_channel", "")
        message_count = metadata.get("message_count", 0)
        if source_channel and message_count:
            source_info = (
                f"*소스 정보*: 채널 `{source_channel}`의 {message_count}개 메시지 참조"
            )

    # 3. 질문 표시
    display_question = question
    if len(display_question) > 300:
        display_question = display_question[:297] + "..."

    # 4. Slack 메시지 블록 준비
    initial_blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*질문*: {display_question}"},
        }
    ]
    if source_info:
        initial_blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": source_info}],
            }
        )
    initial_blocks.append({"type": "divider"})

    # 5. Slack에 첫 메시지 전송
    if len(claude_response) <= SLACK_TEXT_LIMIT:
        # 답변이 짧을 때
        initial_blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Claude의 답변*:\n{claude_response}",
                },
            }
        )
        initial_blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"모델: {model} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    }
                ],
            }
        )

        slack_response = send_block_to_slack(initial_blocks, slack_channel, thread_ts)
        return {"thread_ts": slack_response.get("ts")}

    else:
        # 답변이 길 때 (분할해서 전송)
        initial_blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Claude의 답변*: (응답이 길어 여러 메시지로 분할됩니다)",
                },
            }
        )

        slack_response = send_block_to_slack(initial_blocks, slack_channel, thread_ts)
        thread_ts_for_replies = slack_response.get("ts")

        chunks = split_long_message(claude_response, max_length=SLACK_TEXT_LIMIT)
        for idx, chunk in enumerate(chunks):
            chunk_blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*답변 {idx+1}/{len(chunks)}*:\n{chunk.strip()}",
                    },
                }
            ]
            if idx == len(chunks) - 1:
                chunk_blocks.append(
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"모델: {model} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                            }
                        ],
                    }
                )

            send_block_to_slack(
                chunk_blocks, slack_channel, thread_ts=thread_ts_for_replies
            )

            time.sleep(0.5)

        return {"thread_ts": thread_ts_for_replies}


def fetch_slack_messages(channel_id: str, limit: int = 10, days_ago: int = 3):
    """Slack 채널에서 기간과 개수에 맞춰 메시지 가져오기"""
    url = "https://slack.com/api/conversations.history"
    headers = {"Authorization": f"Bearer " + SLACK_TOKEN}
    oldest = time.time() - (days_ago * 86400)  # N일 전 timestamp
    params = {"channel": channel_id, "limit": limit, "oldest": oldest}
    response = requests.get(url, headers=headers, params=params)
    if response.ok:
        return [
            msg["text"] for msg in response.json().get("messages", []) if "text" in msg
        ]
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
