from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd


NUMERIC_HINTS = (
    "Prix",
    "Variation",
    "RSI14",
    "DividendYield",
    "TrailingPE",
    "ForwardPE",
    "Beta",
    "MarketCap",
    "Volume",
    "VolumeRelatif",
    "SMA20",
    "SMA50",
    "SMA200",
    "Rendement1M",
    "Rendement3M",
    "Rendement6M",
    "Rendement1Y",
)

TICKER_STOPWORDS = {
    "TSX",
    "ETF",
    "IPO",
    "RSI",
    "SMA",
    "CAD",
    "USD",
    "PE",
    "P/E",
    "IA",
    "AI",
}


@dataclass
class StockSnapshot:
    ticker: str
    name: str
    sector: str
    price: float
    change: float
    rsi: float
    dividend_yield: float
    pe: float
    beta: float
    volume_rel: float
    sma20: float
    sma50: float
    sma200: float


def _safe_float(value: Any, default: float = np.nan) -> float:
    try:
        number = float(value)
        return number if np.isfinite(number) else default
    except Exception:
        return default


def _as_text(value: Any, default: str = "N/D") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "none", "nat"} else default


def _pct(value: Any, decimals: int = 2, signed: bool = True) -> str:
    number = _safe_float(value)
    if np.isnan(number):
        return "N/D"
    sign = "+" if signed and number > 0 else ""
    return f"{sign}{number:.{decimals}f} %".replace(".", ",")


def _num(value: Any, decimals: int = 2) -> str:
    number = _safe_float(value)
    if np.isnan(number):
        return "N/D"
    text = f"{number:,.{decimals}f}"
    return text.replace(",", " ").replace(".", ",")


def _money(value: Any, decimals: int = 2) -> str:
    number = _safe_float(value)
    if np.isnan(number):
        return "N/D"
    text = f"{number:,.{decimals}f}"
    return text.replace(",", " ").replace(".", ",") + " $"


def _compact_money(value: Any) -> str:
    number = _safe_float(value)
    if np.isnan(number):
        return "N/D"
    absn = abs(number)
    if absn >= 1_000_000_000_000:
        return f"{number / 1_000_000_000_000:.2f} T$".replace(".", ",")
    if absn >= 1_000_000_000:
        return f"{number / 1_000_000_000:.2f} G$".replace(".", ",")
    if absn >= 1_000_000:
        return f"{number / 1_000_000:.2f} M$".replace(".", ",")
    return _money(number, 0)


def _get_col(df: pd.DataFrame, *names: str) -> str | None:
    lower_map = {str(col).lower(): str(col) for col in df.columns}
    for name in names:
        if name in df.columns:
            return name
        found = lower_map.get(name.lower())
        if found:
            return found
    return None


def _clean_market(market: pd.DataFrame | None) -> pd.DataFrame:
    if market is None or market.empty:
        return pd.DataFrame()
    df = market.copy()
    for col in df.columns:
        if col in NUMERIC_HINTS or any(token.lower() in str(col).lower() for token in ["yield", "variation", "rsi", "volume", "prix", "marketcap", "beta", "sma", "pe"]):
            
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() > 0:
                df[col] = converted
    return df


def _available_columns(df: pd.DataFrame) -> list[str]:
    preferred = [
        "Ticker",
        "YahooTicker",
        "Nom",
        "Secteur",
        "Prix",
        "Variation",
        "RSI14",
        "VolumeRelatif",
        "DividendYield",
        "TrailingPE",
        "MarketCap",
        "SMA20",
        "SMA50",
        "SMA200",
        "SourceCours",
        "Horodatage",
    ]
    return [c for c in preferred if c in df.columns]


def _ticker_series(df: pd.DataFrame) -> pd.Series:
    col = _get_col(df, "Ticker", "Symbol", "Symbole")
    if not col:
        return pd.Series(dtype=str)
    return df[col].fillna("").astype(str).str.replace(".TO", "", regex=False).str.upper()


