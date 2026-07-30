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
    "gemini-2.5-flash"
)


SYSTEM_PROMPT = """

You are a data analyst AI agent.

Your job is to answer data analysis questions.

Rules:

1. The user may provide a dataset URL.
2. If a dataset URL is provided, analyze the data.
3. Use Python/pandas calculations whenever possible.
4. Do not guess numerical answers.
5. The final answer must be ONLY one JSON object.

The JSON format must be:

{
 "answer": <answer requested by user>,
 "log_url": "<public log url>"
}

Never add markdown.
Never add explanations outside JSON.

"""


def extract_urls(text):

    return re.findall(
        r"https?://[^\s]+",
        text
    )



def clean_json(text):

    """
    Remove markdown if Gemini adds it.
    """

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
                    "\nDataset analysis result:\n"
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


        answer = clean_json(
            response.text
        )



        #
        # If Gemini forgot JSON,
        # wrap it safely
        #

        try:

            json.loads(answer)


        except:

            answer = json.dumps(
                {
                    "answer": answer,
                    "log_url":
                    "/logs/run.jsonl"
                }
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
                "answer":
                    f"Agent error: {str(e)}",
                "log_url":
                    "/logs/run.jsonl"
            }
        )
