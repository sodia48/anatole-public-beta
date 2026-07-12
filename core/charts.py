from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


COLORWAY = [
    "#2563EB",
    "#0EA5E9",
    "#14B8A6",
    "#8B5CF6",
    "#F59E0B",
    "#EC4899",
    "#22C55E",
    "#64748B",
]

DEFAULT_PLOTLY_OVERLAYS = [
    "SMA 20",
    "SMA 50",
    "SMA 200",
    "EMA 20",
    "Bandes de Bollinger",
]


def _chart_height(default: int | None) -> int | None:
    if default is None:
        return None
    try:
        if bool(st.session_state.get("mobile_mode_auto", False)):
            if default >= 680:
                return 585
            if default >= 560:
                return 500
            return max(390, min(default, 460))
    except Exception:
        pass
    return default



def _palette() -> dict[str, str]:
    dark = bool(st.session_state.get("theme_toggle", False))
    if dark:
        return {
            "text": "#EAF6FF",
            "muted": "#9AB6CC",
            "grid": "rgba(148, 184, 210, 0.13)",
            "surface": "rgba(11,31,48,0.72)",
            "legend": "rgba(15,39,59,0.86)",
            "border": "rgba(125,211,252,0.16)",
            "hover": "rgba(2,12,22,0.97)",
        }
    return {
        "text": "#102D49",
        "muted": "#5B7088",
        "grid": "rgba(74,125,167,0.13)",
        "surface": "rgba(255,255,255,0.58)",
        "legend": "rgba(255,255,255,0.72)",
        "border": "rgba(76,145,201,0.16)",
        "hover": "rgba(15,39,66,0.96)",
    }


def _modernize(fig: go.Figure, height: int | None = None) -> go.Figure:
    palette = _palette()
    layout: dict = {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": palette["surface"],
        "font": {
            "family": "Inter, ui-sans-serif, system-ui, sans-serif",
            "color": palette["text"],
            "size": 13,
        },
        "title": {
            "font": {"color": palette["text"], "size": 19},
            "x": 0.02,
            "xanchor": "left",
        },
        "colorway": COLORWAY,
        "hoverlabel": {
            "bgcolor": palette["hover"],
            "bordercolor": palette["border"],
            "font": {
                "color": "white",
                "family": "Inter, ui-sans-serif, system-ui, sans-serif",
            },
        },
        "legend": {
            "bgcolor": palette["legend"],
            "bordercolor": palette["border"],
            "borderwidth": 1,
            "font": {"color": palette["muted"]},
        },
    }
    if height is not None:
        layout["height"] = _chart_height(height)

    fig.update_layout(**layout)
    fig.update_xaxes(
        gridcolor=palette["grid"],
        zerolinecolor=palette["grid"],
        linecolor=palette["border"],
        tickfont={"color": palette["muted"]},
        title_font={"color": palette["muted"]},
    )
    fig.update_yaxes(
        gridcolor=palette["grid"],
        zerolinecolor=palette["grid"],
        linecolor=palette["border"],
        tickfont={"color": palette["muted"]},
        title_font={"color": palette["muted"]},
    )
    return fig

def heatmap_figure(df: pd.DataFrame, height: int = 760) -> go.Figure:
    palette = _palette()
    view = df.copy()

    for column in ["Prix", "Variation", "PoidsIndice", "Volume"]:
        if column in view.columns:
            view[column] = pd.to_numeric(view[column], errors="coerce")

    view["PrixTxt"] = view["Prix"].map(
        lambda value: f"${value:,.2f}" if pd.notna(value) else "N/D"
    )
    view["VariationTxt"] = view["Variation"].map(
        lambda value: f"{value:+.2f}%" if pd.notna(value) else "N/D"
    )
    view["PoidsTxt"] = view["PoidsIndice"].map(
        lambda value: f"{value:.2f}%" if pd.notna(value) else "N/D"
    )
    view["VolumeTxt"] = view["Volume"].map(
        lambda value: f"{value:,.0f}" if pd.notna(value) else "N/D"
    )

    fig = px.treemap(
        view,
        path=["Secteur", "Ticker"],
        values="PoidsIndice",
        color="Variation",
        color_continuous_scale=[
            [0.0, "#DC2626"],
            [0.5, "#315A7D"],
            [1.0, "#059669"],
        ],
        color_continuous_midpoint=0,
        custom_data=[
            "Nom",
            "PrixTxt",
            "VariationTxt",
            "PoidsTxt",
            "VolumeTxt",
            "YahooTicker",
            "SourceCours",
        ],
    )
    fig.update_traces(
        texttemplate="<b>%{label}</b><br>%{customdata[2]}",
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Ticker : %{label}<br>"
            "Prix : %{customdata[1]}<br>"
            "Variation : %{customdata[2]}<br>"
            "Poids : %{customdata[3]}<br>"
            "Volume : %{customdata[4]}<br>"
            "Source : %{customdata[6]}<extra></extra>"
        ),
        root_color=palette["surface"],
        pathbar={"visible": False},
        marker={
            "line": {"color": "rgba(255,255,255,0.78)", "width": 1.35},
        },
        tiling={"pad": 3, "packing": "squarify"},
        textfont={"size": 12},
    )
    fig.update_layout(
        height=height,
        margin={"t": 8, "l": 0, "r": 0, "b": 0},
        uniformtext={"minsize": 9, "mode": "hide"},
        coloraxis_colorbar={
            "title": {"text": "Var. %", "font": {"color": palette["muted"]}},
            "thickness": 14,
            "tickfont": {"color": palette["muted"]},
            "outlinewidth": 0,
            "len": 0.94,
        },
        paper_bgcolor="rgba(0,0,0,0)",
        font={
            "family": "Inter, ui-sans-serif, system-ui, sans-serif",
            "color": "white",
        },
    )
    return fig