def _extract_tickers(question: str, market: pd.DataFrame | None = None) -> list[str]:
    tokens = re.findall(r"\b[A-Z][A-Z0-9.\-]{1,9}\b", question.upper())
    tickers: list[str] = []
    valid: set[str] = set()
    if market is not None and not market.empty:
        valid = set(_ticker_series(market).dropna().astype(str))
        yahoo_col = _get_col(market, "YahooTicker", "Yahoo")
        if yahoo_col:
            valid |= set(
                market[yahoo_col]
                .fillna("")
                .astype(str)
                .str.replace(".TO", "", regex=False)
                .str.upper()
            )
    for token in tokens:
        normalized = token.replace(".TO", "")
        if normalized in TICKER_STOPWORDS:
            continue
        if valid and normalized not in valid:
            continue
        if normalized not in tickers:
            tickers.append(normalized)
    return tickers[:6]


def _row_for_ticker(market: pd.DataFrame, ticker: str) -> pd.Series | None:
    if market is None or market.empty:
        return None
    target = ticker.upper().replace(".TO", "")
    ticker_col = _get_col(market, "Ticker", "Symbol", "Symbole")
    yahoo_col = _get_col(market, "YahooTicker", "Yahoo")
    masks = []
    if ticker_col:
        masks.append(market[ticker_col].fillna("").astype(str).str.upper().str.replace(".TO", "", regex=False).eq(target))
    if yahoo_col:
        masks.append(market[yahoo_col].fillna("").astype(str).str.upper().str.replace(".TO", "", regex=False).eq(target))
    if not masks:
        return None
    mask = masks[0]
    for extra in masks[1:]:
        mask = mask | extra
    rows = market[mask]
    if rows.empty:
        return None
    return rows.iloc[0]


def _snapshot_from_row(row: pd.Series) -> StockSnapshot:
    return StockSnapshot(
        ticker=_as_text(row.get("Ticker", row.get("Symbol", "N/D"))),
        name=_as_text(row.get("Nom", row.get("Name", "N/D"))),
        sector=_as_text(row.get("Secteur", row.get("Sector", "N/D"))),
        price=_safe_float(row.get("Prix")),
        change=_safe_float(row.get("Variation")),
        rsi=_safe_float(row.get("RSI14")),
        dividend_yield=_safe_float(row.get("DividendYield")),
        pe=_safe_float(row.get("TrailingPE", row.get("ForwardPE"))),
        beta=_safe_float(row.get("Beta")),
        volume_rel=_safe_float(row.get("VolumeRelatif", row.get("RelativeVolume"))),
        sma20=_safe_float(row.get("SMA20")),
        sma50=_safe_float(row.get("SMA50")),
        sma200=_safe_float(row.get("SMA200")),
    )


def _trend_reading(stock: StockSnapshot) -> list[str]:
    observations: list[str] = []
    if not np.isnan(stock.change):
        if stock.change >= 2:
            observations.append("mouvement quotidien fortement positif")
        elif stock.change <= -2:
            observations.append("pression baissière marquée sur la séance")
        elif stock.change > 0:
            observations.append("mouvement quotidien légèrement positif")
        elif stock.change < 0:
            observations.append("mouvement quotidien légèrement négatif")
    if not np.isnan(stock.rsi):
        if stock.rsi >= 70:
            observations.append("RSI élevé : titre potentiellement étiré à court terme")
        elif stock.rsi <= 30:
            observations.append("RSI faible : titre potentiellement survendu à court terme")
        else:
            observations.append("RSI dans une zone intermédiaire")
    if not np.isnan(stock.price):
        ma_notes = []
        if not np.isnan(stock.sma50):
            ma_notes.append("au-dessus de la SMA50" if stock.price > stock.sma50 else "sous la SMA50")
        if not np.isnan(stock.sma200):
            ma_notes.append("au-dessus de la SMA200" if stock.price > stock.sma200 else "sous la SMA200")
        if ma_notes:
            observations.append("prix " + " et ".join(ma_notes))
    if not np.isnan(stock.volume_rel):
        if stock.volume_rel >= 1.5:
            observations.append("volume relatif élevé : le mouvement attire davantage de participation")
        elif stock.volume_rel <= 0.7:
            observations.append("volume relatif faible : signal moins confirmé par la participation")
    return observations or ["données techniques encore limitées pour ce titre"]


