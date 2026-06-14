from __future__ import annotations

import streamlit as st

from core.database import get_alert_events, get_notifications, mark_all_notifications_read, mark_notification_read
from core.notifications import seed_market_notifications
from core.runtime import load_market_bundle
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context

configure_page("Notifications", "🔔")
apply_style()
profile = sidebar_context()
page_header(
    "Centre de notifications",
    "Regroupe les mouvements inhabituels, alertes de prix, événements techniques et informations importantes.",
    "🔔",
)

_, _, market, _ = load_market_bundle()
seed_market_notifications(profile, market)
notifications = get_notifications(profile, limit=200)
alert_events = get_alert_events(profile, limit=100)

unread = int((notifications.get("is_read", 1) == 0).sum()) if not notifications.empty else 0
c1, c2, c3 = st.columns(3)
c1.metric("Non lues", unread)
c2.metric("Notifications", len(notifications))
c3.metric("Alertes déclenchées", len(alert_events))

if st.button("Tout marquer comme lu", width="content"):
    mark_all_notifications_read(profile)
    st.rerun()

category = st.multiselect(
    "Catégories",
    sorted(notifications["category"].dropna().unique().tolist()) if not notifications.empty else [],
    default=sorted(notifications["category"].dropna().unique().tolist()) if not notifications.empty else [],
)
show_unread = st.toggle("Afficher uniquement les non lues", value=False)

view = notifications.copy()
if not view.empty:
    if category:
        view = view[view["category"].isin(category)]
    if show_unread:
        view = view[view["is_read"] == 0]

if view.empty:
    st.info("Aucune notification correspondant aux filtres.")
else:
    for _, item in view.iterrows():
        icon = {"success": "🟢", "warning": "🟠", "error": "🔴"}.get(str(item.get("severity")), "🔵")
        unread_mark = " · **Nouveau**" if int(item.get("is_read", 0)) == 0 else ""
        with st.container(border=True):
            st.markdown(f"### {icon} {item['title']}{unread_mark}")
            st.caption(f"{item['category']} · {item.get('ticker', '')} · {item['created_at']}")
            if item.get("message"):
                st.write(item["message"])
            if int(item.get("is_read", 0)) == 0 and st.button("Marquer comme lu", key=f"read_{item['id']}"):
                mark_notification_read(int(item["id"]), True)
                st.rerun()

with st.expander("Historique des alertes déclenchées"):
    if alert_events.empty:
        st.caption("Aucune alerte déclenchée.")
    else:
        st.dataframe(alert_events, hide_index=True, width="stretch")

footer()
