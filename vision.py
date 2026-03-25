import base64
import json
import logging

import anthropic
import cv2

logger = logging.getLogger(__name__)


def frame_to_base64(frame) -> str:
    _, buffer = cv2.imencode(".jpg", frame)
    return base64.standard_b64encode(buffer).decode("utf-8")


def check_frame(frame, user_condition: str, camera_name: str, timestamp: str) -> dict:
    """
    Sends a frame to Claude Vision and checks if it matches the user condition.
    Returns {"match": bool, "reason": str}
    """
    client = anthropic.Anthropic()
    image_data = frame_to_base64(frame)

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=256,
        system='You are a security camera analyst. Reply only with JSON.',
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f'Does this frame match: {user_condition}?\n'
                            f'Time: {timestamp}, Camera: {camera_name}\n'
                            'Reply: {"match": true/false, "reason": "one sentence"}'
                        ),
                    },
                ],
            }
        ],
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        result = json.loads(raw)
        return {"match": bool(result.get("match", False)), "reason": result.get("reason", "")}
    except json.JSONDecodeError:
        logger.warning("Claude returned non-JSON response: %s", raw)
        return {"match": False, "reason": raw}
