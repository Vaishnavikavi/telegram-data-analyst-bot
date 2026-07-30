import os
import requests
from fastapi.responses import FileResponse
import os
from fastapi import FastAPI, Request

from agent import process_message

BOT_TOKEN = os.getenv("BOT_TOKEN")

app = FastAPI()


@app.get("/")
def home():
    return {
        "status": "running"
    }

@app.get("/logs/run.jsonl")
def get_log():

    if not os.path.exists("logs/run.jsonl"):
        return {"error": "No log available"}

    return FileResponse(
        "logs/run.jsonl",
        media_type="application/json"
    )

@app.post("/webhook")
async def webhook(request: Request):

    update = await request.json()

    message = update.get("message")

    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]

    text = message.get("text", "")

    answer = process_message(
        chat_id,
        text
    )

    send_message(chat_id, answer)

    return {"ok": True}


def send_message(chat_id, text):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text
        },
        timeout=60
    )