def _sector_table(market: pd.DataFrame) -> pd.DataFrame:
    if market.empty or "Secteur" not in market.columns or "Variation" not in market.columns:
        return pd.DataFrame()
    tmp = market.copy()
    tmp["Variation"] = pd.to_numeric(tmp["Variation"], errors="coerce")
    grouped = (
        tmp.dropna(subset=["Variation"])
        .groupby("Secteur", dropna=False)
        .agg(
            Variation_moyenne=("Variation", "mean"),
            Titres=("Variation", "count"),
            En_hausse=("Variation", lambda s: int((s > 0).sum())),
            En_baisse=("Variation", lambda s: int((s < 0).sum())),
        )
        .reset_index()
        .sort_values("Variation_moyenne", ascending=False)
    )
    return grouped


def _market_snapshot(market: pd.DataFrame) -> dict[str, Any]:
    if market.empty or "Variation" not in market.columns:
        return {}
    variation = pd.to_numeric(market["Variation"], errors="coerce")
    up = int((variation > 0).sum())
    down = int((variation < 0).sum())
    unchanged = int((variation == 0).sum())
    avg = float(variation.mean()) if variation.notna().any() else np.nan
    median = float(variation.median()) if variation.notna().any() else np.nan
    top = market.assign(_var=variation).nlargest(5, "_var")
    bottom = market.assign(_var=variation).nsmallest(5, "_var")
    sectors = _sector_table(market)
    return {
        "up": up,
        "down": down,
        "unchanged": unchanged,
        "avg": avg,
        "median": median,
        "top": top,
        "bottom": bottom,
        "sectors": sectors,
    }


def _render_top_rows(rows: pd.DataFrame, limit: int = 5) -> str:
    if rows is None or rows.empty:
        return "- N/D"
    lines: list[str] = []
    for _, row in rows.head(limit).iterrows():
        ticker = _as_text(row.get("Ticker", row.get("Symbol", "N/D")))
        name = _as_text(row.get("Nom", ""), "")
        variation = _pct(row.get("Variation"))
        sector = _as_text(row.get("Secteur", ""), "")
        label = f"**{ticker}**"
        if name:
            label += f" — {name}"
        meta = f"{variation}"
        if sector:
            meta += f" · {sector}"
        lines.append(f"- {label} : {meta}")
    return "\n".join(lines)


def _deep_market_answer(market: pd.DataFrame) -> str:
    snap = _market_snapshot(market)
    if not snap:
        return "Je n’ai pas assez de données de marché pour produire une lecture fiable."
    sectors = snap.get("sectors", pd.DataFrame())
    best_sector = sectors.iloc[0] if isinstance(sectors, pd.DataFrame) and not sectors.empty else None
    worst_sector = sectors.iloc[-1] if isinstance(sectors, pd.DataFrame) and not sectors.empty else None

    answer = [
        "## Lecture approfondie du marché",
        f"Le mouvement moyen de l’univers actif est de **{_pct(snap.get('avg'))}**, avec une médiane de **{_pct(snap.get('median'))}**.",
        f"La largeur de marché montre **{snap.get('up', 0)} titres en hausse**, **{snap.get('down', 0)} en baisse** et **{snap.get('unchanged', 0)} stables.",
    ]
    if best_sector is not None and worst_sector is not None:
        answer.append(
            f"Le secteur le plus robuste est **{best_sector.get('Secteur', 'N/D')}** ({_pct(best_sector.get('Variation_moyenne'))}), "
            f"tandis que le secteur le plus faible est **{worst_sector.get('Secteur', 'N/D')}** ({_pct(worst_sector.get('Variation_moyenne'))})."
        )
    answer.extend(
        [
            "\n### Ce qui porte le marché",
            _render_top_rows(snap.get("top"), 5),
            "\n### Ce qui pèse sur le marché",
            _render_top_rows(snap.get("bottom"), 5),
            "\n### Interprétation",
            "- Si la baisse moyenne est plus forte que la médiane, le marché est probablement tiré vers le bas par quelques titres ou secteurs lourds.",
            "- Si la majorité des titres baisse en même temps, la faiblesse est plus large et donc plus significative.",
            "- Un secteur positif dans un marché négatif peut indiquer une rotation défensive ou thématique plutôt qu’un appétit général pour le risque.",
            "\n### À vérifier ensuite",
            "- comparer la performance par secteur avec le volume relatif ;",
            "- regarder si les banques, l’énergie ou les matériaux expliquent une part disproportionnée du mouvement ;",
            "- ouvrir les titres extrêmes en Mode Focus pour distinguer bruit de séance et changement de tendance.",
        ]
    )
    return "\n".join(answer)


