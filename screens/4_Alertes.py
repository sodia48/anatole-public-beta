from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import streamlit as st

from core.analytics import evaluate_alert
from core.config import ALERT_TYPES
from core.database import (
    add_alert,
    delete_alert,
    get_alert_events,
    get_alerts,
    record_alert_trigger,
    set_alert_active,
    update_alert_value,
)
from core.rate_limit import consume
from core.runtime import load_light_market_bundle, load_technical_bundle
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context
from core.utils import get_secret, safe_float

TECHNICAL_ALERT_TYPES = {"rsi", "relative_volume", "sma_cross"}


def _needs_technical_features(alerts) -> bool:
    return not alerts.empty and alerts["alert_type"].astype(str).isin(TECHNICAL_ALERT_TYPES).any()


configure_page("Alertes", "🔔")
apply_style()
profile = sidebar_context()
page_header(
    "Alertes",
    "Surveille tes titres, tes seuils et tes signaux importants.",
    "🔔",
)

constituents, diagnostics, snapshot = load_light_market_bundle()
feature_map = snapshot.set_index("YahooTicker").to_dict(orient="index") if "YahooTicker" in snapshot else {}
lookup = dict(zip(constituents["YahooTicker"], constituents["Ticker"] + " — " + constituents["Nom"]))

with st.expander("➕ Créer une alerte", expanded=True):
    with st.form("new_alert"):
        c1, c2, c3 = st.columns(3)
        with c1:
            ticker = st.selectbox(
                "Titre",
                constituents["YahooTicker"].tolist(),
                format_func=lambda value: lookup.get(value, value),
            )
        with c2:
            alert_label = st.selectbox("Type", list(ALERT_TYPES))
        with c3:
            channel = st.selectbox("Canal", ["app", "telegram", "email"])

        alert_type = ALERT_TYPES[alert_label]
        d1, d2, d3 = st.columns(3)
        with d1:
            if alert_type == "sma_cross":
                operator = st.selectbox(
                    "Condition",
                    ["croise_hausse", "croise_baisse"],
                    format_func=lambda value: "Croisement haussier" if value == "croise_hausse" else "Croisement baissier",
                )
            else:
                operator = st.selectbox("Condition", [">", "<"], format_func=lambda value: "Au-dessus de" if value == ">" else "En-dessous de")
        current_feature = feature_map.get(ticker, {})
        current_price = safe_float(current_feature.get("Prix"))

        default_thresholds = {
            "price": 0.0 if np.isnan(current_price) else round(float(current_price), 2),
            "daily_change": 0.0,
            "rsi": 70.0 if operator == ">" else 30.0,
            "relative_volume": 1.5 if operator == ">" else 0.7,
            "sma_cross": 0.0,
        }

        threshold_help = (
            "Prérempli avec le dernier prix disponible pour éviter une alerte de prix à 0,00."
            if alert_type == "price"
            else None
        )

        with d2:
            threshold = st.number_input(
                "Seuil",
                value=float(default_thresholds.get(alert_type, 0.0)),
                step=0.1,
                format="%.2f",
                disabled=alert_type == "sma_cross",
                help=threshold_help,
                key=f"new_alert_threshold_{ticker}_{alert_type}_{operator}",
            )
        with d3:
            cooldown = st.number_input("Délai minimum entre notifications (min)", min_value=5, max_value=10_080, value=60, step=5)

        submit = st.form_submit_button("Enregistrer l'alerte", type="primary")
        if submit:
            add_alert(
                profile=profile,
                ticker=ticker,
                alert_type=alert_type,
                operator=operator,
                threshold=None if alert_type == "sma_cross" else threshold,
                channel=channel,
                cooldown_minutes=int(cooldown),
            )
            st.success("Alerte enregistrée.")
            st.rerun()

telegram_ready = bool(get_secret("TELEGRAM_BOT_TOKEN") and get_secret("TELEGRAM_CHAT_ID"))
email_ready = bool(get_secret("SMTP_HOST") and get_secret("SMTP_USERNAME") and get_secret("SMTP_PASSWORD") and get_secret("ALERT_EMAIL_TO"))
status_cols = st.columns(3)
status_cols[0].metric("Notifications dans l'app", "Prêtes")
status_cols[1].metric("Telegram", "Prêt" if telegram_ready else "À activer")
status_cols[2].metric("Courriel", "Prêt" if email_ready else "À activer")


alerts = get_alerts(profile)
if alerts.empty:
    st.info("Aucune alerte enregistrée.")
    footer()
    st.stop()

