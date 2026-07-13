from __future__ import annotations

import re

import streamlit as st

from core.analytics import enrich_news, portfolio_table
from core.assistant_context import (
    ask_openai,
    build_context,
    local_answer,
    suggested_questions,
)
from core.data import fetch_news_bundle
from core.database import get_positions, get_watchlist
from core.rate_limit import consume
from core.runtime import load_technical_bundle
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context
from core.utils import get_secret


configure_page("Assistant", "💬")
apply_style()
profile = sidebar_context()
page_header(
    "Assistant contextuel",
    "Pose une question sur le marché, un titre, ta liste, ton portefeuille ou les nouvelles. Anatole prépare une réponse structurée à partir des données disponibles.",
)

st.caption(
    "Objectif : transformer les données d’Anatole en lecture claire. Les réponses sont informatives et ne constituent pas une recommandation personnalisée."
)

if "assistant_messages" not in st.session_state:
    st.session_state.assistant_messages = [
        {
            "role": "assistant",
            "content": (
                "Bonjour. Je peux analyser le marché, expliquer les mouvements sectoriels, "
                "comparer des titres, résumer les nouvelles et relever les risques d’un portefeuille."
            ),
        }
    ]

if "assistant_prefill" not in st.session_state:
    st.session_state.assistant_prefill = ""

with st.container(border=True):
    c1, c2 = st.columns([1, 1])
    with c1:
        analysis_depth = st.selectbox(
            "Profondeur d’analyse",
            ["Rapide", "Approfondi", "Comité d’investissement"],
            index=1,
            help="Le mode approfondi donne plus de contexte, de scénarios et de limites.",
        )
    with c2:
        include_news = st.toggle(
            "Inclure les nouvelles disponibles",
            value=True,
            help="Ajoute les manchettes disponibles pour la liste de suivi et les titres mentionnés.",
        )

with st.expander("Questions puissantes à essayer", expanded=False):
    question_groups = suggested_questions()
    tabs = st.tabs(list(question_groups.keys()))
    for tab, (_, questions) in zip(tabs, question_groups.items()):
        with tab:
            for index, suggestion in enumerate(questions):
                if st.button(suggestion, key=f"assistant_suggestion_{index}_{suggestion[:20]}", use_container_width=True):
                    st.session_state.assistant_prefill = suggestion
                    st.rerun()

for message in st.session_state.assistant_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prefill = st.session_state.get("assistant_prefill", "")
question = st.chat_input("Pose une question précise : ex. Pourquoi le marché bouge ? Analyse RY. Compare RY et TD.")
if not question and prefill:
    question = prefill
    st.session_state.assistant_prefill = ""


def _tickers_from_question(text: str) -> list[str]:
    tokens = re.findall(r"\b[A-Z][A-Z0-9.\-]{1,9}\b", text.upper())
    ignored = {"TSX", "ETF", "IPO", "RSI", "SMA", "CAD", "USD", "PE", "IA", "AI"}
    result: list[str] = []
    for token in tokens:
        token = token.replace(".TO", "")
        if token not in ignored and token not in result:
            result.append(token)
    return result[:8]


if question:
    allowed, wait_seconds = consume(
        "assistant_question",
        max_calls=8,
        window_seconds=600,
    )
    if not allowed:
        st.warning(
            f"Beaucoup de questions ont été envoyées récemment. Réessaie dans environ {wait_seconds} secondes."
        )
        footer()
        st.stop()

    st.session_state.assistant_messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Analyse des données disponibles…"):
            try:
                constituents, diagnostics, market, features = load_technical_bundle()
                watchlist = get_watchlist(profile)
                positions = get_positions(profile)
                portfolio = portfolio_table(positions, market, constituents)

                news = None
                if include_news:
                    mentioned = _tickers_from_question(question)
                    tickers_for_news = list(dict.fromkeys(mentioned + list(watchlist[:8])))[:12]
                    if tickers_for_news:
                        news = enrich_news(fetch_news_bundle(tuple(tickers_for_news)))

                api_key = get_secret("OPENAI_API_KEY")
                model = get_secret("OPENAI_MODEL", "gpt-5.5")
                if api_key:
                    context = build_context(
                        features,
                        portfolio,
                        watchlist,
                        news,
                        question=question,
                        analysis_depth=analysis_depth,
                    )
                    answer = ask_openai(
                        question,
                        context,
                        api_key,
                        model,
                        analysis_depth=analysis_depth,
                    )
                else:
                    answer = local_answer(
                        question,
                        features,
                        portfolio=portfolio,
                        watchlist=watchlist,
                        news=news,
                        analysis_depth=analysis_depth,
                    )
            except Exception:
                answer = (
                    "Je n’ai pas pu préparer une analyse complète avec les données disponibles. "
                    "Réessaie dans quelques instants ou pose une question plus ciblée sur un titre, un secteur ou le portefeuille."
                )
        st.markdown(answer)

    st.session_state.assistant_messages.append({"role": "assistant", "content": answer})

with st.expander("Ce que l’assistant sait analyser", expanded=False):
    st.markdown(
        """
- **Marché** : largeur, secteurs forts/faibles, titres moteurs, lecture de séance.
- **Titre spécifique** : technique, secteur, valorisation simple, dividende, scénarios et limites.
- **Comparaison** : plusieurs titres côte à côte avec les métriques disponibles.
- **Portefeuille** : concentration, exposition sectorielle et risques dominants.
- **Nouvelles** : synthèse des manchettes disponibles dans Anatole.
"""
    )

footer()