def _nearest_history_point(
    history: pd.DataFrame,
    raw_time: object,
) -> tuple[object, float] | None:
    """Retourne le point d'historique le plus proche d'une date d'événement."""
    if history is None or history.empty or raw_time is None:
        return None

    try:
        event_day = pd.Timestamp(raw_time).tz_localize(None).normalize()
    except Exception:
        return None

    index = pd.to_datetime(history.index)
    try:
        index = index.tz_localize(None)
    except TypeError:
        pass

    normalized = pd.Series(index.normalize(), index=history.index)
    matches = normalized[normalized == event_day]
    if matches.empty:
        # Si l'événement tombe un week-end ou jour férié, on prend la séance
        # la plus proche dans une fenêtre de quelques jours.
        distances = (normalized - event_day).abs()
        if distances.empty or distances.min() > pd.Timedelta(days=5):
            return None
        x_value = distances.idxmin()
    else:
        x_value = matches.index[-1]

    high = pd.to_numeric(history.get("High"), errors="coerce")
    close = pd.to_numeric(history.get("Close"), errors="coerce")
    if x_value in high.index and pd.notna(high.loc[x_value]):
        y_value = float(high.loc[x_value]) * 1.018
    elif x_value in close.index and pd.notna(close.loc[x_value]):
        y_value = float(close.loc[x_value]) * 1.018
    else:
        return None

    return x_value, y_value


def _add_plotly_event_markers(
    fig: go.Figure,
    history: pd.DataFrame,
    markers: list[dict] | None,
) -> None:
    """Affiche les événements sur le graphique Plotly principal."""
    if not markers:
        return

    xs: list[object] = []
    ys: list[float] = []
    texts: list[str] = []
    hover_texts: list[str] = []

    for marker in markers[:16]:
        point = _nearest_history_point(history, marker.get("time"))
        if point is None:
            continue

        x_value, y_value = point
        color = marker.get("color") or "#F59E0B"
        short_text = str(marker.get("text") or "N")[:3]
        title = str(
            marker.get("title")
            or marker.get("headline")
            or marker.get("label")
            or "Événement"
        )
        source = str(marker.get("source") or marker.get("publisher") or "").strip()
        date_label = pd.Timestamp(x_value).strftime("%Y-%m-%d")

        xs.append(x_value)
        ys.append(y_value)
        texts.append(short_text)
        hover_texts.append(
            f"<b>{title}</b><br>Date : {date_label}"
            + (f"<br>Source : {source}" if source else "")
        )

        fig.add_vline(
            x=x_value,
            line_width=1.2,
            line_dash="dot",
            line_color=color,
            opacity=0.42,
            row=1,
            col=1,
        )

    if not xs:
        return

    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers+text",
            name="Événements",
            text=texts,
            textposition="top center",
            textfont={"size": 11, "color": "#F59E0B"},
            marker={
                "size": 14,
                "symbol": "diamond",
                "color": "#F59E0B",
                "line": {"width": 1.5, "color": "white"},
            },
            hovertext=hover_texts,
            hovertemplate="%{hovertext}<extra></extra>",
        ),
        row=1,
        col=1,
    )


def _add_plotly_price_lines(
    fig: go.Figure,
    price_lines: list[dict] | None,
) -> None:
    """Affiche les lignes horizontales importantes comme la cible analystes."""
    for line in price_lines or []:
        price = line.get("price")
        try:
            price = float(price)
        except Exception:
            continue

        title = str(line.get("title") or "Niveau")
        color = str(line.get("color") or "#F59E0B")

        fig.add_hline(
            y=price,
            line_dash="dash",
            line_color=color,
            line_width=1.4,
            opacity=0.78,
            annotation_text=title,
            annotation_position="top left",
            row=1,
            col=1,
        )


