# camIA

A lightweight CCTV activity detection and alert system. Monitors an RTSP camera stream, detects motion, uses Claude Vision to check if the motion matches a condition you define in plain English, and sends a Telegram alert with a snapshot when matched.

## How it works

```
RTSP Stream → OpenCV frame capture
  → MOG2 motion filter (local, free)
    → [motion detected] → Claude Vision API
      → Claude checks frame against your condition
        → [match] → save snapshot + send Telegram alert
```

Claude only gets called when motion is detected above the sensitivity threshold — keeping API costs low.

## Requirements

- Python 3.11+
- An RTSP camera stream
- Anthropic API key
- A Telegram bot token and chat ID

## Setup

```bash
git clone https://github.com/your-username/camIA.git
cd camIA
pip install -r requirements.txt
```

Set your Anthropic API key:
```bash
export ANTHROPIC_API_KEY=your-key-here
```

Edit `config.yaml` with your camera and Telegram details:
```yaml
rtsp_url: "rtsp://username:password@192.168.1.100:554/stream"
camera_name: "Front Door"
telegram_bot_token: "your-bot-token"
telegram_chat_id: "your-chat-id"
check_interval_seconds: 2
motion_sensitivity: 500
user_condition: "alert me when a person enters through the back door after dark"
alert_cooldown_seconds: 60
```

## Run

```bash
python main.py
```

## Configuration

| Field | Description | Default |
|-------|-------------|---------|
| `rtsp_url` | Full RTSP URL of your camera | — |
| `camera_name` | Label used in alerts and snapshot filenames | — |
| `telegram_bot_token` | Token from [@BotFather](https://t.me/BotFather) | — |
| `telegram_chat_id` | Your Telegram chat or group ID | — |
| `check_interval_seconds` | Seconds between frame reads | `2` |
| `motion_sensitivity` | Min pixel contour area to count as motion | `500` |
| `user_condition` | Plain English description of what to alert on | — |
| `alert_cooldown_seconds` | Minimum seconds between consecutive alerts | `60` |

### Writing a good condition

The `user_condition` field is sent directly to Claude as a natural language prompt. Be specific:

```yaml
# good
user_condition: "alert me if a person is visible near the gate after 8pm"

# too vague
user_condition: "something suspicious"
```

## File structure

```
camIA/
├── main.py          # main loop
├── detector.py      # MOG2 motion detection
├── vision.py        # Claude Vision API call
├── notifier.py      # Telegram alert delivery
├── config.yaml      # your configuration
├── requirements.txt
└── snapshots/       # saved alert images (auto-created)
```

Alerts are also logged to `alerts.log` with timestamps and Claude's reasons.

## Getting a Telegram bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the token into `config.yaml`
4. To get your chat ID, message [@userinfobot](https://t.me/userinfobot)

## Out of scope for MVP

- Multi-camera support
- Web UI
- Video clip saving (snapshots only)
- WhatsApp notifications