def _stock_answer(question: str, market: pd.DataFrame, ticker: str) -> str:
    row = _row_for_ticker(market, ticker)
    if row is None:
        return f"Je n’ai pas trouvé **{ticker}** dans l’univers actif. Essaie avec le symbole exact utilisé par Anatole."
    stock = _snapshot_from_row(row)
    observations = _trend_reading(stock)

    sector_peers = pd.DataFrame()
    if "Secteur" in market.columns and "Variation" in market.columns and stock.sector != "N/D":
        sector_peers = market[market["Secteur"].astype(str).eq(stock.sector)].copy()
        if not sector_peers.empty:
            sector_peers["Variation"] = pd.to_numeric(sector_peers["Variation"], errors="coerce")
            sector_peers = sector_peers.sort_values("Variation", ascending=False)

    lines = [
        f"## Analyse approfondie — {stock.ticker}",
        f"**{stock.name}** · Secteur : **{stock.sector}**",
        "\n### Résumé exécutif",
        f"- Prix observé : **{_money(stock.price)}**.",
        f"- Variation de séance : **{_pct(stock.change)}**.",
        f"- RSI 14 : **{_num(stock.rsi, 1)}**.",
        f"- Rendement du dividende : **{_pct(stock.dividend_yield, 2, signed=False)}**.",
        f"- P/E observé : **{_num(stock.pe, 1)}**.",
        f"- Bêta : **{_num(stock.beta, 2)}**.",
        "\n### Lecture technique",
    ]
    lines.extend(f"- {obs}." for obs in observations)
    lines.extend(
        [
            "\n### Lecture fondamentale rapide",
            f"- Capitalisation : **{_compact_money(row.get('MarketCap'))}**.",
            f"- Dividende : **{_pct(stock.dividend_yield, 2, signed=False)}** ; à comparer avec la stabilité des bénéfices et le payout ratio si disponible.",
            f"- Valorisation : P/E de **{_num(stock.pe, 1)}**, à interpréter relativement au secteur et au cycle des taux.",
        ]
    )
    if not sector_peers.empty:
        sector_avg = pd.to_numeric(sector_peers["Variation"], errors="coerce").mean()
        rank = int((sector_peers["Variation"] > stock.change).sum() + 1) if not np.isnan(stock.change) else None
        lines.extend(
            [
                "\n### Position dans son secteur",
                f"- Secteur : **{stock.sector}**.",
                f"- Variation moyenne du secteur : **{_pct(sector_avg)}**.",
            ]
        )
        if rank:
            lines.append(f"- Rang indicatif dans le secteur aujourd’hui : **{rank}/{len(sector_peers)}**.")
        lines.append("- Meilleurs comparables du secteur :")
        lines.append(_render_top_rows(sector_peers.head(5), 5))
    lines.extend(
        [
            "\n### Scénarios à surveiller",
            "- **Scénario constructif** : le titre surperforme son secteur avec volume confirmé et amélioration de la largeur de marché.",
            "- **Scénario neutre** : le mouvement reste surtout lié au secteur ou au marché global, sans catalyseur propre au titre.",
            "- **Scénario fragile** : le titre baisse plus vite que ses pairs, casse ses moyennes importantes ou réagit mal aux nouvelles.",
            "\n### Limites",
            "Cette lecture utilise les données disponibles dans Anatole. Elle ne remplace pas une analyse complète des états financiers, des communiqués officiels et des dépôts réglementaires.",
        ]
    )
    return "\n".join(lines)