def price_chart(
    history: pd.DataFrame,
    ticker: str,
    overlays: list[str] | None = None,
    markers: list[dict] | None = None,
    price_lines: list[dict] | None = None,
) -> go.Figure:
    overlays = overlays or DEFAULT_PLOTLY_OVERLAYS

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.77, 0.23],
    )
    fig.add_trace(
        go.Candlestick(
            x=history.index,
            open=history["Open"],
            high=history["High"],
            low=history["Low"],
            close=history["Close"],
            name=ticker,
            increasing_line_color="#059669",
            decreasing_line_color="#DC2626",
            increasing_fillcolor="#10B981",
            decreasing_fillcolor="#EF4444",
        ),
        row=1,
        col=1,
    )
    mapping = {
        "SMA 20": "SMA20",
        "SMA 50": "SMA50",
        "SMA 200": "SMA200",
        "EMA 20": "EMA20",
    }
    for label, column in mapping.items():
        if label in overlays and column in history:
            fig.add_trace(
                go.Scatter(x=history.index, y=history[column], name=label, mode="lines", line={"width": 1.7}),
                row=1,
                col=1,
            )
    if (
        "Bandes de Bollinger" in overlays
        and "BB_Haut" in history
        and "BB_Bas" in history
    ):
        fig.add_trace(
            go.Scatter(
                x=history.index,
                y=history["BB_Haut"],
                name="Bollinger haut",
                mode="lines",
                line={"dash": "dot", "width": 1.1},
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=history.index,
                y=history["BB_Bas"],
                name="Bollinger bas",
                mode="lines",
                line={"dash": "dot", "width": 1.1},
                fill="tonexty",
                fillcolor="rgba(37,99,235,0.07)",
            ),
            row=1,
            col=1,
        )
    if "Volume" in history:
        volume_colors = [
            "rgba(16,185,129,0.55)" if float(close) >= float(open_) else "rgba(239,68,68,0.55)"
            for open_, close in zip(history["Open"].fillna(0), history["Close"].fillna(0))
        ]
        volume_labels = [
            "Volume d'entrée" if float(close) >= float(open_) else "Volume de sortie"
            for open_, close in zip(history["Open"].fillna(0), history["Close"].fillna(0))
        ]
        fig.add_trace(
            go.Bar(
                x=history.index,
                y=history["Volume"],
                name="Volume",
                opacity=0.60,
                marker_color=volume_colors,
                customdata=volume_labels,
                hovertemplate="%{x}<br>%{customdata}: %{y:,.0f}<extra></extra>",
            ),
            row=2,
            col=1,
        )

    _add_plotly_event_markers(fig, history, markers)
    _add_plotly_price_lines(fig, price_lines)

    fig.update_layout(
        margin={"t": 48, "l": 6, "r": 6, "b": 6},
        title=f"{ticker} · prix et indicateurs",
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        dragmode="pan",
        uirevision=f"{ticker}-focus-chart",
        legend={"orientation": "h", "y": 1.025, "x": 0},
    )
    fig.update_xaxes(
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor="rgba(37,99,235,.36)",
        spikethickness=1,
    )
    fig.update_yaxes(
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor="rgba(37,99,235,.30)",
        spikethickness=1,
    )
    return _modernize(fig, 690)


