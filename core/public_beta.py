from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import os
import re
import uuid
from typing import Any

import streamlit as st
from core.database import (
    ensure_profile,
    get_preference,
    init_db,
    set_preference,
)


LEGAL_VERSION = "2026-06-13"
LEGAL_QUERY_PARAM = "anatole_accepted"
LEGAL_STORAGE_KEY = "anatole_legal_acceptance_version"
GUEST_STORAGE_KEY = "anatole_guest_profile"
GUEST_MODE_QUERY_PARAM = "anatole_guest_mode"


@dataclass(frozen=True)
class BetaContext:
    profile: str
    display_name: str
    email: str
    authenticated: bool
    is_admin: bool
    access_mode: str
    public_beta: bool


def _setting(name: str, default: str = "") -> str:
    env_value = os.getenv(name)
    if env_value not in (None, ""):
        return str(env_value)

    try:
        value = st.secrets.get(name, default)
        if value not in (None, ""):
            return str(value)
    except Exception:
        pass

    return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "oui"}


def public_beta_enabled() -> bool:
    return _as_bool(_setting("ANATOLE_PUBLIC_BETA", "false"))


def access_mode() -> str:
    mode = _setting("ANATOLE_ACCESS_MODE", "hybrid").strip().lower()
    return mode if mode in {"guest", "login", "hybrid"} else "hybrid"


def auth_configured() -> bool:
    try:
        auth = st.secrets.get("auth")
        return bool(
            auth
            and auth.get("redirect_uri")
            and auth.get("cookie_secret")
            and auth.get("client_id")
            and auth.get("client_secret")
            and auth.get("server_metadata_url")
        )
    except Exception:
        return False


def _logged_user() -> tuple[bool, str, str, str]:
    try:
        user = st.user
        logged_in = bool(user.is_logged_in)
        if not logged_in:
            return False, "", "", ""

        email = str(user.get("email", "") or "")
        name = str(user.get("name", "") or email or "Utilisateur")
        subject = str(user.get("sub", "") or email or name)
        return True, subject, name, email
    except Exception:
        return False, "", "", ""


def _profile_from_identity(subject: str) -> str:
    digest = hashlib.sha256(subject.encode("utf-8")).hexdigest()[:24]
    return f"user-{digest}"


def _guest_profile() -> str:
    """
    Garde un profil invité stable dans la session et dans l'URL.
    Cela évite de redemander les conditions lors d'un changement de page,
    d'un rechargement ou d'un redémarrage léger de session.
    """
    session_value = str(st.session_state.get("_anatole_guest_profile", ""))
    query_value = _query_value("anatole_guest")

    if _valid_guest_profile(session_value):
        profile = session_value
    elif _valid_guest_profile(query_value):
        profile = query_value
    else:
        profile = f"guest-{uuid.uuid4().hex[:24]}"

    st.session_state["_anatole_guest_profile"] = profile
    _set_query_value("anatole_guest", profile)
    return profile


def _admin_emails() -> set[str]:
    raw = _setting("ANATOLE_ADMIN_EMAILS", "")
    return {
        value.strip().lower()
        for value in raw.split(",")
        if value.strip()
    }


def _query_value(name: str, default: str = "") -> str:
    """Lit un paramètre d'URL sans casser l'app hors contexte Streamlit."""
    try:
        value = st.query_params.get(name, default)
        if isinstance(value, list):
            return str(value[0]) if value else default
        return str(value or default)
    except Exception:
        return default


def _set_query_value(name: str, value: str) -> None:
    """Écrit un paramètre d'URL seulement si nécessaire."""
    try:
        if _query_value(name) != value:
            st.query_params[name] = value
    except Exception:
        pass


def _valid_guest_profile(value: str) -> bool:
    return bool(re.fullmatch(r"guest-[0-9a-f]{20,40}", str(value or "")))


def _query_acceptance_is_valid() -> bool:
    return _query_value(LEGAL_QUERY_PARAM) == LEGAL_VERSION


def _mark_legal_accepted_in_url(profile: str) -> None:
    _set_query_value(LEGAL_QUERY_PARAM, LEGAL_VERSION)
    if _valid_guest_profile(profile):
        _set_query_value("anatole_guest", profile)


def _inject_mobile_persistence_bridge() -> None:
    """Pont navigateur désactivé pour éviter les écrans blancs sur Render.

    Les anciennes versions injectaient un composant HTML invisible pour propager
    les paramètres de session. Sur certains navigateurs/versions Streamlit, ces
    iframes pouvaient laisser une page blanche après acceptation des conditions.
    La persistance est désormais gérée côté session, préférences et paramètres
    générés par les liens Anatole.
    """
    return

