import os
import json
import re

from google import genai

from memory import get_history, add_message
from logger import start_log, log_step, finish_log
from tools import analyze_dataset


client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-flash-latest"
)


LOG_URL = os.getenv(
    "PUBLIC_LOG_URL",
    "https://telegram-data-analyst-bot-yl4v.onrender.com/logs/run.jsonl"
)


SYSTEM_PROMPT = """

You are a data analyst AI agent.

Your job is to answer the user's data analysis question.

Rules:

1. If the user provides a dataset URL, analyze the dataset.
2. Use calculations from the dataset. Do not guess.
3. Answer exactly what the user asks.
4. Final response must be ONLY valid JSON.

Required format:

{
 "answer": <answer requested by user>,
 "log_url": "PUBLIC_LOG_URL"
}

Never use markdown.
Never add explanations outside JSON.

"""


def extract_urls(text):

    return re.findall(
        r"https?://[^\s]+",
        text
    )



def clean_json(text):

    text = text.strip()

    if text.startswith("```"):

        text = (
            text
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

    return text



def process_message(chat_id, text):

    start_log(chat_id)

    try:

        log_step(
            {
                "event": "message_received",
                "text": text
            }
        )


        history = get_history(chat_id)


        add_message(
            chat_id,
            "user",
            text
        )


        urls = extract_urls(text)

        analysis_context = ""


        if urls:

            log_step(
                {
                    "event": "dataset_found",
                    "urls": urls
                }
            )

            try:

                result = analyze_dataset(
                    urls[0],
                    text
                )


                analysis_context = (
                    "\nDataset analysis:\n"
                    +
                    json.dumps(result)
                )


                log_step(
                    {
                        "event": "dataset_analyzed"
                    }
                )


            except Exception as e:

                log_step(
                    {
                        "event": "dataset_error",
                        "error": str(e)
                    }
                )


        prompt = SYSTEM_PROMPT


        for item in history:

            prompt += (
                "\n"
                + item["role"]
                + ": "
                + item["content"]
            )


        prompt += (
            "\nuser: "
            + text
        )


        prompt += analysis_context



        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )


        raw_answer = clean_json(
            response.text
        )


        #
        # Force final JSON format
        #

        try:

            parsed = json.loads(
                raw_answer
            )


            if isinstance(parsed, dict) and "answer" in parsed:

                final_answer = {
                    "answer": parsed["answer"],
                    "log_url": LOG_URL
                }

            else:

                final_answer = {
                    "answer": parsed,
                    "log_url": LOG_URL
                }


        except:

            final_answer = {
                "answer": raw_answer,
                "log_url": LOG_URL
            }



        answer = json.dumps(
            final_answer,
            ensure_ascii=False
        )


        add_message(
            chat_id,
            "assistant",
            answer
        )


        log_step(
            {
                "event": "llm_completed"
            }
        )


        finish_log()


        return answer



    except Exception as e:


        log_step(
            {
                "event": "agent_error",
                "error": str(e)
            }
        )


        finish_log()


        return json.dumps(
            {
                "answer": f"Agent error: {str(e)}",
                "log_url": LOG_URL
            }
        )
