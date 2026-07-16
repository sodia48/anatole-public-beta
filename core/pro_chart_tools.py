from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go


PRO_DRAW_BUTTONS = [
    "drawline",
    "drawopenpath",
    "drawclosedpath",
    "drawrect",
    "drawcircle",
    "eraseshape",
]


MODEL_LABELS = {
    "support_resistance": "Zones support / résistance",
    "trend_channel": "Canal de tendance",
    "fibonacci": "Retracement Fibonacci",
    "breakout_box": "Zone de cassure / range",
    "analyst_target": "Objectif analystes",
}


def _num(value: Any, default: float = np.nan) -> float:
    try:
        number = float(value)
        return number if np.isfinite(number) else default
    except Exception:
        return default


def _money(value: Any, currency: str = "CAD") -> str:
    number = _num(value)
    if not np.isfinite(number):
        return "N/D"
    symbol = "$" if currency in {"CAD", "USD"} else f"{currency} "
    return f"{symbol}{number:,.2f}"


def _pct(value: Any) -> str:
    number = _num(value)
    if not np.isfinite(number):
        return "N/D"
    return f"{number:+.2f}%"


def _series(history: pd.DataFrame, column: str) -> pd.Series:
    if history is None or history.empty or column not in history.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(history[column], errors="coerce").dropna()


def pro_chart_config(*, enable_drawing: bool = True, scroll_zoom: bool = False) -> dict[str, Any]:
    """Configuration Plotly pour un espace graphique professionnel.

    Les outils de dessin Plotly sont natifs côté navigateur : ils permettent de
    tracer lignes, zones et formes directement sur le graphique sans dépendance
    additionnelle. Les dessins manuels restent dans le graphique tant que la
    figure n'est pas recréée.
    """
    config: dict[str, Any] = {
        "displaylogo": False,
        "responsive": True,
        "scrollZoom": bool(scroll_zoom),
        "doubleClick": "reset",
        "toImageButtonOptions": {
            "format": "png",
            "filename": "anatole_focus_chart",
            "height": 1080,
            "width": 1920,
            "scale": 2,
        },
        "modeBarButtonsToRemove": [
            "select2d",
            "lasso2d",
            "autoScale2d",
        ],
    }
    if enable_drawing:
        config["modeBarButtonsToAdd"] = PRO_DRAW_BUTTONS
        config["edits"] = {
            "shapePosition": True,
            "annotationPosition": True,
        }
    return config


def chart_model_options() -> list[str]:
    return list(MODEL_LABELS.values())


def _model_key(label: str) -> str:
    for key, value in MODEL_LABELS.items():
        if value == label:
            return key
    return str(label)


def _tail(history: pd.DataFrame, n: int = 160) -> pd.DataFrame:
    if history is None or history.empty:
        return pd.DataFrame()
    return history.tail(min(len(history), n)).copy()


def _x_at(frame: pd.DataFrame, position: int) -> Any:
    if frame.empty:
        return None
    position = max(0, min(len(frame) - 1, position))
    return frame.index[position]


def _support_resistance_levels(history: pd.DataFrame, max_levels: int = 2) -> tuple[list[float], list[float]]:
    close = _series(history, "Close")
    high = _series(history, "High")
    low = _series(history, "Low")
    if close.empty:
        return [], []
    price = float(close.iloc[-1])
    recent = history.tail(min(len(history), 180))
    candidates: list[float] = []
    for column in ["High", "Low", "Close"]:
        values = pd.to_numeric(recent.get(column), errors="coerce").dropna()
        if values.empty:
            continue
        for q in (0.05, 0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 0.95):
            value = _num(values.quantile(q))
            if np.isfinite(value):
                candidates.append(value)
        candidates.extend([_num(values.min()), _num(values.max()), _num(values.tail(30).min()), _num(values.tail(30).max())])

    def unique_near(values: list[float]) -> list[float]:
        filtered: list[float] = []
        for value in sorted([v for v in values if np.isfinite(v)], key=lambda x: abs(x - price)):
            tolerance = max(price * 0.008, 0.05)
            if all(abs(value - kept) > tolerance for kept in filtered):
                filtered.append(float(value))
            if len(filtered) >= max_levels:
                break
        return filtered

    supports = unique_near([v for v in candidates if v < price])
    resistances = unique_near([v for v in candidates if v > price])
    return supports, resistances


def _add_zone(fig: go.Figure, y: float, color: str, label: str, width_pct: float = 0.006) -> None:
    if not np.isfinite(y):
        return
    band = max(abs(y) * width_pct, 0.05)
    fig.add_hrect(
        y0=y - band,
        y1=y + band,
        line_width=0,
        fillcolor=color,
        opacity=0.14,
        annotation_text=label,
        annotation_position="top left",
        annotation_font_size=11,
        annotation_font_color="rgba(226,242,255,0.78)",
        row=1,
        col=1,
    )


