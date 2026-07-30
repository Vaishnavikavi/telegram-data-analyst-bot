import os
import requests

from fastapi import FastAPI, Request
from openai import OpenAI

BOT_TOKEN = os.getenv("BOT_TOKEN")

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

app = FastAPI()


@app.get("/")
def home():
    return {"status": "running"}


@app.post("/webhook")
async def webhook(request: Request):
    update = await request.json()

    message = update.get("message")

    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    answer = ask_llm(text)

    send_message(chat_id, answer)

    return {"ok": True}


def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
        },
        timeout=30,
    )

    print(response.status_code)
    print(response.text)


def ask_llm(user_message: str):
    response = client.responses.create(
        model=MODEL,
        input=user_message,
    )

    return response.output_text