def _render_login_gate(mode: str) -> None:
    st.title("Anatole — bêta publique")
    st.write(
        "Connecte-toi pour conserver ta watchlist, ton portefeuille, "
        "tes préférences et tes alertes de manière isolée."
    )

    if not auth_configured():
        st.error(
            "La connexion utilisateur est temporairement indisponible. "
            "Vous pouvez réessayer plus tard ou continuer en mode invité si cette option est proposée."
        )
        st.stop()

    st.button(
        "Se connecter",
        type="primary",
        use_container_width=True,
        on_click=st.login,
    )
    if mode == "hybrid":
        if st.button("Continuer comme invité", use_container_width=True):
            st.session_state["_anatole_guest_override"] = True
            _set_query_value(GUEST_MODE_QUERY_PARAM, "1")
            st.rerun()
    st.stop()


def _require_legal_consent(profile: str, authenticated: bool) -> None:
    """Vérifie l'acceptation légale sans écran blanc après le clic.

    V5.9.8 : lorsqu'un utilisateur accepte les conditions, on vide le panneau
    d'accueil légal et on laisse l'application continuer vers la navigation dans
    la même exécution. On évite ainsi les boucles une relance de page / redirection qui
    pouvaient laisser une page blanche sur Render ou mobile.
    """
    stored = get_preference(profile, "legal_acceptance_version", "")
    profile_key = f"_anatole_legal_accepted_{profile}"
    browser_accepted = _query_acceptance_is_valid()
    session_accepted = bool(
        st.session_state.get(profile_key)
        or st.session_state.get("_anatole_legal_accepted")
    )

    if stored == LEGAL_VERSION or browser_accepted or session_accepted:
        st.session_state[profile_key] = True
        st.session_state["_anatole_legal_accepted"] = True
        if stored != LEGAL_VERSION:
            set_preference(profile, "legal_acceptance_version", LEGAL_VERSION)
        _mark_legal_accepted_in_url(profile)
        return

    gate = st.empty()
    with gate.container():
        st.title("Bienvenue dans la bêta publique d’Anatole")
        st.warning(
            "Anatole est un outil expérimental d’information financière. "
            "Les données peuvent être différées, incomplètes ou indisponibles. "
            "Il ne fournit pas de conseil financier personnalisé."
        )

        with st.expander("Résumé des conditions", expanded=True):
            st.markdown(
                """
                - Utilisation à des fins d’information et d’évaluation.
                - Aucune garantie sur les prix, nouvelles, signaux ou calculs.
                - Ne saisis pas de renseignements bancaires, numéros de compte ou secrets.
                - Les données de portefeuille saisies sont des données de test.
                - Les fonctionnalités et données peuvent changer pendant la bêta.
                """
            )

        terms = st.checkbox(
            "J’accepte les conditions d’utilisation de la bêta.",
            key="_anatole_terms_checkbox",
        )
        privacy = st.checkbox(
            "J’ai lu l’avis de confidentialité et j’accepte le traitement décrit.",
            key="_anatole_privacy_checkbox",
        )

        accepted_now = st.button(
            "Accéder à Anatole",
            type="primary",
            disabled=not (terms and privacy),
            use_container_width=True,
        )

    if accepted_now:
        st.session_state[profile_key] = True
        st.session_state["_anatole_legal_accepted"] = True
        set_preference(profile, "legal_acceptance_version", LEGAL_VERSION)
        _mark_legal_accepted_in_url(profile)
        st.rerun()

    st.stop()

def bootstrap_public_beta() -> BetaContext:
    init_db()
    _inject_mobile_persistence_bridge()

    beta = public_beta_enabled()
    mode = access_mode() if beta else "guest"
    logged_in, subject, name, email = _logged_user()
    guest_override = bool(
        st.session_state.get("_anatole_guest_override")
        or _query_value(GUEST_MODE_QUERY_PARAM) == "1"
    )

    if beta and mode == "login" and not logged_in:
        _render_login_gate(mode)

    if beta and mode == "hybrid" and not logged_in and not guest_override:
        if auth_configured():
            _render_login_gate(mode)
        else:
            # En l'absence de fournisseur OIDC, le mode hybride continue
            # automatiquement avec une session invitée temporaire.
            st.session_state["_anatole_guest_override"] = True
            _set_query_value(GUEST_MODE_QUERY_PARAM, "1")
            guest_override = True

    if logged_in:
        profile = ensure_profile(_profile_from_identity(subject))
        display_name = name
    else:
        profile = ensure_profile(_guest_profile() if beta else "principal")
        display_name = "Invité" if beta else "Profil local"

    is_admin = bool(email and email.lower() in _admin_emails())

    context = BetaContext(
        profile=profile,
        display_name=display_name,
        email=email,
        authenticated=logged_in,
        is_admin=is_admin,
        access_mode=mode,
        public_beta=beta,
    )

    st.session_state["profile"] = profile
    st.session_state["beta_context"] = asdict(context)

    if beta:
        _require_legal_consent(profile, logged_in)

    return context


def current_context() -> BetaContext:
    raw = st.session_state.get("beta_context")
    if isinstance(raw, dict):
        return BetaContext(**raw)

    return BetaContext(
        profile=str(st.session_state.get("profile", "principal")),
        display_name="Profil local",
        email="",
        authenticated=False,
        is_admin=False,
        access_mode="guest",
        public_beta=False,
    )