def _add_trend_channel(fig: go.Figure, history: pd.DataFrame) -> None:
    frame = _tail(history, 140)
    close = _series(frame, "Close")
    low = _series(frame, "Low")
    high = _series(frame, "High")
    if frame.empty or close.size < 30:
        return

    x0 = _x_at(frame, max(0, len(frame) - 120))
    x1 = _x_at(frame, len(frame) - 1)
    lows = low.tail(min(len(low), 120)) if not low.empty else close.tail(min(len(close), 120))
    highs = high.tail(min(len(high), 120)) if not high.empty else close.tail(min(len(close), 120))
    if lows.size < 10 or highs.size < 10 or x0 is None or x1 is None:
        return

    y0 = _num(lows.quantile(0.12))
    y1 = _num(close.iloc[-1] * (1 - 0.012))
    channel_height = max(_num(highs.quantile(0.88)) - _num(lows.quantile(0.12)), abs(close.iloc[-1]) * 0.04)
    y0_top = y0 + channel_height
    y1_top = y1 + channel_height

    if not all(np.isfinite(v) for v in [y0, y1, y0_top, y1_top]):
        return

    for y_start, y_end, label in [(y0, y1, "Canal bas"), (y0_top, y1_top, "Canal haut")]:
        fig.add_shape(
            type="line",
            x0=x0,
            y0=y_start,
            x1=x1,
            y1=y_end,
            xref="x",
            yref="y",
            line={"color": "rgba(56,189,248,0.78)", "width": 1.35, "dash": "dash"},
            row=1,
            col=1,
        )
    fig.add_annotation(
        x=x1,
        y=y1_top,
        text="Canal tendance",
        showarrow=False,
        bgcolor="rgba(8,47,73,0.72)",
        bordercolor="rgba(56,189,248,0.24)",
        font={"color": "#BAE6FD", "size": 11},
        row=1,
        col=1,
    )


def _add_fibonacci(fig: go.Figure, history: pd.DataFrame, currency: str = "CAD") -> None:
    frame = _tail(history, 180)
    high = _series(frame, "High")
    low = _series(frame, "Low")
    if frame.empty or high.empty or low.empty:
        return
    swing_high = _num(high.max())
    swing_low = _num(low.min())
    if not np.isfinite(swing_high) or not np.isfinite(swing_low) or swing_high <= swing_low:
        return
    x0 = _x_at(frame, max(0, len(frame) - 150))
    x1 = _x_at(frame, len(frame) - 1)
    if x0 is None or x1 is None:
        return
    levels = [0.236, 0.382, 0.5, 0.618, 0.786]
    span = swing_high - swing_low
    for level in levels:
        price = swing_high - span * level
        fig.add_shape(
            type="line",
            x0=x0,
            x1=x1,
            y0=price,
            y1=price,
            xref="x",
            yref="y",
            line={"color": "rgba(168,85,247,0.54)", "width": 1.0, "dash": "dot"},
            row=1,
            col=1,
        )
        fig.add_annotation(
            x=x1,
            y=price,
            text=f"Fib {level*100:.1f}% · {_money(price, currency)}",
            showarrow=False,
            xanchor="right",
            bgcolor="rgba(30,27,75,0.62)",
            bordercolor="rgba(168,85,247,0.18)",
            font={"color": "#DDD6FE", "size": 10},
            row=1,
            col=1,
        )


def _add_breakout_box(fig: go.Figure, history: pd.DataFrame) -> None:
    frame = _tail(history, 90)
    close = _series(frame, "Close")
    high = _series(frame, "High")
    low = _series(frame, "Low")
    if frame.empty or close.size < 20:
        return
    x0 = _x_at(frame, max(0, len(frame) - 45))
    x1 = _x_at(frame, len(frame) - 1)
    top = _num(high.tail(45).quantile(0.82)) if not high.empty else _num(close.tail(45).quantile(0.82))
    bottom = _num(low.tail(45).quantile(0.18)) if not low.empty else _num(close.tail(45).quantile(0.18))
    if x0 is None or x1 is None or not np.isfinite(top) or not np.isfinite(bottom) or top <= bottom:
        return
    fig.add_shape(
        type="rect",
        x0=x0,
        x1=x1,
        y0=bottom,
        y1=top,
        xref="x",
        yref="y",
        line={"color": "rgba(14,165,233,0.62)", "width": 1.1, "dash": "dash"},
        fillcolor="rgba(14,165,233,0.08)",
        row=1,
        col=1,
    )
    fig.add_annotation(
        x=x0,
        y=top,
        text="Range / cassure à surveiller",
        showarrow=False,
        xanchor="left",
        bgcolor="rgba(8,47,73,0.70)",
        font={"color": "#E0F2FE", "size": 11},
        row=1,
        col=1,
    )


