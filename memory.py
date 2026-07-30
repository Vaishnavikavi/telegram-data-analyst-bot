import os
import json


MEMORY_FILE = "memory.json"


def load_memory():

    if not os.path.exists(MEMORY_FILE):
        return {}

    try:

        with open(
            MEMORY_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except:

        return {}



def save_memory(memory):

    with open(
        MEMORY_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            memory,
            f,
            indent=2
        )



def get_history(chat_id):

    memory = load_memory()

    return memory.get(
        str(chat_id),
        []
    )



def add_message(
        chat_id,
        role,
        content
):

    memory = load_memory()


    key = str(chat_id)


    if key not in memory:

        memory[key] = []


    memory[key].append(
        {
            "role": role,
            "content": content
        }
    )


    #
    # Keep only last 10 messages
    #

    memory[key] = memory[key][-10:]


    save_memory(
        memory
    )
