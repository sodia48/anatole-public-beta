from __future__ import annotations

import streamlit as st

from core.analytics import enrich_news, portfolio_table
from core.assistant_context import ask_openai, build_context, local_answer
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
    "Assistant financier",
    "Le contexte de marché, le portefeuille et les actualités sont chargés seulement lorsque tu poses une question.",
)

suggestions = [
    "Quelles actions du TSX 60 ont un RSI inférieur à 30 ?",
    "Quelles sont les principales hausses aujourd'hui ?",
    "Quels titres ont les dividendes les plus élevés ?",
    "Quels risques vois-tu dans mon portefeuille ?",
    "Résume les nouvelles importantes de ma watchlist.",
]

with st.expander("Exemples de questions", expanded=False):
    for index, suggestion in enumerate(suggestions):
        if st.button(suggestion, key=f"suggestion_{index}", width="stretch"):
            st.session_state.assistant_prefill = suggestion

if "assistant_messages" not in st.session_state:
    st.session_state.assistant_messages = [
        {
            "role": "assistant",
            "content": "Bonjour. Pose une question sur le TSX 60, ta watchlist, ton portefeuille ou les actualités.",
        }
    ]

for message in st.session_state.assistant_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prefill = st.session_state.pop("assistant_prefill", "")
question = st.chat_input("Pose une question sur tes données…")
if not question and prefill:
    question = prefill

if question:
    allowed, wait_seconds = consume(
        "assistant_question",
        max_calls=5,
        window_seconds=600,
    )
    if not allowed:
        st.warning(
            f"Limite temporaire atteinte. Réessaie dans environ {wait_seconds} secondes."
        )
        footer()
        st.stop()

    st.session_state.assistant_messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Préparation du contexte…"):
            try:
                constituents, _, market, features = load_technical_bundle()
                watchlist = get_watchlist(profile)
                positions = get_positions(profile)
                portfolio = portfolio_table(positions, market, constituents)

                news = enrich_news(
                    fetch_news_bundle(tuple(watchlist[:4]))
                )

                api_key = get_secret("OPENAI_API_KEY")
                model = get_secret("OPENAI_MODEL", "gpt-5.5")
                if api_key:
                    context = build_context(features, portfolio, watchlist, news)
                    answer = ask_openai(question, context, api_key, model)
                else:
                    answer = local_answer(question, features)
            except Exception:
                answer = (
                    "Je n'ai pas pu charger toutes les données pour cette "
                    "question. Réessaie dans quelques instants ou demande "
                    "une analyse plus ciblée."
                )
        st.markdown(answer)

    st.session_state.assistant_messages.append({"role": "assistant", "content": answer})

st.caption("Le chargement des historiques et des nouvelles n'est déclenché qu'après l'envoi d'une question.")
footer()