def _compare_answer(market: pd.DataFrame, tickers: list[str]) -> str:
    rows = []
    for ticker in tickers[:4]:
        row = _row_for_ticker(market, ticker)
        if row is not None:
            s = _snapshot_from_row(row)
            rows.append(
                {
                    "Ticker": s.ticker,
                    "Nom": s.name,
                    "Secteur": s.sector,
                    "Prix": _money(s.price),
                    "Variation": _pct(s.change),
                    "RSI14": _num(s.rsi, 1),
                    "Dividende": _pct(s.dividend_yield, 2, signed=False),
                    "P/E": _num(s.pe, 1),
                    "Bêta": _num(s.beta, 2),
                }
            )
    if len(rows) < 2:
        return "Je peux comparer plusieurs titres si tu mentionnes au moins deux symboles présents dans l’univers actif, par exemple `RY vs TD`."
    df = pd.DataFrame(rows)
    md = df.to_markdown(index=False)
    return (
        "## Comparaison multi-titres\n\n"
        + md
        + "\n\n### Lecture\n"
        + "- Compare d’abord le secteur : deux titres de secteurs différents ne réagissent pas aux mêmes facteurs macro.\n"
        + "- Observe ensuite la variation et le RSI : un titre fort avec RSI très élevé peut être plus vulnérable à une prise de profits.\n"
        + "- Le dividende et le P/E donnent un angle de valorisation, mais ils doivent être confirmés avec les résultats, le bilan et la guidance."
    )


def _portfolio_answer(portfolio: pd.DataFrame | None, market: pd.DataFrame) -> str:
    if portfolio is None or portfolio.empty:
        return (
            "Je n’ai pas encore assez d’information sur ton portefeuille dans Anatole. "
            "Ajoute des positions pour obtenir une analyse de concentration, d’exposition sectorielle et de risque."
        )
    df = portfolio.copy()
    value_col = _get_col(df, "Valeur", "MarketValue", "value", "Montant")
    ticker_col = _get_col(df, "Ticker", "Symbole", "Symbol")
    if value_col:
        df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
        total = df[value_col].sum()
        if total and np.isfinite(total):
            df["Poids"] = df[value_col] / total * 100
    else:
        total = np.nan
    answer = ["## Analyse du portefeuille", f"Valeur suivie : **{_compact_money(total)}**."]
    if ticker_col and "Poids" in df.columns:
        top = df.sort_values("Poids", ascending=False).head(8)
        answer.append("\n### Concentration")
        for _, row in top.iterrows():
            answer.append(f"- **{row.get(ticker_col)}** : {_pct(row.get('Poids'), 2, signed=False)} du portefeuille.")
        top_weight = float(top["Poids"].head(3).sum()) if not top.empty else np.nan
        answer.append(f"Les trois premières positions représentent environ **{_pct(top_weight, 2, signed=False)}**.")
    if ticker_col and not market.empty and "Secteur" in market.columns:
        m = market.copy()
        m["_ticker_norm"] = _ticker_series(m)
        df["_ticker_norm"] = df[ticker_col].fillna("").astype(str).str.upper().str.replace(".TO", "", regex=False)
        merged = df.merge(m[["_ticker_norm", "Secteur"]], on="_ticker_norm", how="left")
        if "Poids" in merged.columns and merged["Secteur"].notna().any():
            sectors = merged.groupby("Secteur")["Poids"].sum().sort_values(ascending=False)
            answer.append("\n### Exposition sectorielle")
            for sector, weight in sectors.head(8).items():
                answer.append(f"- **{sector}** : {_pct(weight, 2, signed=False)}.")
    answer.extend(
        [
            "\n### Risques à surveiller",
            "- concentration excessive sur quelques titres ou un seul secteur ;",
            "- titres fortement corrélés, notamment banques, énergie ou matériaux ;",
            "- exposition aux taux d’intérêt, au dollar canadien et aux matières premières ;",
            "- absence de diversification géographique si le portefeuille est principalement canadien.",
            "\n### Prochaine étape utile",
            "Demande par exemple : `Quels sont les 3 risques principaux de mon portefeuille ?` ou `Quel secteur domine mon portefeuille ?`."
        ]
    )
    return "\n".join(answer)