def oscillator_chart(history: pd.DataFrame, ticker: str) -> go.Figure:
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("RSI 14", "MACD"),
    )
    fig.add_trace(go.Scatter(x=history.index, y=history["RSI14"], name="RSI 14", line={"color": "#2563EB"}), row=1, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#DC2626", opacity=.7, row=1, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#059669", opacity=.7, row=1, col=1)
    fig.add_trace(go.Scatter(x=history.index, y=history["MACD"], name="MACD", line={"color": "#0EA5E9"}), row=2, col=1)
    fig.add_trace(go.Scatter(x=history.index, y=history["SignalMACD"], name="Signal", line={"color": "#8B5CF6"}), row=2, col=1)
    fig.add_trace(go.Bar(x=history.index, y=history["HistogrammeMACD"], name="Histogramme", opacity=0.48, marker_color="#93C5FD"), row=2, col=1)
    fig.update_layout(
        margin={"t": 60, "l": 8, "r": 8, "b": 8},
        title=f"Oscillateurs · {ticker}",
        hovermode="x unified",
    )
    return _modernize(fig, 520)


def normalized_performance_chart(normalized: pd.DataFrame) -> go.Figure:
    prepared = normalized.copy()
    prepared.index.name = "Date"
    long = prepared.reset_index().melt(id_vars="Date", var_name="Ticker", value_name="Base 100")
    fig = px.line(long, x="Date", y="Base 100", color="Ticker", title="Performance normalisée (base 100)")
    fig.update_traces(line={"width": 2.3})
    fig.update_layout(hovermode="x unified", margin={"t": 58, "l": 8, "r": 8, "b": 8})
    return _modernize(fig, 560)


def correlation_chart(correlation: pd.DataFrame) -> go.Figure:
    fig = px.imshow(
        correlation,
        text_auto=".2f",
        zmin=-1,
        zmax=1,
        color_continuous_scale=[
            [0.0, "#DC2626"],
            [0.5, "#EFF8FF"],
            [1.0, "#2563EB"],
        ],
        title="Corrélation des rendements quotidiens",
    )
    fig.update_layout(margin={"t": 60, "l": 8, "r": 8, "b": 8})
    return _modernize(fig, max(520, 55 * len(correlation)))


def portfolio_allocation_chart(portfolio: pd.DataFrame, group: str = "Ticker") -> go.Figure:
    grouped = portfolio.groupby(group, as_index=False)["Valeur"].sum()
    fig = px.pie(
        grouped,
        names=group,
        values="Valeur",
        hole=0.56,
        title=f"Allocation par {group.lower()}",
        color_discrete_sequence=COLORWAY,
    )
    fig.update_traces(textposition="inside", marker={"line": {"color": "white", "width": 2}})
    fig.update_layout(margin={"t": 60, "l": 8, "r": 8, "b": 8})
    return _modernize(fig, 450)


def equity_curve_chart(frame: pd.DataFrame, title: str = "Courbe de capital") -> go.Figure:
    columns = [column for column in ["Equity", "BuyHoldEquity"] if column in frame]
    prepared = frame[columns].copy()
    prepared.index.name = "Date"
    plot = prepared.reset_index().melt(id_vars="Date", var_name="Série", value_name="Valeur")
    fig = px.line(plot, x="Date", y="Valeur", color="Série", title=title)
    fig.update_traces(line={"width": 2.35})
    fig.update_layout(hovermode="x unified", margin={"t": 58, "l": 8, "r": 8, "b": 8})
    return _modernize(fig, 560)


def market_breadth_chart(features: pd.DataFrame) -> go.Figure:
    categories = ["Au-dessus SMA20", "Au-dessus SMA50", "Au-dessus SMA200"]
    values = [
        features["AboveSMA20"].mean() * 100,
        features["AboveSMA50"].mean() * 100,
        features["AboveSMA200"].mean() * 100,
    ]
    fig = px.bar(
        x=categories,
        y=values,
        labels={"x": "", "y": "% des titres"},
        title="Largeur technique du marché",
        color=values,
        color_continuous_scale=["#BFDBFE", "#2563EB"],
    )
    fig.update_traces(marker_line_width=0, text=[f"{value:.0f}%" for value in values], textposition="outside")
    fig.update_yaxes(range=[0, 108])
    fig.update_layout(showlegend=False, coloraxis_showscale=False, margin={"t": 58, "l": 8, "r": 8, "b": 8})
    return _modernize(fig, 360)


def sector_performance_chart(features: pd.DataFrame) -> go.Figure:
    change_col = "Variation" if "Variation" in features else "DailyChangeTech"
    sector = features.groupby("Secteur", as_index=False)[change_col].mean().sort_values(change_col)
    colors = ["#DC2626" if value < 0 else "#059669" for value in sector[change_col]]
    fig = px.bar(
        sector,
        x=change_col,
        y="Secteur",
        orientation="h",
        title="Performance moyenne par secteur",
        labels={change_col: "Variation moyenne (%)"},
    )
    fig.update_traces(marker_color=colors, marker_line_width=0)
    fig.add_vline(x=0, line_color="rgba(15,39,66,.28)", line_width=1)
    fig.update_layout(margin={"t": 58, "l": 8, "r": 8, "b": 8})
    return _modernize(fig, 440)


def rolling_correlation_chart(prices: pd.DataFrame, first: str, second: str, window: int) -> go.Figure:
    returns = prices[[first, second]].pct_change()
    rolling = returns[first].rolling(window).corr(returns[second])
    fig = px.line(
        x=rolling.index,
        y=rolling.values,
        labels={"x": "Date", "y": "Corrélation"},
        title=f"Corrélation mobile {window} séances · {first} / {second}",
    )
    fig.update_traces(line={"color": "#2563EB", "width": 2.3}, fill="tozeroy", fillcolor="rgba(37,99,235,.08)")
    fig.add_hline(y=0, line_dash="dash", line_color="rgba(15,39,66,.34)")
    fig.update_yaxes(range=[-1, 1])
    fig.update_layout(margin={"t": 58, "l": 8, "r": 8, "b": 8})
    return _modernize(fig, 420)
