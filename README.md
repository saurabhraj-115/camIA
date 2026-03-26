# camIA

Intelligent CCTV monitoring with a web dashboard. Watches your camera streams, detects motion locally with OpenCV, sends frames to Claude Vision when motion is detected, and fires a Telegram alert with a snapshot when the scene matches a condition you define in plain English.

## How it works

```
RTSP Stream → OpenCV (MOG2 motion filter, free & local)
  → [motion above threshold] → Claude Vision API
    → Claude checks frame against your condition
      → [match] → save snapshot + send Telegram alert
```

Claude is only called when motion is detected — keeping API costs minimal.

## Features

- **Web dashboard** — live MJPEG feed, alert gallery, real-time log viewer
- **Multi-camera** — add and monitor unlimited cameras, each with its own condition
- **Stats** — charts for alerts per day / per camera / per hour
- **Log filtering** — filter by level (alerts / motion / errors) and text search
- **Alert management** — search, preview, and delete snapshots from the UI
- **Settings UI** — configure cameras, API key, and Telegram without editing files
- **Deploy to Fly.io** — run the dashboard remotely, accessible from anywhere

## Quick start (local)

```bash
git clone https://github.com/saurabhraj-115/camIA.git
cd camIA
pip install -r requirements.txt
cp config.example.yaml config.yaml   # then edit, or use the web UI
python3 web_ui.py
```

Open **http://localhost:6789**, go to **⚙ Settings**, and fill in your camera and API details.

To run the monitor headlessly (no web UI):
```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 main.py
```

## Configuration

The easiest way is through the web UI Settings tab. To configure manually, edit `config.yaml`:

```yaml
anthropic_api_key: "sk-ant-..."

telegram_bot_token: "1234567890:ABCdef..."
telegram_chat_id:   "123456789"

cameras:
  - id: cam_front
    rtsp_url:               "rtsp://user:pass@192.168.1.100:554/stream"
    camera_name:            "Front Door"
    user_condition:         "alert me when a person enters through the front door"
    check_interval_seconds: 2
    motion_sensitivity:     500
    alert_cooldown_seconds: 60
  - id: cam_back
    rtsp_url:               "rtsp://user:pass@192.168.1.101:554/stream"
    camera_name:            "Back Garden"
    user_condition:         "alert me when motion is detected near the shed"
    check_interval_seconds: 3
    motion_sensitivity:     300
    alert_cooldown_seconds: 90
```

### Configuration reference

| Field | Description | Default |
|---|---|---|
| `anthropic_api_key` | Anthropic API key (or set `ANTHROPIC_API_KEY` env var) | — |
| `telegram_bot_token` | Token from [@BotFather](https://t.me/BotFather) | — |
| `telegram_chat_id` | Your personal or group chat ID | — |
| `cameras[].rtsp_url` | Full RTSP URL of the camera stream | — |
| `cameras[].camera_name` | Label for alerts and snapshot filenames | — |
| `cameras[].user_condition` | Plain English description of what to alert on | — |
| `cameras[].check_interval_seconds` | Seconds between frame reads | `2` |
| `cameras[].motion_sensitivity` | Minimum pixel contour area to count as motion | `500` |
| `cameras[].alert_cooldown_seconds` | Minimum seconds between consecutive alerts | `60` |

### Writing a good condition

```yaml
# good — specific, context-aware
user_condition: "alert me if a person is visible near the gate after 8pm"

# too vague
user_condition: "something suspicious"
```

## Telegram setup

1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token
2. Send `/start` to your new bot
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in your browser
4. Find `"chat":{"id": YOUR_ID}` — that number is your Chat ID
5. Paste both into the Settings UI and click **Test Connection**

> Note: Chat IDs from `@userinfobot` are user IDs, not bot chat IDs. Use the `getUpdates` method above.

## Deploy to Fly.io

The web dashboard can be deployed to Fly.io for remote access from anywhere.

> **Note:** Live MJPEG feeds require the RTSP URLs to be reachable from Fly's network. If your cameras are on a local network, the feed won't stream — but alerts, snapshots, and configuration all work.

### First deploy

```bash
# Install flyctl if needed: https://fly.io/docs/hands-on/install-flyctl/
fly auth login
fly apps create camia          # or choose a unique name, update fly.toml
fly volumes create camia_data --region sin --size 1
fly secrets set ANTHROPIC_API_KEY=sk-ant-... \
               TELEGRAM_BOT_TOKEN=... \
               TELEGRAM_CHAT_ID=...
fly deploy
```

### Subsequent deploys

```bash
fly deploy
```

### Update secrets

```bash
fly secrets set ANTHROPIC_API_KEY=sk-ant-new-key
```

After first deploy, open the Fly URL, go to **⚙ Settings**, add your cameras, and start monitoring.

## File structure

```
camIA/
├── main.py              # headless monitor loop (one instance per camera)
├── detector.py          # OpenCV MOG2 motion detection
├── vision.py            # Claude Vision API
├── notifier.py          # Telegram alerts
├── web_ui.py            # Flask dashboard + process manager
├── templates/
│   └── index.html       # dashboard UI
├── config.example.yaml  # template — copy to config.yaml
├── Dockerfile
├── fly.toml
├── entrypoint.sh
├── requirements.txt
└── snapshots/           # alert images (auto-created, gitignored)
```

Per-camera logs are written to `alerts_{camera_id}.log`. The web dashboard merges and displays all logs.