def _news_answer(news: pd.DataFrame | None, watchlist: list[str] | None = None) -> str:
    if news is None or news.empty:
        return "Je n’ai pas de manchettes exploitables dans le contexte actuel. Essaie avec un titre précis ou ajoute des titres à ta liste."
    cols = {c.lower(): c for c in news.columns}
    ticker_col = cols.get("ticker") or cols.get("symbole")
    title_col = cols.get("titre") or cols.get("title")
    sentiment_col = cols.get("sentiment")
    category_col = cols.get("categorie") or cols.get("catégorie")
    lines = ["## Synthèse des actualités", "Voici les éléments les plus utiles à vérifier :"]
    for _, row in news.head(12).iterrows():
        ticker = _as_text(row.get(ticker_col), "") if ticker_col else ""
        title = _as_text(row.get(title_col), "Sans titre") if title_col else "Sans titre"
        sentiment = _as_text(row.get(sentiment_col), "") if sentiment_col else ""
        category = _as_text(row.get(category_col), "") if category_col else ""
        prefix = f"**{ticker}** — " if ticker else ""
        suffix = ""
        if sentiment or category:
            suffix = f" · {category} {sentiment}".strip()
        lines.append(f"- {prefix}{title}{suffix}")
    lines.extend(
        [
            "\n### Lecture",
            "- Une manchette isolée ne suffit pas : il faut vérifier si le marché réagit avec volume et si le secteur confirme le mouvement.",
            "- Les nouvelles les plus importantes sont celles qui changent les bénéfices attendus, le bilan, la réglementation, les marges ou la trajectoire des taux.",
        ]
    )
    return "\n".join(lines)


def _rank_answer(question: str, market: pd.DataFrame) -> str:
    q = question.lower()
    df = market.copy()
    if "rsi" in q and "RSI14" in df.columns:
        df["RSI14"] = pd.to_numeric(df["RSI14"], errors="coerce")
        if "surachet" in q or "70" in q or "élev" in q:
            rows = df[df["RSI14"] >= 70].sort_values("RSI14", ascending=False)
            title = "Titres avec RSI élevé"
        else:
            rows = df[df["RSI14"] <= 30].sort_values("RSI14")
            title = "Titres avec RSI faible"
        if rows.empty:
            return f"Aucun titre ne ressort clairement dans la catégorie demandée ({title.lower()})."
        return "## " + title + "\n\n" + "\n".join(
            f"- **{row.get('Ticker', 'N/D')}** — {_as_text(row.get('Nom', ''))} : RSI **{_num(row.get('RSI14'), 1)}**, variation **{_pct(row.get('Variation'))}**"
            for _, row in rows.head(15).iterrows()
        )
    if "divid" in q and "DividendYield" in df.columns:
        df["DividendYield"] = pd.to_numeric(df["DividendYield"], errors="coerce")
        rows = df.dropna(subset=["DividendYield"]).sort_values("DividendYield", ascending=False).head(15)
        return "## Titres avec rendement du dividende élevé\n\n" + "\n".join(
            f"- **{row.get('Ticker', 'N/D')}** — {_as_text(row.get('Nom', ''))} : **{_pct(row.get('DividendYield'), 2, signed=False)}**"
            for _, row in rows.iterrows()
        ) + "\n\nUn rendement élevé doit être validé avec la solidité du bilan, le payout ratio et la stabilité des flux de trésorerie."
    if any(term in q for term in ["hausse", "gagnant", "fort", "surperformance"]):
        rows = df.copy()
        rows["Variation"] = pd.to_numeric(rows.get("Variation"), errors="coerce")
        return "## Principales hausses\n\n" + _render_top_rows(rows.nlargest(15, "Variation"), 15)
    if any(term in q for term in ["baisse", "perdant", "faible", "sous-performance"]):
        rows = df.copy()
        rows["Variation"] = pd.to_numeric(rows.get("Variation"), errors="coerce")
        return "## Principales baisses\n\n" + _render_top_rows(rows.nsmallest(15, "Variation"), 15)
    return ""


