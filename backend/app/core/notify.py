"""Canale di notifica esterno (opzionale, key-gated).

Telegram è il canale personale a costo zero: bot dedicato + chat privata.
- il token NON compare mai nei log (pattern di redazione dedicato);
- nessun contenuto sensibile: solo ticker, stato e frase sintetica;
- fallimento di invio = warning, mai un blocco della pipeline.

Setup (una volta): creare un bot con @BotFather, copiare il token in
DDR_TELEGRAM_BOT_TOKEN, scrivere un messaggio al bot e ricavare la chat id
(api getUpdates) in DDR_TELEGRAM_CHAT_ID, impostare DDR_NOTIFY_CHANNEL=telegram.
"""
from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

API_HOST = "https://api.telegram.org"


def telegram_configured() -> bool:
    s = get_settings()
    return (s.notify_channel == "telegram"
            and bool(s.telegram_bot_token) and bool(s.telegram_chat_id))


def send_notification(title: str, body: str | None = None) -> bool:
    """Invia sul canale configurato. True se inviata, False altrimenti.

    Con canale 'none' le notifiche restano solo in-app (default).
    """
    if not telegram_configured():
        return False
    s = get_settings()
    text = f"📡 {title}" + (f"\n{body}" if body else "")
    try:
        resp = httpx.post(
            f"{API_HOST}/bot{s.telegram_bot_token}/sendMessage",
            json={"chat_id": s.telegram_chat_id, "text": text[:4000]},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 - mai bloccare la pipeline
        logger.warning("Notifica Telegram fallita: %s", str(exc)[:200])
        return False