def apply_pro_chart_models(
    fig: go.Figure,
    history: pd.DataFrame,
    selected_labels: list[str] | None,
    *,
    info: dict[str, Any] | None = None,
    currency: str = "CAD",
) -> go.Figure:
    selected = {_model_key(label) for label in (selected_labels or [])}
    info = info or {}

    if "support_resistance" in selected:
        supports, resistances = _support_resistance_levels(history, max_levels=2)
        for idx, level in enumerate(supports, 1):
            _add_zone(fig, level, "#10B981", f"Support {idx}")
        for idx, level in enumerate(resistances, 1):
            _add_zone(fig, level, "#EF4444", f"Résistance {idx}")

    if "trend_channel" in selected:
        _add_trend_channel(fig, history)

    if "fibonacci" in selected:
        _add_fibonacci(fig, history, currency=currency)

    if "breakout_box" in selected:
        _add_breakout_box(fig, history)

    if "analyst_target" in selected:
        target = _num(info.get("targetMeanPrice"))
        if np.isfinite(target):
            _add_zone(fig, target, "#F59E0B", "Objectif analystes", width_pct=0.004)

    return fig


def apply_pro_chart_style(fig: go.Figure, ticker: str, *, height: int = 760) -> go.Figure:
    fig.update_layout(
        height=height,
        title=None,
        dragmode="pan",
        clickmode="event+select",
        hovermode="x unified",
        margin={"t": 18, "l": 4, "r": 4, "b": 4},
        legend={
            "orientation": "h",
            "y": 1.04,
            "x": 0,
            "bgcolor": "rgba(2,12,22,0.64)",
            "bordercolor": "rgba(125,211,252,0.16)",
            "borderwidth": 1,
            "font": {"size": 11},
        },
        newshape={
            "line": {"color": "#38BDF8", "width": 2},
            "fillcolor": "rgba(56,189,248,0.14)",
            "opacity": 0.85,
        },
        activeselection={"fillcolor": "rgba(56,189,248,0.14)", "opacity": 0.18},
        modebar={"orientation": "h", "bgcolor": "rgba(2,12,22,0.82)", "color": "#9DB7CC", "activecolor": "#38BDF8"},
    )
    fig.update_xaxes(
        rangeslider_visible=False,
        showspikes=True,
        spikemode="across+marker",
        spikesnap="cursor",
        spikecolor="rgba(148, 184, 210, .42)",
        spikethickness=1,
        showline=True,
        mirror=True,
    )
    fig.update_yaxes(
        side="right",
        showspikes=True,
        spikemode="across+marker",
        spikesnap="cursor",
        spikecolor="rgba(148, 184, 210, .38)",
        spikethickness=1,
        showline=True,
        mirror=True,
    )
    return fig


def pro_quote_panel(history: pd.DataFrame, info: dict[str, Any], currency: str = "CAD") -> dict[str, str]:
    if history is None or history.empty:
        return {}
    last = history.iloc[-1]
    previous = history.iloc[-2] if len(history) > 1 else last
    close = _num(last.get("Close"))
    prev = _num(previous.get("Close"))
    change = ((close - prev) / prev * 100) if np.isfinite(close) and np.isfinite(prev) and prev else np.nan
    volume = _num(last.get("Volume"))
    avg_volume = _num(pd.to_numeric(history.get("Volume"), errors="coerce").tail(20).mean())
    target = _num(info.get("targetMeanPrice"))
    upside = ((target / close - 1) * 100) if np.isfinite(target) and np.isfinite(close) and close else np.nan
    supports, resistances = _support_resistance_levels(history, max_levels=2)
    return {
        "Prix": _money(close, currency),
        "Variation": _pct(change),
        "Volume": f"{volume:,.0f}" if np.isfinite(volume) else "N/D",
        "Volume moyen 20j": f"{avg_volume:,.0f}" if np.isfinite(avg_volume) else "N/D",
        "Objectif moyen": _money(target, currency),
        "Potentiel vs objectif": _pct(upside),
        "Résistance 1": _money(resistances[0], currency) if resistances else "N/D",
        "Support 1": _money(supports[0], currency) if supports else "N/D",
    }


def drawing_tool_labels() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Outil": "Ligne", "Usage": "Tracer une tendance, une cassure ou une invalidation."},
            {"Outil": "Rectangle", "Usage": "Marquer une zone de support, résistance, range ou gap."},
            {"Outil": "Open path", "Usage": "Dessiner un mouvement ou une structure libre."},
            {"Outil": "Circle", "Usage": "Encadrer une réaction de prix ou un événement."},
            {"Outil": "Erase shape", "Usage": "Supprimer les tracés manuels."},
        ]
    )
