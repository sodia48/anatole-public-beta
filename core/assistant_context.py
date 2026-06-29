from __future__ import annotations


import pandas as pd


def build_context(
    market: pd.DataFrame | None = None,
    portfolio: pd.DataFrame | None = None,
    watchlist: list[str] | None = None,
    news: pd.DataFrame | None = None,
) -> str:
    blocks: list[str] = []
    if market is not None and not market.empty:
        cols = [c for c in ["Ticker", "Nom", "Secteur", "Prix", "Variation", "RSI14", "DividendYield", "TrailingPE"] if c in market.columns]
        blocks.append("MARCHÉ\n" + market[cols].head(60).to_csv(index=False))
    if portfolio is not None and not portfolio.empty:
        blocks.append("PORTEFEUILLE\n" + portfolio.head(50).to_csv(index=False))
    if watchlist:
        blocks.append("WATCHLIST\n" + ", ".join(watchlist))
    if news is not None and not news.empty:
        cols = [c for c in ["Ticker", "Titre", "Categorie", "Sentiment", "Resume"] if c in news.columns]
        blocks.append("ACTUALITÉS\n" + news[cols].head(30).to_csv(index=False))
    return "\n\n".join(blocks)


def local_answer(question: str, market: pd.DataFrame) -> str:
    q = question.lower()
    if market is None or market.empty:
        return "Les données de marché ne sont pas disponibles pour le moment."

    if "rsi" in q and ("30" in q or "survend" in q) and "RSI14" in market:
        rows = market[pd.to_numeric(market["RSI14"], errors="coerce") < 30].sort_values("RSI14")
        if rows.empty:
            return "Aucun titre du tableau actuel n'a un RSI inférieur à 30."
        return "Titres avec RSI inférieur à 30 :\n\n" + "\n".join(
            f"- **{row['Ticker']}** : RSI {float(row['RSI14']):.1f}" for _, row in rows.head(12).iterrows()
        )

    if "dividende" in q and "DividendYield" in market:
        rows = market.sort_values("DividendYield", ascending=False).head(10)
        return "Rendements de dividende les plus élevés :\n\n" + "\n".join(
            f"- **{row['Ticker']}** : {float(row['DividendYield']):.2f}%" for _, row in rows.iterrows() if pd.notna(row.get("DividendYield"))
        )

    if "hausse" in q or "gagnant" in q:
        rows = market.nlargest(10, "Variation")
        return "Principales hausses :\n\n" + "\n".join(
            f"- **{row['Ticker']}** : {float(row['Variation']):+.2f}%" for _, row in rows.iterrows()
        )

    if "baisse" in q or "perdant" in q:
        rows = market.nsmallest(10, "Variation")
        return "Principales baisses :\n\n" + "\n".join(
            f"- **{row['Ticker']}** : {float(row['Variation']):+.2f}%" for _, row in rows.iterrows()
        )

    return (
        "Je peux analyser les hausses, les baisses, les RSI, les dividendes, la watchlist et le portefeuille. "
        "Pose une question plus précise, par exemple sur les gagnants, les perdants ou les titres survendus."
    )


def ask_openai(question: str, context: str, api_key: str, model: str) -> str:
    from openai import OpenAI

    prompt = f"""
Tu es Anatole, assistant financier pédagogique spécialisé dans le marché canadien.
Réponds en français à la question à partir du contexte de l'application ci-dessous.
Ne donne pas de conseil financier personnalisé. Distingue faits, interprétations et limites.
Quand les données sont insuffisantes, dis-le clairement. Sois concret et structuré.

QUESTION
{question}

CONTEXTE DE L'APPLICATION
{context}
"""
    client = OpenAI(api_key=api_key)
    response = client.responses.create(model=model, input=prompt)
    return response.output_text