def build_context(
    market: pd.DataFrame | None = None,
    portfolio: pd.DataFrame | None = None,
    watchlist: list[str] | None = None,
    news: pd.DataFrame | None = None,
    question: str | None = None,
    analysis_depth: str = "Approfondi",
) -> str:
    """Build a compact but decision-useful context for the language model.

    The function stays intentionally text-based so it remains stable on Render and
    does not require any external dependency beyond pandas.
    """
    market = _clean_market(market)
    blocks: list[str] = []
    blocks.append(
        "RÈGLES DE RÉPONSE\n"
        "- Répondre en français, avec un niveau analyste senior.\n"
        "- Ne jamais donner de recommandation personnalisée d'achat ou de vente.\n"
        "- Séparer faits, interprétations, risques, scénarios et limites.\n"
        "- Être concret : citer les titres, les secteurs et les chiffres disponibles.\n"
        "- Quand une donnée manque, le dire clairement et proposer une vérification.\n"
        f"- Profondeur demandée : {analysis_depth}."
    )
    if question:
        blocks.append(f"QUESTION UTILISATEUR\n{question}")
    if market is not None and not market.empty:
        snap = _market_snapshot(market)
        blocks.append(
            "SYNTHÈSE MARCHÉ\n"
            f"Titres en hausse={snap.get('up', 'N/D')}; titres en baisse={snap.get('down', 'N/D')}; "
            f"variation moyenne={snap.get('avg', 'N/D')}; variation médiane={snap.get('median', 'N/D')}"
        )
        sectors = snap.get("sectors", pd.DataFrame())
        if isinstance(sectors, pd.DataFrame) and not sectors.empty:
            blocks.append("SECTEURS\n" + sectors.head(12).to_csv(index=False))
        cols = _available_columns(market)
        if cols:
            blocks.append("TABLEAU MARCHÉ\n" + market[cols].head(120).to_csv(index=False))
        tickers = _extract_tickers(question or "", market)
        if tickers:
            rows = []
            for ticker in tickers:
                row = _row_for_ticker(market, ticker)
                if row is not None:
                    rows.append(row)
            if rows:
                detail = pd.DataFrame(rows)
                detail_cols = _available_columns(detail)
                blocks.append("TITRES MENTIONNÉS\n" + detail[detail_cols].to_csv(index=False))
    if portfolio is not None and not portfolio.empty:
        blocks.append("PORTEFEUILLE\n" + portfolio.head(80).to_csv(index=False))
    if watchlist:
        blocks.append("LISTE DE SUIVI\n" + ", ".join(str(x) for x in watchlist[:60]))
    if news is not None and not news.empty:
        cols = [c for c in ["Ticker", "Titre", "Categorie", "Catégorie", "Sentiment", "Resume", "Résumé", "Source"] if c in news.columns]
        if cols:
            blocks.append("ACTUALITÉS\n" + news[cols].head(40).to_csv(index=False))
    return "\n\n".join(blocks)


def suggested_questions() -> dict[str, list[str]]:
    return {
        "Marché": [
            "Pourquoi le marché bouge aujourd’hui ? Donne-moi les secteurs et titres qui expliquent le mouvement.",
            "Est-ce que la baisse actuelle est large ou concentrée dans quelques secteurs ?",
            "Quels titres tirent le plus le TSX vers le haut ou vers le bas ?",
        ],
        "Titre": [
            "Analyse RY en profondeur : technique, secteur, risques, scénarios et limites.",
            "Compare RY et TD avec les données disponibles.",
            "Quels signaux me disent qu’un titre est fort mais potentiellement étiré ?",
        ],
        "Portefeuille": [
            "Quels sont les risques principaux de mon portefeuille ?",
            "Quel secteur domine mon portefeuille et que dois-je surveiller ?",
            "Mon portefeuille est-il trop concentré selon les données disponibles ?",
        ],
        "Recherche": [
            "Quels titres ont un RSI inférieur à 30 et méritent une vérification ?",
            "Quels titres ont les rendements de dividende les plus élevés ?",
            "Résume les nouvelles importantes de ma liste de suivi.",
        ],
        "Terminal Pro": [
            "Donne-moi le radar institutionnel Anatole avec les meilleurs profils et les fragilités.",
            "Quelles dislocations méritent une vérification aujourd’hui ?",
            "Explique le score Anatole et la rotation sectorielle comme un comité d’investissement.",
        ],
    }




def _premium_terminal_answer(question: str, market: pd.DataFrame) -> str:
    try:
        from core.intelligence_engine import build_institutional_brief, explain_ticker, score_titles

        tickers = _extract_tickers(question, market)
        if tickers:
            return explain_ticker(market, tickers[0])
        brief = build_institutional_brief(market)
        scored = score_titles(market)
        if scored.empty:
            return brief
        leaders = scored.head(5)
        pressure = scored.sort_values("Score Anatole", ascending=True).head(5)
        lines = [brief, "", "## Lecture supplémentaire — Radar premium", "", "### Profils les plus solides statistiquement"]
        for _, row in leaders.iterrows():
            lines.append(
                f"- **{row.get('Ticker')}** · score {_num(row.get('Score Anatole'), 1)}/100 · {row.get('Catégorie')} · {row.get('Lecture Anatole')}"
            )
        lines.append("\n### Profils les plus fragiles à vérifier")
        for _, row in pressure.iterrows():
            lines.append(
                f"- **{row.get('Ticker')}** · score {_num(row.get('Score Anatole'), 1)}/100 · {row.get('Risque principal')} · {row.get('Points à vérifier')}"
            )
        lines.append("\n**Lecture Anatole :** ce classement sert à prioriser les vérifications, pas à recommander une transaction.")
        return "\n".join(lines)
    except Exception:
        return _deep_market_answer(market)


