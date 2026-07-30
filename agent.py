import json
import os
import re

from google import genai

from memory import get_history, add_message
from logger import start_log, log_step, finish_log

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

MODEL = "gemini-flash-latest"


def extract_urls(text: str):
    pattern = r"https?://[^\s]+"
    return re.findall(pattern, text)


SYSTEM_PROMPT = """
You are a data analyst.

Your job is to answer the user's question.

Rules:

1. If the user includes a public dataset URL,
   say exactly:
   DOWNLOAD_DATASET

2. Otherwise answer normally.

3. If the user explicitly asks to return JSON,
   return ONLY valid JSON.

Never wrap JSON inside markdown.
"""


def process_message(chat_id, text):

    start_log(chat_id)

    history = get_history(chat_id)

    add_message(chat_id, "user", text)

    urls = extract_urls(text)

    if urls:

        log_step({
            "action": "dataset_detected",
            "urls": urls
        })

        finish_log()

        return json.dumps({
            "answer": "Dataset detected. (Download tool will be added next.)",
            "log_url": "/logs/run.jsonl"
        })

    prompt = SYSTEM_PROMPT

    for msg in history:
        prompt += f"\n{msg['role']}: {msg['content']}"

    prompt += f"\nuser: {text}"

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt
    )

    answer = response.text.strip()

    add_message(
        chat_id,
        "assistant",
        answer
    )

    log_step({
        "action": "llm_response"
    })

    finish_log()

    return answer
