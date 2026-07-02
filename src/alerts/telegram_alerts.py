from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv


class TelegramAlerter:
    """Small Telegram sender for BTCRadar alerts.

    Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from .env/environment.
    If not configured, send() becomes a safe no-op.
    """

    def __init__(self, cfg: dict | None = None):
        load_dotenv()
        cfg = cfg or {}
        tg_cfg = cfg.get('telegram', {}) if isinstance(cfg, dict) else {}

        self.token = os.getenv('TELEGRAM_BOT_TOKEN') or tg_cfg.get('bot_token') or ''
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID') or tg_cfg.get('chat_id') or ''
        self.timeout_sec = int(tg_cfg.get('timeout_sec', 10))
        self.enabled = bool(self.token and self.chat_id)

    def send(self, text: str, *, parse_mode: str | None = None) -> bool:
        if not self.enabled:
            return False

        url = f'https://api.telegram.org/bot{self.token}/sendMessage'
        payload: dict[str, Any] = {
            'chat_id': self.chat_id,
            'text': text,
            'disable_web_page_preview': True,
        }
        if parse_mode:
            payload['parse_mode'] = parse_mode

        try:
            r = requests.post(url, json=payload, timeout=self.timeout_sec)
            r.raise_for_status()
            return True
        except Exception:
            return False
