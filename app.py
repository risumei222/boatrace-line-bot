import base64
import hashlib
import hmac
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict
from urllib.request import Request, urlopen

from flask import Flask, abort, request
from bot_controller import parse_race_input, run_mode_2_post_exhibition, run_morning_job

app = Flask(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("boatrace-line-bot")

CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "").strip()
EXECUTOR = ThreadPoolExecutor(max_workers=int(os.getenv("BOT_MAX_WORKERS", "4")))

def verify_signature(raw_body: bytes, signature: str) -> bool:
    if not CHANNEL_SECRET or not signature:
        return False
    digest = hmac.new(CHANNEL_SECRET.encode("utf-8"), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature)

def reply_line_message(reply_token: str, message: str) -> bool:
    """手動で『大村10』と送ってきた人へ返信する用の機能"""
    if not CHANNEL_ACCESS_TOKEN or not reply_token:
        return False
    message = str(message)[:4900]
    payload = json.dumps({"replyToken": reply_token, "messages": [{"type": "text", "text": message}]}, ensure_ascii=False).encode("utf-8")
    req = Request(
        "https://api.line.me/v2/bot/message/reply",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=12) as response:
            return 200 <= response.status < 300
    except Exception:
        logger.exception("LINE reply API failed")
        return False

def broadcast_line_message(message: str) -> bool:
    """朝のタイマー用：ボットからあなたへ一方的に通知を送る機能"""
    if not CHANNEL_ACCESS_TOKEN:
        return False
    message = str(message)[:4900]
    payload = json.dumps({"messages": [{"type": "text", "text": message}]}, ensure_ascii=False).encode("utf-8")
    req = Request(
        "https://api.line.me/v2/bot/message/broadcast",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=12) as response:
            return 200 <= response.status < 300
    except Exception:
        logger.exception("LINE broadcast API failed")
        return False

def _process_event(user_text: str, reply_token: str) -> None:
    try:
        response = run_mode_2_post_exhibition(user_text)
    except Exception:
        logger.exception("race processing failed")
        response = "ERROR: 判定処理に失敗しました。時間をおいて再試行してください。"
    reply_line_message(reply_token, response)

def _process_morning_job() -> None:
    try:
        response = run_morning_job()
        broadcast_line_message(response)
    except Exception:
        logger.exception("morning job failed")

@app.post("/callback")
def callback():
    raw_body = request.get_data(cache=False, as_text=False)
    signature = request.headers.get("X-Line-Signature", "")
    if not verify_signature(raw_body, signature):
        abort(400)
    try:
        payload: Dict[str, Any] = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        abort(400)

    for event in payload.get("events", []):
        if event.get("type") != "message" or event.get("message", {}).get("type") != "text":
            continue
        user_text = str(event.get("message", {}).get("text", "")).strip()
        reply_token = event.get("replyToken")
        
        jcd, rno = parse_race_input(user_text)
        if jcd and rno and reply_token:
            try:
                EXECUTOR.submit(_process_event, user_text, reply_token)
            except RuntimeError:
                logger.exception("background executor unavailable")
    return "OK", 200

@app.get("/morning_job")
def morning_job_endpoint():
    """朝8時に外部タイマーから呼び出される専用の窓口"""
    try:
        EXECUTOR.submit(_process_morning_job)
    except RuntimeError:
        logger.exception("background executor unavailable")
        return "Error", 500
    return "Morning Job Started", 200

@app.get("/")
def health():
    return "Boatrace LINE Bot Webhook Server Running.", 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
