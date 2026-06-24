from __future__ import annotations

from typing import Any

import pandas as pd


def summarize_news_in_french(
    news: pd.DataFrame,
    api_key: str,
    model: str = "gpt-5.5",
) -> str:
    from openai import OpenAI

    if news.empty:
        return "Aucune nouvelle à résumer."
    lines = []
    for _, article in news.head(20).iterrows():
        lines.append(
            f"- {article.get('Ticker', '')}: {article.get('Titre', '')} | "
            f"catégorie={article.get('Categorie', '')} | sentiment={article.get('Sentiment', '')} | "
            f"résumé source={article.get('Resume', '')}"
        )
    prompt = """
Tu es un analyste de marchés canadien. Produis en français une synthèse concise et équilibrée
à partir des manchettes fournies. Ne donne aucune recommandation personnalisée.

Structure :
1. Résumé général en 5 à 8 phrases
2. Catalyseurs positifs
3. Risques et éléments négatifs
4. Entreprises les plus concernées
5. Limites : précise que l'analyse repose seulement sur les manchettes disponibles

Manchettes :
""" + "\n".join(lines)
    client = OpenAI(api_key=api_key)
    response = client.responses.create(model=model, input=prompt)
    return response.output_text


def analyze_stock_in_french(
    ticker: str,
    company_name: str,
    market_data: dict[str, Any],
    fundamentals: dict[str, Any],
    technical: dict[str, Any],
    news: pd.DataFrame,
    api_key: str,
    model: str = "gpt-5.5",
) -> str:
    from openai import OpenAI

    headlines = "\n".join(
        f"- {row.get('Titre', '')} ({row.get('Source', '')})"
        for _, row in news.head(8).iterrows()
    ) or "- Aucune manchette disponible"
    prompt = f"""
Analyse {ticker} ({company_name}) en français à partir des données fournies.
Ne formule aucune recommandation personnalisée d'achat ou de vente. Sépare les faits,
les interprétations et les limites. Mentionne que les cotations peuvent être différées.

Marché : {market_data}
Fondamentaux : {fundamentals}
Technique : {technical}
Actualités :
{headlines}

Structure : résumé exécutif, technique, fondamentaux, catalyseurs, risques,
scénarios haussier/central/baissier et limites.
"""
    client = OpenAI(api_key=api_key)
    response = client.responses.create(model=model, input=prompt)
    return response.output_text
