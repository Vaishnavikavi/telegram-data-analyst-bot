from collections import defaultdict

# Stores conversation history for each Telegram chat
# Key = chat_id
# Value = list of {"role": "...", "content": "..."}
conversation_history = defaultdict(list)

# Keep only the last few messages to avoid huge prompts
MAX_HISTORY = 10


def get_history(chat_id):
    """
    Return the conversation history for this user.
    """
    return conversation_history[chat_id]


def add_message(chat_id, role, content):
    """
    Add a message to the conversation history.
    """
    conversation_history[chat_id].append(
        {
            "role": role,
            "content": content,
        }
    )

    # Keep only the most recent messages
    if len(conversation_history[chat_id]) > MAX_HISTORY:
        conversation_history[chat_id] = conversation_history[chat_id][-MAX_HISTORY:]


def clear_history(chat_id):
    """
    Clear the conversation for one user.
    """
    conversation_history[chat_id] = []
