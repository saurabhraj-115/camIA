import logging

import telegram

logger = logging.getLogger(__name__)


async def send_alert(
    bot_token: str,
    chat_id: str,
    camera_name: str,
    reason: str,
    timestamp: str,
    snapshot_path: str,
):
    bot = telegram.Bot(token=bot_token)
    message = f"🚨 Alert — {camera_name}\n{reason}\nTime: {timestamp}"

    async with bot:
        with open(snapshot_path, "rb") as photo:
            await bot.send_photo(chat_id=chat_id, photo=photo, caption=message)

    logger.info("Alert sent for %s at %s", camera_name, timestamp)
