import os
import re
import sys
import time
import uuid
import subprocess
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import cv2
import yaml
from flask import Flask, Response, render_template, jsonify, request, send_from_directory

app = Flask(__name__)

# ── Global state ──────────────────────────────────────────────────────────────
_camera_processes: dict = {}   # cam_id → Popen
_process_lock = threading.Lock()
_config_lock  = threading.Lock()
_stats_cache: dict = {}
_stats_snap_mtime: float = 0.0


# ── Config helpers ────────────────────────────────────────────────────────────

def load_config() -> dict:
    try:
        with open("config.yaml") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def save_config_file(config: dict):
    with _config_lock:
        with open("config.yaml", "w") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)


def get_cameras(config: dict = None) -> list:
    if config is None:
        config = load_config()
    cameras = config.get("cameras") or []
    if not cameras and (config.get("rtsp_url") or config.get("camera_name")):
        cameras = [{
            "id": "default",
            "rtsp_url":               config.get("rtsp_url", ""),
            "camera_name":            config.get("camera_name", "Camera"),
            "user_condition":         config.get("user_condition", ""),
            "check_interval_seconds": config.get("check_interval_seconds", 2),
            "motion_sensitivity":     config.get("motion_sensitivity", 500),
            "alert_cooldown_seconds": config.get("alert_cooldown_seconds", 60),
        }]
    return cameras


def write_camera_config(cam: dict, global_cfg: dict) -> Path:
    Path("configs").mkdir(exist_ok=True)
    merged = {
        "rtsp_url":               cam["rtsp_url"],
        "camera_name":            cam["camera_name"],
        "user_condition":         cam.get("user_condition", ""),
        "check_interval_seconds": int(cam.get("check_interval_seconds") or 2),
        "motion_sensitivity":     int(cam.get("motion_sensitivity") or 500),
        "alert_cooldown_seconds": int(cam.get("alert_cooldown_seconds") or 60),
        "telegram_bot_token":     cam.get("telegram_bot_token") or global_cfg.get("telegram_bot_token", ""),
        "telegram_chat_id":       cam.get("telegram_chat_id") or global_cfg.get("telegram_chat_id", ""),
    }
    path = Path("configs") / f"{cam['id']}.yaml"
    with open(path, "w") as f:
        yaml.dump(merged, f, default_flow_style=False)
    return path


# ── Process helpers ───────────────────────────────────────────────────────────

def is_cam_running(cam_id: str) -> bool:
    proc = _camera_processes.get(cam_id)
    return proc is not None and proc.poll() is None


def any_running() -> bool:
    return any(is_cam_running(cid) for cid in list(_camera_processes))


