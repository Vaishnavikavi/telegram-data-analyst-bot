import os
import json
import time
import requests

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from agent import process_message


BOT_TOKEN = os.getenv("BOT_TOKEN")

app = FastAPI()


START_TIME = time.time()


@app.get("/")
def home():
    return {
        "status": "running",
        "service": "telegram-data-analyst-bot"
    }


@app.get("/healthz")
def health():

    return {
        "status": "ok",
        "uptime_s": time.time() - START_TIME
    }


@app.get("/logs/run.jsonl")
def get_logs():

    file_path = "logs/run.jsonl"

    if not os.path.exists(file_path):
        return JSONResponse(
            {
                "error": "No log available"
            },
            status_code=404
        )

    return FileResponse(
        file_path,
        media_type="application/json"
    )


@app.post("/webhook")
async def webhook(request: Request):

    try:

        update = await request.json()

        message = update.get("message")

        if not message:
            return {
                "ok": True
            }


        chat_id = message["chat"]["id"]

        text = message.get(
            "text",
            ""
        )


        answer = process_message(
            chat_id,
            text
        )


        send_message(
            chat_id,
            answer
        )


        return {
            "ok": True
        }


    except Exception as e:

        print(
            "Webhook error:",
            e
        )

        return JSONResponse(
            {
                "ok": False,
                "error": str(e)
            },
            status_code=500
        )



def send_message(chat_id, text):

    if not BOT_TOKEN:
        print(
            "BOT_TOKEN missing"
        )
        return


    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )


    # Telegram message limit protection
    if len(text) > 4000:
        text = text[:4000]


    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text
        },
        timeout=30
    )


    print(
        "Telegram Status:",
        response.status_code
    )

    print(
        response.text
    )



@app.get("/set-webhook")
def set_webhook():

    webhook_url = os.getenv(
        "WEBHOOK_URL"
    )

    if not webhook_url:
        return {
            "error": "WEBHOOK_URL missing"
        }


    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/setWebhook"
    )


    response = requests.post(
        url,
        json={
            "url": webhook_url
        }
    )


    return response.json()
