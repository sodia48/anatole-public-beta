from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from core.database import add_notification, get_notifications


def seed_market_notifications(profile: str, snapshot: pd.DataFrame) -> None:
    """Ajoute des notifications informatives sans dupliquer excessivement."""
    if snapshot is None or snapshot.empty:
        return
    existing = get_notifications(profile, limit=200)
    recent_titles = set(existing["title"].astype(str).tolist()) if not existing.empty else set()

    movers = snapshot.dropna(subset=["Variation"]).copy()
    if movers.empty:
        return

    top = movers.nlargest(2, "Variation")
    bottom = movers.nsmallest(2, "Variation")
    for _, row in pd.concat([top, bottom]).iterrows():
        change = float(row["Variation"])
        ticker = str(row.get("YahooTicker", row.get("Ticker", "")))
        title = f"Mouvement inhabituel · {ticker} {change:+.2f}%"
        if title in recent_titles or abs(change) < 3:
            continue
        add_notification(
            profile,
            title=title,
            message="Variation importante détectée dans le dernier instantané de marché.",
            category="Mouvement",
            ticker=ticker,
            severity="warning" if change < 0 else "success",
        )


def unread_count(profile: str) -> int:
    frame = get_notifications(profile, unread_only=True, limit=1000)
    return int(len(frame))