def local_answer(
    question: str,
    market: pd.DataFrame | None,
    portfolio: pd.DataFrame | None = None,
    watchlist: list[str] | None = None,
    news: pd.DataFrame | None = None,
    analysis_depth: str = "Approfondi",
) -> str:
    market = _clean_market(market)
    q = question.lower().strip()
    if market is None or market.empty:
        return "Les données de marché ne sont pas disponibles pour le moment. Essaie de relancer l’analyse ou de poser une question plus ciblée."

    if any(term in q for term in ["terminal", "radar", "score anatole", "dislocation", "institutionnel", "conviction", "meilleurs profils", "profils solides", "comité"]):
        return _premium_terminal_answer(question, market)

    tickers = _extract_tickers(question, market)
    if len(tickers) >= 2 and any(term in q for term in ["compare", "compar", " vs ", "contre"]):
        return _compare_answer(market, tickers)
    if tickers:
        return _stock_answer(question, market, tickers[0])
    if any(term in q for term in ["marché", "bouge", "secteur", "largeur", "pourquoi", "tsx"]):
        return _deep_market_answer(market)
    if any(term in q for term in ["portefeuille", "position", "concentration", "risque"]):
        return _portfolio_answer(portfolio, market)
    if any(term in q for term in ["nouvelle", "news", "actualité", "manchette", "watchlist", "liste"]):
        return _news_answer(news, watchlist)
    ranked = _rank_answer(question, market)
    if ranked:
        return ranked
    return (
        "## Analyse disponible\n"
        "Je peux produire une analyse détaillée sur le marché, un titre, une comparaison, les secteurs, les dividendes, le RSI, les nouvelles ou le portefeuille.\n\n"
        "Exemples efficaces :\n"
        "- `Pourquoi le marché bouge aujourd’hui ?`\n"
        "- `Analyse RY en profondeur`\n"
        "- `Compare RY et TD`\n"
        "- `Quels titres ont un RSI inférieur à 30 ?`\n"
        "- `Quels sont les risques principaux de mon portefeuille ?`"
    )


def ask_openai(
    question: str,
    context: str,
    api_key: str,
    model: str,
    analysis_depth: str = "Approfondi",
) -> str:
    from openai import OpenAI

    depth_instruction = {
        "Rapide": "Réponse concise, prioriser les 5 points les plus utiles.",
        "Approfondi": "Réponse structurée et détaillée, avec chiffres, secteurs, scénarios et limites.",
        "Comité d’investissement": "Réponse très approfondie, niveau comité d’investissement : thèse, contre-thèse, facteurs macro, risques, scénarios, signaux à confirmer et limites."
    }.get(analysis_depth, "Réponse structurée et détaillée.")

    prompt = f"""
Tu es Anatole, assistant d'analyse financière spécialisé dans le marché canadien.
Tu dois répondre avec un niveau d'analyse exceptionnel, comparable à un analyste senior qui prépare une note pour un investisseur sérieux.

Contraintes :
- Réponds en français.
- Ne formule pas de recommandation personnalisée d'achat, de vente ou de conservation.
- Distingue clairement : faits observés, interprétations, risques, scénarios et limites.
- Utilise seulement les données fournies dans le contexte. Si une donnée manque, dis-le.
- Donne des chiffres précis quand ils sont disponibles.
- Priorise le TSX, les secteurs, la largeur de marché, les titres moteurs, la watchlist et le portefeuille si présents.
- Termine par une courte section "À vérifier ensuite".

Niveau de profondeur : {analysis_depth}
Instruction de profondeur : {depth_instruction}

QUESTION
{question}

CONTEXTE ANATOLE
{context}
"""
    client = OpenAI(api_key=api_key)
    response = client.responses.create(model=model, input=prompt)
    return response.output_text
