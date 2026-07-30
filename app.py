import os
import requests

from fastapi import FastAPI, Request
from google import genai

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

MODEL = "gemini-flash-latest"

app = FastAPI()


@app.get("/")
def home():
    models = []

    try:
        for model in client.models.list():
            models.append({
                "name": model.name,
                "methods": getattr(model, "supported_generation_methods", [])
            })

        return models

    except Exception as e:
        return {"error": str(e)}


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

    print("Telegram Status:", response.status_code)
    print("Telegram Response:", response.text)


def ask_llm(user_message: str):
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=user_message,
        )

        return response.text

    except Exception as e:
        print(e)
        return f"Error: {e}"