def _start_cam(cam: dict, config: dict):
    env = os.environ.copy()
    if config.get("anthropic_api_key"):
        env["ANTHROPIC_API_KEY"] = config["anthropic_api_key"]
    cfg_path = write_camera_config(cam, config)
    log_path = f"alerts_{cam['id']}.log"
    proc = subprocess.Popen(
        [sys.executable, "main.py"],
        env={**env, "CAMI_CONFIG": str(cfg_path), "CAMI_LOG": log_path},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _camera_processes[cam["id"]] = proc
    return proc


# ── Snapshots ─────────────────────────────────────────────────────────────────

def get_snapshots(limit: int = 30, camera_id: str = None, search: str = "") -> list:
    snap_dir = Path("snapshots")
    if not snap_dir.exists():
        return []
    files = sorted(snap_dir.glob("*.jpg"), key=os.path.getmtime, reverse=True)
    if camera_id and camera_id != "all":
        cams = get_cameras()
        cam  = next((c for c in cams if c["id"] == camera_id), None)
        if cam:
            prefix = cam["camera_name"].replace(" ", "_")
            files  = [f for f in files if f.name.startswith(prefix)]
    if search:
        files = [f for f in files if search.lower() in f.name.lower()]
    return [
        {
            "filename": f.name,
            "datetime": datetime.fromtimestamp(f.stat().st_mtime).strftime("%b %d, %H:%M:%S"),
        }
        for f in files[:limit]
    ]


def snapshot_count() -> int:
    snap_dir = Path("snapshots")
    return len(list(snap_dir.glob("*.jpg"))) if snap_dir.exists() else 0


# ── Logs ──────────────────────────────────────────────────────────────────────

def get_logs(limit: int = 120, level: str = "all", search: str = "", camera_id: str = "all") -> list:
    if camera_id != "all":
        log_files = [Path(f"alerts_{camera_id}.log")]
        if not log_files[0].exists():
            log_files = [Path("alerts.log")]
    else:
        log_files = [Path("alerts.log")] + list(Path(".").glob("alerts_*.log"))

    lines: list = []
    for lf in log_files:
        if lf.exists():
            with open(lf) as f:
                lines.extend(ln.rstrip() for ln in f if ln.strip())
    lines.sort()  # timestamp prefix gives chronological order

    if level == "alert":
        lines = [l for l in lines if re.search(r'ALERT|alert sent|Match:', l, re.I)]
    elif level == "motion":
        lines = [l for l in lines if re.search(r'Motion detected', l, re.I)]
    elif level == "error":
        lines = [l for l in lines if re.search(r'\[ERROR\]|\[WARNING\]|Failed|error', l, re.I)]

    if search:
        lines = [l for l in lines if search.lower() in l.lower()]

    return lines[-limit:]


# ── Stats ─────────────────────────────────────────────────────────────────────

_DATE_RE = re.compile(r'_(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})_')


def get_stats() -> dict:
    global _stats_cache, _stats_snap_mtime
    snap_dir = Path("snapshots")
    try:
        cur_mtime = snap_dir.stat().st_mtime if snap_dir.exists() else 0
    except OSError:
        cur_mtime = 0
    if _stats_cache and cur_mtime == _stats_snap_mtime:
        return _stats_cache

    snaps  = list(snap_dir.glob("*.jpg")) if snap_dir.exists() else []
    config = load_config()
    cams   = get_cameras(config)
    cam_prefixes = {c["camera_name"].replace(" ", "_"): c["camera_name"] for c in cams}

    today    = datetime.now().date()
    day_keys = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    per_day  = {d.isoformat(): 0 for d in day_keys}
    per_cam: dict = {}
    per_hour = {h: 0 for h in range(24)}

    for f in snaps:
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        dk    = mtime.date().isoformat()
        if dk in per_day:
            per_day[dk] += 1
        per_hour[mtime.hour] += 1
        m = _DATE_RE.search(f.name)
        if m:
            raw     = f.name[:m.start()]
            display = cam_prefixes.get(raw, raw.replace("_", " "))
        else:
            display = "Unknown"
        per_cam[display] = per_cam.get(display, 0) + 1

    result = {
        "per_day":    {"labels": [datetime.fromisoformat(d).strftime("%b %d") for d in per_day], "data": list(per_day.values())},
        "per_camera": {"labels": list(per_cam.keys()),  "data": list(per_cam.values())},
        "per_hour":   {"labels": [f"{h:02d}:00" for h in range(24)], "data": [per_hour[h] for h in range(24)]},
        "total":      len(snaps),
    }
    _stats_cache     = result
    _stats_snap_mtime = cur_mtime
    return result


# ── MJPEG stream ──────────────────────────────────────────────────────────────

def _generate_frames(rtsp_url: str):
    if not rtsp_url:
        return
    cap = cv2.VideoCapture(rtsp_url)
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                cap.release()
                time.sleep(2)
                cap = cv2.VideoCapture(rtsp_url)
                continue
            frame = cv2.resize(frame, (640, 360))
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
            time.sleep(0.05)
    finally:
        cap.release()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    config  = load_config()
    cameras = get_cameras(config)
    return render_template(
        "index.html",
        config=config,
        cameras=cameras,
        snapshots=get_snapshots(30),
        logs=get_logs(80),
        running_map={c["id"]: is_cam_running(c["id"]) for c in cameras},
        total_alerts=snapshot_count(),
    )


@app.route("/video_feed", defaults={"cam_id": None})
@app.route("/video_feed/<cam_id>")
def video_feed(cam_id):
    config  = load_config()
    cameras = get_cameras(config)
    if cam_id:
        cam = next((c for c in cameras if c["id"] == cam_id), None)
        rtsp_url = cam["rtsp_url"] if cam else ""
    else:
        rtsp_url = cameras[0]["rtsp_url"] if cameras else ""
    return Response(_generate_frames(rtsp_url), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/snapshots/<path:filename>")
def serve_snapshot(filename):
    return send_from_directory("snapshots", filename)


@app.route("/api/snapshot/<path:filename>", methods=["DELETE"])
def delete_snapshot(filename):
    if "/" in filename or ".." in filename:
        return jsonify({"status": "invalid"}), 400
    p = Path("snapshots") / filename
    if p.exists():
        p.unlink()
        return jsonify({"status": "deleted"})
    return jsonify({"status": "not_found"}), 404


@app.route("/api/snapshots/bulk_delete", methods=["POST"])
def bulk_delete():
    fns = (request.get_json() or {}).get("filenames", [])
    deleted, errors = [], []
    for fn in fns:
        if "/" in fn or ".." in fn:
            errors.append(fn); continue
        p = Path("snapshots") / fn
        if p.exists():
            p.unlink(); deleted.append(fn)
        else:
            errors.append(fn)
    return jsonify({"deleted": deleted, "errors": errors})


@app.route("/api/status")
def api_status():
    config  = load_config()
    cameras = get_cameras(config)
    return jsonify({
        "running": any_running(),
        "cameras": [{"id": c["id"], "name": c["camera_name"], "running": is_cam_running(c["id"])} for c in cameras],
        "total_alerts": snapshot_count(),
        "recent_snapshots": get_snapshots(10),
        "logs": get_logs(80),
    })


@app.route("/api/logs")
def api_logs():
    return jsonify({"logs": get_logs(
        limit=int(request.args.get("limit", 150)),
        level=request.args.get("level", "all"),
        search=request.args.get("search", ""),
        camera_id=request.args.get("camera", "all"),
    )})


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


@app.route("/api/config")
def api_config_get():
    config = load_config()
    safe   = {k: v for k, v in config.items() if k != "anthropic_api_key"}
    safe["anthropic_api_key_set"] = bool(config.get("anthropic_api_key"))
    return jsonify(safe)


@app.route("/api/config/save", methods=["POST"])
def api_config_save():
    data   = request.get_json() or {}
    config = load_config()

    for field in ("telegram_bot_token", "telegram_chat_id"):
        if data.get(field):
            config[field] = data[field]
    if data.get("anthropic_api_key"):
        config["anthropic_api_key"] = data["anthropic_api_key"]

    if "cameras" in data:
        cleaned = []
        for cam in data["cameras"]:
            cleaned.append({
                "id":                     cam.get("id") or f"cam_{uuid.uuid4().hex[:8]}",
                "rtsp_url":               cam.get("rtsp_url", ""),
                "camera_name":            cam.get("camera_name", "Camera"),
                "user_condition":         cam.get("user_condition", ""),
                "check_interval_seconds": int(cam.get("check_interval_seconds") or 2),
                "motion_sensitivity":     int(cam.get("motion_sensitivity") or 500),
                "alert_cooldown_seconds": int(cam.get("alert_cooldown_seconds") or 60),
            })
        config["cameras"] = cleaned
        for k in ("rtsp_url", "camera_name", "user_condition",
                  "check_interval_seconds", "motion_sensitivity", "alert_cooldown_seconds"):
            config.pop(k, None)

    save_config_file(config)
    return jsonify({"status": "saved"})


@app.route("/api/monitor/start", methods=["POST"])
def api_start_all():
    config  = load_config()
    cameras = get_cameras(config)
    started = []
    with _process_lock:
        for cam in cameras:
            if not is_cam_running(cam["id"]):
                _start_cam(cam, config)
                started.append(cam["id"])
    return jsonify({"status": "started", "cameras": started})


@app.route("/api/monitor/stop", methods=["POST"])
def api_stop_all():
    stopped = []
    with _process_lock:
        for cam_id, proc in list(_camera_processes.items()):
            if proc.poll() is None:
                proc.terminate()
                try:    proc.wait(timeout=5)
                except subprocess.TimeoutExpired: proc.kill()
                stopped.append(cam_id)
    return jsonify({"status": "stopped", "cameras": stopped})


@app.route("/api/monitor/<cam_id>/start", methods=["POST"])
def api_start_camera(cam_id):
    if is_cam_running(cam_id):
        return jsonify({"status": "already_running"})
    config  = load_config()
    cameras = get_cameras(config)
    cam     = next((c for c in cameras if c["id"] == cam_id), None)
    if not cam:
        return jsonify({"status": "not_found"}), 404
    with _process_lock:
        _start_cam(cam, config)
    return jsonify({"status": "started"})


@app.route("/api/monitor/<cam_id>/stop", methods=["POST"])
def api_stop_camera(cam_id):
    proc = _camera_processes.get(cam_id)
    if not proc or proc.poll() is not None:
        return jsonify({"status": "not_running"})
    proc.terminate()
    try:    proc.wait(timeout=5)
    except subprocess.TimeoutExpired: proc.kill()
    return jsonify({"status": "stopped"})


@app.route("/api/telegram/test", methods=["POST"])
def api_telegram_test():
    import asyncio
    config = load_config()
    token  = config.get("telegram_bot_token", "")
    chat_id = config.get("telegram_chat_id", "")
    if not token or not chat_id or "your-bot" in token:
        return jsonify({"status": "error", "message": "Telegram not configured"})
    try:
        from telegram import Bot
        async def _send():
            await Bot(token=token).send_message(chat_id=chat_id, text="✅ camIA — Telegram connection test successful!")
        asyncio.run(_send())
        return jsonify({"status": "ok", "message": "Test message sent!"})
    except Exception as ex:
        return jsonify({"status": "error", "message": str(ex)})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("camIA Dashboard → http://localhost:6789")
    app.run(host="0.0.0.0", port=6789, debug=False, threaded=True)
