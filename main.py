import asyncio
import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import cv2
import yaml

from detector import MotionDetector
from notifier import send_alert
from vision import check_frame

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("alerts.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def get_timestamp() -> str:
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S IST")


def save_snapshot(frame, camera_name: str, timestamp: str) -> str:
    os.makedirs("snapshots", exist_ok=True)
    safe_ts = timestamp.replace(":", "-").replace(" ", "_")
    safe_name = camera_name.replace(" ", "_")
    path = f"snapshots/{safe_name}_{safe_ts}.jpg"
    cv2.imwrite(path, frame)
    return path


def main():
    config = load_config()

    rtsp_url = config["rtsp_url"]
    camera_name = config["camera_name"]
    user_condition = config["user_condition"]
    check_interval = config.get("check_interval_seconds", 2)
    sensitivity = config.get("motion_sensitivity", 500)
    cooldown = config.get("alert_cooldown_seconds", 60)
    bot_token = config["telegram_bot_token"]
    chat_id = config["telegram_chat_id"]

    detector = MotionDetector(sensitivity=sensitivity)
    cap = cv2.VideoCapture(rtsp_url)

    if not cap.isOpened():
        logger.error("Failed to open RTSP stream: %s", rtsp_url)
        return

    logger.info("camIA started — watching '%s'", camera_name)
    logger.info("Condition: %s", user_condition)

    last_alert_time = 0.0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.warning("Failed to read frame — retrying in %ss", check_interval)
                time.sleep(check_interval)
                cap.release()
                cap = cv2.VideoCapture(rtsp_url)
                continue

            motion_detected, _ = detector.detect(frame)

            if not motion_detected:
                time.sleep(check_interval)
                continue

            now = time.time()
            if now - last_alert_time < cooldown:
                time.sleep(check_interval)
                continue

            timestamp = get_timestamp()
            logger.info("Motion detected at %s — checking with Claude Vision", timestamp)

            result = check_frame(frame, user_condition, camera_name, timestamp)

            if result["match"]:
                logger.info("Match: %s", result["reason"])
                snapshot_path = save_snapshot(frame, camera_name, timestamp)
                asyncio.run(
                    send_alert(bot_token, chat_id, camera_name, result["reason"], timestamp, snapshot_path)
                )
                last_alert_time = now
            else:
                logger.info("No match: %s", result["reason"])

            time.sleep(check_interval)

    except KeyboardInterrupt:
        logger.info("Shutting down.")
    finally:
        cap.release()


if __name__ == "__main__":
    main()
