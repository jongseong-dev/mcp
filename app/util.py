import os

import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional


from fastapi import (
    HTTPException,
    status,
)


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

        # Slack 메시지 전송 시작 - 첫 번째 메시지에는 질문과 소스 정보 포함
        initial_blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*질문*: {display_question}"},
            }
        ]

        # 소스 정보가 있으면 추가
        if source_info:
            initial_blocks.append(
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": source_info}],
                }
            )

        initial_blocks.append({"type": "divider"})

        # 응답 분할 필요 여부 확인 (Slack은 텍스트 블록당 3000자 제한)
        SLACK_TEXT_LIMIT = 2900  # 안전 마진 포함

        if len(claude_response) <= SLACK_TEXT_LIMIT:
            # 응답이 짧으면 하나의 메시지로 보내기
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

            initial_message = SlackMessage(
                channel=slack_channel,
                text=f"*질문*: {display_question}\n\n*Claude의 답변*: (응답 참조)",
                thread_ts=thread_ts,
                blocks=initial_blocks,
            )

            slack_response = await send_to_slack(initial_message)
            thread_ts_for_replies = slack_response.get("ts")

        else:
            # 응답이 길면 응답 시작 메시지 보내기
            initial_blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Claude의 답변*: (응답이 길어 여러 메시지로 분할됩니다)",
                    },
                }
            )

            initial_message = SlackMessage(
                channel=slack_channel,
                text=f"*질문*: {display_question}\n\n*Claude의 답변*: (응답이 길어 여러 메시지로 분할됩니다)",
                thread_ts=thread_ts,
                blocks=initial_blocks,
            )

            slack_response = await send_to_slack(initial_message)
            thread_ts_for_replies = slack_response.get("ts")

            # 응답을 여러 메시지로 분할하여 전송
            chunks = split_long_message(claude_response, SLACK_TEXT_LIMIT)

            for i, chunk in enumerate(chunks):
                # 청크 번호 표시 (1/3, 2/3, 3/3 등)
                chunk_header = f"*답변 {i+1}/{len(chunks)}*:\n\n"

                chunk_blocks = [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": chunk_header + chunk},
                    }
                ]

                # 마지막 청크에만 모델 정보 추가
                if i == len(chunks) - 1:
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

                chunk_message = SlackMessage(
                    channel=slack_channel,
                    text=f"답변 {i+1}/{len(chunks)}",
                    thread_ts=thread_ts_for_replies,  # 생성된 스레드에 답장
                    blocks=chunk_blocks,
                )

                await send_to_slack(chunk_message)

                # 메시지 간 짧은 지연 추가 (Slack 속도 제한 방지)
                await asyncio.sleep(0.5)

        return {
            "claude_response": claude_response,
            "slack_message_ts": slack_response["ts"],
            "thread_ts": thread_ts or slack_response["ts"],
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


# 긴 메시지를 분할하는 헬퍼 함수
def split_long_message(message: str, max_length: int) -> List[str]:
    """긴 메시지를 여러 청크로 분할합니다"""
    # 메시지가 제한보다 짧으면 바로 반환
    if len(message) <= max_length:
        return [message]

    chunks = []
    current_chunk = ""

    # 단락 기준으로 분할 시도
    paragraphs = message.split("\n\n")

    for paragraph in paragraphs:
        # 단락 자체가 제한보다 길면 더 작게 분할
        if len(paragraph) > max_length:
            # 현재 청크를 추가하고 새로 시작
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""

            # 단락을 라인 단위로 분할
            lines = paragraph.split("\n")
            for line in lines:
                # 라인 자체가 너무 길면 단어 단위로 분할
                if len(line) > max_length:
                    words = line.split(" ")
                    for word in words:
                        if len(current_chunk) + len(word) + 1 > max_length:
                            chunks.append(current_chunk)
                            current_chunk = word + " "
                        else:
                            current_chunk += word + " "
                # 일반 라인 처리
                elif len(current_chunk) + len(line) + 1 > max_length:
                    chunks.append(current_chunk)
                    current_chunk = line + "\n"
                else:
                    current_chunk += line + "\n"
        # 일반 단락 처리
        elif len(current_chunk) + len(paragraph) + 2 > max_length:
            chunks.append(current_chunk)
            current_chunk = paragraph + "\n\n"
        else:
            current_chunk += paragraph + "\n\n"

    # 남은 텍스트 추가
    if current_chunk:
        chunks.append(current_chunk)

    return chunks
