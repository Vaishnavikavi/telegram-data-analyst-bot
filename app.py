import os
import requests

from fastapi import FastAPI, Request

BOT_TOKEN = os.getenv("BOT_TOKEN")

app = FastAPI()

from openai import OpenAI
import os

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
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

    send_message(chat_id, f"You said:\n{text}")

    return {"ok": True}


def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
        },
        timeout=30,
    )
