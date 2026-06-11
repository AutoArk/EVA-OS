import uuid

def wrap_rtvi_envelope(message: dict, topic: str = "task-ir-control") -> dict:
    return {
        "label": "rtvi-ai",
        "type": "client-message",
        "id": f"msg-{uuid.uuid4().hex[:8]}",
        "data": {
            "t": topic,
            "d": message
        }
    }

def unwrap_rtvi_envelope(message: dict) -> dict:
    if "label" in message and message.get("label") == "rtvi-ai":
        inner = message.get("data", message)
        if isinstance(inner, dict) and "d" in inner:
            return inner["d"]
        return inner
    return message
