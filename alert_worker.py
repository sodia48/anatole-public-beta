from __future__ import annotations

import argparse
import os
import smtplib
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import yfinance as yf

from core.analytics import add_indicators, evaluate_alert
from core.database import (
    get_alerts,
    init_db,
    record_alert_trigger,
    update_alert_value,
)
from core.utils import extract_ticker_frame

ROOT = Path(__file__).resolve().parent
SECRETS_FILE = ROOT / ".streamlit" / "secrets.toml"


def load_settings() -> dict[str, str]:
    settings: dict[str, str] = {}
    if SECRETS_FILE.exists():
        try:
            import tomllib

            with SECRETS_FILE.open("rb") as handle:
                raw = tomllib.load(handle)
            settings.update({str(key): str(value) for key, value in raw.items() if value is not None})
        except Exception as exc:
            print(f"Impossible de lire {SECRETS_FILE}: {exc}")
    for key in [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_USE_TLS",
        "ALERT_EMAIL_FROM",
        "ALERT_EMAIL_TO",
    ]:
        if os.getenv(key):
            settings[key] = os.environ[key]
    return settings


def send_telegram(message: str, settings: dict[str, str]) -> bool:
    token = settings.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = settings.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message},
        timeout=20,
    )
    response.raise_for_status()
    return True


def send_email(message: str, settings: dict[str, str]) -> bool:
    host = settings.get("SMTP_HOST", "")
    username = settings.get("SMTP_USERNAME", "")
    password = settings.get("SMTP_PASSWORD", "")
    recipient = settings.get("ALERT_EMAIL_TO", "")
    sender = settings.get("ALERT_EMAIL_FROM", username)
    port = int(settings.get("SMTP_PORT", "587"))
    use_tls = settings.get("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes", "oui"}
    if not all([host, username, password, recipient, sender]):
        return False

    email = EmailMessage()
    email["Subject"] = "Alerte Anatole"
    email["From"] = sender
    email["To"] = recipient
    email.set_content(message)
    with smtplib.SMTP(host, port, timeout=30) as server:
        if use_tls:
            server.starttls()
        server.login(username, password)
        server.send_message(email)
    return True


def build_features(tickers: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    if not tickers:
        return {}
    data = yf.download(
        list(tickers),
        period="1y",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )
    result: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        frame = extract_ticker_frame(data, ticker)
        enriched = add_indicators(frame)
        if enriched.empty:
            continue
        last = enriched.dropna(subset=["Close"]).iloc[-1]
        previous_close = enriched["Close"].dropna().iloc[-2] if len(enriched["Close"].dropna()) >= 2 else None
        current = float(last["Close"])
        result[ticker] = {
            "YahooTicker": ticker,
            "Prix": current,
            "Variation": ((current / previous_close) - 1) * 100 if previous_close else None,
            "RSI14": last.get("RSI14"),
            "VolumeRelatif": last.get("VolumeRelatif"),
            "SMA20": last.get("SMA20"),
            "SMA50": last.get("SMA50"),
        }
    return result


def cooldown_elapsed(last_triggered: str | None, cooldown_minutes: int) -> bool:
    if not last_triggered:
        return True
    try:
        return datetime.utcnow() - datetime.fromisoformat(last_triggered) >= timedelta(minutes=cooldown_minutes)
    except Exception:
        return True


def process_once(settings: dict[str, str]) -> int:
    alerts = get_alerts(active_only=True)
    if alerts.empty:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Aucune alerte active.")
        return 0
    features = build_features(tuple(sorted(alerts["ticker"].unique().tolist())))
    triggered_count = 0

    for _, alert in alerts.iterrows():
        feature = features.get(alert["ticker"])
        if not feature:
            print(f"Données indisponibles pour {alert['ticker']}")
            continue
        triggered, observed, message = evaluate_alert(alert, feature)
        update_alert_value(int(alert["id"]), observed)
        if not triggered or not cooldown_elapsed(alert.get("last_triggered_at"), int(alert["cooldown_minutes"])):
            continue

        channel = str(alert.get("channel", "app"))
        notification_status = "enregistrée dans l'application"
        try:
            if channel == "telegram":
                notification_status = "envoyée sur Telegram" if send_telegram(message, settings) else "Telegram non configuré; enregistrée seulement"
            elif channel == "email":
                notification_status = "envoyée par courriel" if send_email(message, settings) else "SMTP non configuré; enregistrée seulement"
        except Exception as exc:
            notification_status = f"notification externe échouée ({type(exc).__name__}: {exc})"

        full_message = f"{message} · {notification_status}"
        record_alert_trigger(
            int(alert["id"]),
            str(alert["profile"]),
            str(alert["ticker"]),
            full_message,
            observed,
        )
        triggered_count += 1
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {full_message}")
    return triggered_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker d'alertes TSX 60 Ultimate")
    parser.add_argument("--interval", type=int, default=60, help="Intervalle entre vérifications, en secondes")
    parser.add_argument("--once", action="store_true", help="Effectuer une seule vérification")
    args = parser.parse_args()

    init_db()
    settings = load_settings()
    while True:
        try:
            process_once(settings)
        except KeyboardInterrupt:
            print("Worker arrêté.")
            break
        except Exception as exc:
            print(f"Erreur du worker: {type(exc).__name__}: {exc}")
        if args.once:
            break
        time.sleep(max(args.interval, 15))


if __name__ == "__main__":
    main()