label_by_type = {value: key for key, value in ALERT_TYPES.items()}
needs_technical = _needs_technical_features(alerts)
show_live_technical = False
if needs_technical:
    show_live_technical = st.toggle(
        "Afficher les signaux détaillés",
        value=False,
        help="Affiche les derniers indicateurs disponibles pour mieux comprendre les alertes avant l’évaluation.",
    )
    if show_live_technical:
        with st.spinner("Chargement des indicateurs techniques des alertes…"):
            _, _, _, technical_features = load_technical_bundle()
        feature_map = technical_features.set_index("YahooTicker").to_dict(orient="index")

if st.button("▶️ Vérifier les alertes maintenant"):
    allowed, wait_seconds = consume(
        "manual_alert_evaluation",
        max_calls=6,
        window_seconds=60,
    )
    if not allowed:
        st.warning(
            f"Trop d'évaluations rapprochées. Réessaie dans {wait_seconds} secondes."
        )
        footer()
        st.stop()

    evaluation_features = feature_map
    active_alerts = alerts[alerts["active"] == 1]
    if _needs_technical_features(active_alerts):
        with st.spinner("Mise à jour des signaux d’alerte…"):
            _, _, _, technical_features = load_technical_bundle()
        evaluation_features = technical_features.set_index("YahooTicker").to_dict(orient="index")

    triggered_count = 0
    for _, alert in active_alerts.iterrows():
        feature = evaluation_features.get(alert["ticker"])
        if not feature:
            continue
        triggered, value, message = evaluate_alert(alert, feature)
        update_alert_value(int(alert["id"]), value)
        last_triggered = alert.get("last_triggered_at")
        cooldown_ok = True
        if last_triggered:
            try:
                cooldown_ok = datetime.utcnow() - datetime.fromisoformat(str(last_triggered)) >= timedelta(minutes=int(alert["cooldown_minutes"]))
            except Exception:
                cooldown_ok = True
        if triggered and cooldown_ok:
            record_alert_trigger(
                int(alert["id"]),
                profile,
                str(alert["ticker"]),
                message,
                value,
            )
            triggered_count += 1
    if triggered_count:
        st.error(f"{triggered_count} alerte(s) déclenchée(s).")
    else:
        st.success("Aucune nouvelle alerte déclenchée.")
    st.rerun()

st.subheader("Alertes actives et inactives")
for _, alert in alerts.iterrows():
    feature = feature_map.get(alert["ticker"], {})
    alert_type = str(alert.get("alert_type", ""))
    if alert_type in TECHNICAL_ALERT_TYPES and not show_live_technical:
        value_raw = safe_float(alert.get("last_value"))
        triggered, value, message = False, None if np.isnan(value_raw) else value_raw, "Valeur technique chargée seulement à l'évaluation."
    else:
        triggered, value, message = evaluate_alert(alert, feature) if feature else (False, None, "Donnée indisponible")
    with st.container(border=True):
        cols = st.columns([2.2, 1.2, 1.2, 1.2, 0.8, 0.8])
        cols[0].markdown(f"**{alert['ticker']}** · {label_by_type.get(alert['alert_type'], alert['alert_type'])}")
        condition = alert["operator"] if alert["alert_type"] == "sma_cross" else f"{alert['operator']} {safe_float(alert['threshold']):.2f}"
        cols[1].write(condition)
        cols[2].write(f"Valeur : {value:.2f}" if value is not None else "Valeur : N/D")
        cols[3].write("🚨 Déclenchée" if triggered else "En attente")
        toggle_label = "Désactiver" if int(alert["active"]) else "Activer"
        if cols[4].button(toggle_label, key=f"toggle_{alert['id']}"):
            set_alert_active(int(alert["id"]), not bool(alert["active"]))
            st.rerun()
        if cols[5].button("Suppr.", key=f"delete_{alert['id']}"):
            delete_alert(int(alert["id"]))
            st.rerun()
        st.caption(f"Canal : {alert['channel']} · cooldown : {alert['cooldown_minutes']} min · dernier déclenchement : {alert['last_triggered_at'] or 'jamais'}")
        if message and alert_type in TECHNICAL_ALERT_TYPES and not show_live_technical:
            st.caption(message)

st.subheader("Historique des déclenchements")
events = get_alert_events(profile)
if events.empty:
    st.caption("Aucun déclenchement enregistré.")
else:
    st.dataframe(events[["created_at", "ticker", "message", "observed_value"]], hide_index=True, width="stretch")

footer()