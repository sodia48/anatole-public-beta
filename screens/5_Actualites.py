from __future__ import annotations

import pandas as pd
import streamlit as st

from core.ai import summarize_news_in_french
from core.analytics import enrich_news
from core.data import fetch_news_bundle, load_constituents
from core.device import mobile_is_lite, mobile_page_limit
from core.performance import load_timer, perf_caption
from core.universe import current_universe
from core.database import get_watchlist
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context
from core.utils import get_secret

configure_page("Actualités", "📰")
apply_style()
profile = sidebar_context()
page_header(
    "Actualités et sentiment",
    "Agrège les manchettes sans surcharger le serveur. Les fils avancés sont limités pour éviter les erreurs 502.",
    "📰",
)

constituents, diagnostics = load_constituents()
lookup = dict(zip(constituents["YahooTicker"], constituents["Ticker"] + " — " + constituents["Nom"]))
watchlist = [ticker for ticker in get_watchlist(profile) if ticker in lookup]
defaults = watchlist[:3] or constituents["YahooTicker"].head(3 if mobile_is_lite() else 4).tolist()
selected = st.multiselect(
    "Titres à surveiller (maximum 4)",
    constituents["YahooTicker"].tolist(),
    default=defaults,
    max_selections=4,
    format_func=lambda value: lookup.get(value, value),
    help="Limité volontairement pour éviter les délais réseau et les erreurs 502.",
)
st.caption(
    f"Univers actif : {current_universe().short_label}. "
    "Les nouvelles sont récupérées avec un délai maximal afin de garder Anatole disponible."
)

if not selected:
    st.info("Sélectionne au moins un titre.")
    footer()
    st.stop()

try:
    with st.spinner("Collecte des nouvelles..."):
        with load_timer("actualites"):
            articles = fetch_news_bundle(tuple(selected))
except Exception:
    articles = []
    st.warning(
        "La source d'actualités est temporairement lente ou indisponible. "
        "Réessaie dans quelques minutes ou réduis la sélection de titres."
    )

perf_caption("actualites", threshold=2.5)
news = enrich_news(articles)

if news.empty:
    st.warning("Aucune manchette retournée pour la sélection.")
    footer()
    st.stop()

filter1, filter2, filter3 = st.columns(3)
with filter1:
    sentiments = st.multiselect("Sentiment", ["Positif", "Neutre", "Négatif"], default=["Positif", "Neutre", "Négatif"])
with filter2:
    categories = sorted(news["Categorie"].unique().tolist())
    selected_categories = st.multiselect("Catégories", categories, default=categories)
with filter3:
    importance = st.multiselect("Importance", ["Élevée", "Normale"], default=["Élevée", "Normale"])

filtered = news[
    news["Sentiment"].isin(sentiments)
    & news["Categorie"].isin(selected_categories)
    & news["Importance"].isin(importance)
].copy()

average_score = filtered["SentimentScore"].mean() * 100 if not filtered.empty else 0
positive_share = (filtered["Sentiment"] == "Positif").mean() * 100 if not filtered.empty else 0
negative_share = (filtered["Sentiment"] == "Négatif").mean() * 100 if not filtered.empty else 0
if not filtered.empty and "DateParsed" in filtered:
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)
    recent_7d = filtered[filtered["DateParsed"] >= cutoff]
else:
    recent_7d = pd.DataFrame()
sentiment_7d = recent_7d["SentimentScore"].mean() * 100 if not recent_7d.empty else 0
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Manchettes uniques", len(filtered))
m2.metric("Score moyen", f"{average_score:+.0f}/100")
m3.metric("Sentiment 7 jours", f"{sentiment_7d:+.0f}/100")
m4.metric("Part positive", f"{positive_share:.0f}%")
m5.metric("Part négative", f"{negative_share:.0f}%")

st.subheader("Répartition par catégorie")
category_table = filtered.groupby(["Categorie", "Sentiment"]).size().unstack(fill_value=0)
st.bar_chart(category_table)

st.subheader("Fil d'actualité")
for _, article in filtered.head(mobile_page_limit(40, 18)).iterrows():
    with st.container(border=True):
        st.markdown(f"**[{article['Titre']}]({article['URL']})**")
        st.caption(
            f"{article['Ticker']} · {article['Source']} · {article['Categorie']} · "
            f"{article['Sentiment']} ({article['SentimentScore']:+.2f}) · {article['Date']}"
        )
        if article.get("Resume"):
            st.write(article["Resume"])

st.subheader("Synthèse du fil")
if filtered.empty:
    st.write("Aucune manchette ne correspond aux filtres actuels.")
else:
    dominant_category = filtered["Categorie"].value_counts().index[0]
    dominant_sentiment = filtered["Sentiment"].value_counts().index[0]
    st.write(
        f"Le fil contient **{len(filtered)} manchettes**. La catégorie dominante est "
        f"**{dominant_category}** et le sentiment le plus fréquent est **{dominant_sentiment.lower()}**. "
        f"Le score moyen est de **{average_score:+.0f}/100**."
    )

openai_key = get_secret("OPENAI_API_KEY")
if openai_key:
    model = get_secret("OPENAI_MODEL", "gpt-5.5")
    if st.button("Approfondir la synthèse", type="primary"):
        try:
            with st.spinner("Génération de la synthèse..."):
                st.session_state["news_ai_summary"] = summarize_news_in_french(
                    filtered,
                    openai_key,
                    model,
                )
        except Exception:
            st.error(
                "La synthèse avancée est temporairement indisponible. "
                "Le fil local reste accessible."
            )
    if st.session_state.get("news_ai_summary"):
        st.markdown(st.session_state["news_ai_summary"])

st.download_button(
    "Télécharger les nouvelles analysées",
    filtered.drop(columns=["DateParsed"], errors="ignore").to_csv(index=False).encode("utf-8-sig"),
    file_name=f"actualites_{current_universe().short_label.lower().replace(' ', '_')}.csv",
    mime="text/csv",
)

footer()
