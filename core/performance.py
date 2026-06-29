from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter
from typing import Iterator

import streamlit as st


@contextmanager
def load_timer(label: str) -> Iterator[dict[str, float]]:
    """Mesure discrètement une opération pour les diagnostics UI."""
    start = perf_counter()
    record = {"seconds": 0.0}
    try:
        yield record
    finally:
        record["seconds"] = perf_counter() - start
        st.session_state[f"_perf_{label}"] = record["seconds"]


def perf_caption(label: str, threshold: float = 2.5) -> None:
    """Compatibility hook. Do not display performance messages to public users."""
    return None


def render_load_more_button(key: str, label: str = "Charger plus") -> bool:
    """Bouton standard pour éviter de charger les détails lourds automatiquement."""
    return st.button(label, key=key, width="stretch")


def safe_display_count(total: int, displayed: int) -> str:
    if total <= displayed:
        return f"{displayed} éléments affichés"
    return f"{displayed} éléments affichés sur {total}"
