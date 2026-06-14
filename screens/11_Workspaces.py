from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from core.database import delete_workspace, get_workspaces, save_workspace
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context
from core.workspaces import DEFAULT_LAYOUTS, dataframe_to_layout, ensure_default_workspaces, layout_to_dataframe

configure_page("Espaces de travail", "🧱")
apply_style()
profile = sidebar_context()
page_header(
    "Espaces de travail personnalisables",
    "Choisis les modules, leur ordre et leur taille afin de créer plusieurs cockpits adaptés à tes usages.",
    "🧱",
)

ensure_default_workspaces(profile)
workspaces = get_workspaces(profile)
names = workspaces["name"].tolist() if not workspaces.empty else list(DEFAULT_LAYOUTS)
selected = st.selectbox("Espace à modifier", names)
row = workspaces[workspaces["name"] == selected]
if row.empty:
    layout = DEFAULT_LAYOUTS.get(selected, DEFAULT_LAYOUTS["Marché canadien"])
else:
    try:
        layout = json.loads(row.iloc[0]["layout_json"])
    except Exception:
        layout = DEFAULT_LAYOUTS["Marché canadien"]

st.caption("Modifie l'ordre numérique, la visibilité et la taille. Le cockpit utilisera ensuite cette configuration.")
editor = st.data_editor(
    layout_to_dataframe(layout),
    hide_index=True,
    width="stretch",
    num_rows="dynamic",
    column_config={
        "module": st.column_config.TextColumn("Module", required=True),
        "visible": st.column_config.CheckboxColumn("Visible"),
        "size": st.column_config.SelectboxColumn("Taille", options=["small", "medium", "large"]),
        "order": st.column_config.NumberColumn("Ordre", min_value=1, step=1),
    },
)

c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    if st.button("Enregistrer et activer", type="primary", width="stretch"):
        save_workspace(profile, selected, json.dumps(dataframe_to_layout(editor), ensure_ascii=False), active=True)
        st.success("Espace enregistré et activé.")
        st.rerun()
with c2:
    if st.button("Dupliquer", width="stretch"):
        copy_name = f"{selected} - copie"
        save_workspace(profile, copy_name, json.dumps(dataframe_to_layout(editor), ensure_ascii=False), active=False)
        st.success(f"Espace créé : {copy_name}")
        st.rerun()
with c3:
    new_name = st.text_input("Nom d'un nouvel espace", placeholder="Ex. Dividendes et banques")
    if st.button("Créer le nouvel espace") and new_name.strip():
        save_workspace(profile, new_name.strip(), json.dumps(dataframe_to_layout(editor), ensure_ascii=False), active=True)
        st.success("Nouvel espace créé.")
        st.rerun()

st.divider()
st.subheader("Aperçu de la disposition")
visible = [item for item in dataframe_to_layout(editor) if item.get("visible")]
for item in visible:
    width = {"small": 30, "medium": 60, "large": 100}.get(item.get("size"), 60)
    st.markdown(
        f"<div style='width:{width}%;min-width:260px;padding:16px 18px;margin:8px 0;border-radius:16px;"
        "background:var(--sky-surface);border:1px solid var(--sky-border);box-shadow:var(--sky-shadow-soft);'>"
        f"<strong>{item['order']}. {item['module']}</strong><br><span style='color:var(--sky-muted)'>Taille : {item['size']}</span></div>",
        unsafe_allow_html=True,
    )

if len(names) > 1:
    st.divider()
    remove = st.selectbox("Supprimer un espace", [name for name in names if name != selected])
    if st.button("Supprimer définitivement", type="secondary"):
        delete_workspace(profile, remove)
        st.success("Espace supprimé.")
        st.rerun()

st.info("Le déplacement est géré par l'ordre et les tailles sauvegardées. Cette approche reste stable sur ordinateur et mobile, sans dépendance de glisser-déposer fragile.")
footer()
