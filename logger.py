import json
import os
import time

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "run.jsonl")

os.makedirs(LOG_DIR, exist_ok=True)


def start_log(chat_id):
    """
    Start a new log for this run.
    """
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "event": "start",
                    "chat_id": chat_id,
                    "timestamp": time.time(),
                }
            )
            + "\n"
        )


def log_step(data):
    """
    Append one JSON object to the log.
    """
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(data) + "\n")


def finish_log():
    """
    Finish the log.
    """
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "event": "finish",
                    "timestamp": time.time(),
                }
            )
            + "\n"
        )
