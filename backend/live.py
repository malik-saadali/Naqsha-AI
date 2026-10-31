"""Live push to dashboards (WebSocket) and to phones (Telegram)."""
import json

import httpx
from fastapi import WebSocket

from . import config


class Hub:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.add(ws)

    def drop(self, ws: WebSocket):
        self.clients.discard(ws)

    async def send(self, kind: str, data):
        msg = json.dumps({"type": kind, "data": data}, ensure_ascii=False, default=str)
        for ws in list(self.clients):
            try:
                await ws.send_text(msg)
            except Exception:
                self.drop(ws)


hub = Hub()


async def telegram(chat_id, text: str) -> bool:
    # Telegram chat ids are numbers (groups are negative); skip demo/test ids without a network call
    if not config.TELEGRAM_BOT_TOKEN or not str(chat_id or "").lstrip("-").isdigit():
        return False
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=6)) as cl:
            r = await cl.post(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
                              json={"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True})
        return r.status_code == 200
    except Exception:
        return False
