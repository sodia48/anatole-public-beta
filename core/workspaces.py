from __future__ import annotations

import json
from typing import Any

import pandas as pd

from core.database import get_workspaces, save_workspace


DEFAULT_LAYOUTS: dict[str, list[dict[str, Any]]] = {
    "Marché canadien": [
        {"module": "Market Pulse", "visible": True, "size": "large", "order": 1},
        {"module": "Heatmap", "visible": True, "size": "large", "order": 2},
        {"module": "Moteurs du marché", "visible": True, "size": "medium", "order": 3},
        {"module": "Actualités", "visible": True, "size": "medium", "order": 4},
        {"module": "Alertes", "visible": True, "size": "small", "order": 5},
        {"module": "Portefeuille", "visible": False, "size": "medium", "order": 6},
    ],
    "Trading court terme": [
        {"module": "Graphique Focus", "visible": True, "size": "large", "order": 1},
        {"module": "Watchlist", "visible": True, "size": "small", "order": 2},
        {"module": "Screener", "visible": True, "size": "medium", "order": 3},
        {"module": "Alertes", "visible": True, "size": "small", "order": 4},
        {"module": "Actualités", "visible": True, "size": "medium", "order": 5},
    ],
    "Investissement long terme": [
        {"module": "Portefeuille", "visible": True, "size": "large", "order": 1},
        {"module": "Fondamentaux", "visible": True, "size": "medium", "order": 2},
        {"module": "Calendrier", "visible": True, "size": "medium", "order": 3},
        {"module": "Actualités", "visible": True, "size": "medium", "order": 4},
        {"module": "Corrélations", "visible": True, "size": "medium", "order": 5},
    ],
}


def ensure_default_workspaces(profile: str) -> None:
    current = get_workspaces(profile)
    existing = set(current["name"].tolist()) if not current.empty else set()
    for index, (name, layout) in enumerate(DEFAULT_LAYOUTS.items()):
        if name not in existing:
            save_workspace(profile, name, json.dumps(layout, ensure_ascii=False), active=index == 0)


def layout_to_dataframe(layout: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(layout, columns=["module", "visible", "size", "order"])


def dataframe_to_layout(frame: pd.DataFrame) -> list[dict[str, Any]]:
    work = frame.copy()
    work["order"] = pd.to_numeric(work["order"], errors="coerce").fillna(999).astype(int)
    work["visible"] = work["visible"].fillna(False).astype(bool)
    work["size"] = work["size"].where(work["size"].isin(["small", "medium", "large"]), "medium")
    return work.sort_values("order").to_dict(orient="records")


def active_workspace(profile: str) -> tuple[str, list[dict[str, Any]]]:
    ensure_default_workspaces(profile)
    frame = get_workspaces(profile)
    if frame.empty:
        return "Marché canadien", DEFAULT_LAYOUTS["Marché canadien"]
    active = frame[frame["is_active"] == 1]
    row = active.iloc[0] if not active.empty else frame.iloc[0]
    try:
        layout = json.loads(row["layout_json"])
    except Exception:
        layout = DEFAULT_LAYOUTS["Marché canadien"]
    return str(row["name"]), layout
