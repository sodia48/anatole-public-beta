from __future__ import annotations

import html
import importlib.metadata
from datetime import datetime
from typing import Iterable

import streamlit as st
import streamlit.components.v1 as components

from core.config import DEFAULT_PROFILE, TORONTO_TZ
from core.database import ensure_profile, init_db
from core.preferences import hydrate_preferences, save_preferences
from core.utils import market_status
from core.universe import current_universe


THEME_QUERY_PARAM = "anatole_theme"
THEME_STORAGE_KEY = "anatole_theme"
VALID_THEME_VALUES = {"light", "dark"}


def _query_param_value(name: str, default: str = "") -> str:
    try:
        value = st.query_params.get(name, default)
        if isinstance(value, list):
            return str(value[0]) if value else default
        return str(value or default)
    except Exception:
        return default


def _set_query_param_value(name: str, value: str) -> None:
    try:
        if _query_param_value(name) != value:
            st.query_params[name] = value
    except Exception:
        pass


def _safe_urlencode(pairs: dict[str, str]) -> str:
    """Encode une petite série de query params sans dépendance externe."""
    try:
        from urllib.parse import urlencode

        return urlencode({k: v for k, v in pairs.items() if str(v or "").strip()})
    except Exception:
        # Fallback minimal : les valeurs générées par Anatole sont déjà sûres
        # ou très contrôlées. On échappe quand même les caractères HTML au rendu.
        return "&".join(
            f"{str(k).strip()}={html.escape(str(v).strip(), quote=True)}"
            for k, v in pairs.items()
            if str(v or "").strip()
        )


def _navigation_query_suffix(*, nav: str | None = None) -> str:
    """Préserve les paramètres essentiels lors de la navigation interne.

    Sans cette couche, un clic sur une section Streamlit peut perdre
    l'acceptation de la bêta, le profil invité ou le thème. C'est ce qui
    donnait l'impression de recommencer à zéro à chaque changement de page.
    """
    params: dict[str, str] = {}
    if nav:
        params["nav"] = str(nav)

    keys = [
        "anatole_guest",
        "anatole_guest_mode",
        "anatole_accepted",
        "anatole_theme",
        "universe",
        "ticker",
        "symbol",
    ]
    for key in keys:
        value = _query_param_value(key)
        if value:
            params[key] = value

    # Sombre par défaut : même sans query param, on transporte l'état actif.
    if "anatole_theme" not in params:
        params["anatole_theme"] = _normalized_theme(st.session_state.get("_anatole_theme")) or _theme_from_session()

    encoded = _safe_urlencode(params)
    return f"?{encoded}" if encoded else ""


def _normalized_theme(value: object) -> str:
    raw = str(value or "").strip().lower()
    if raw in VALID_THEME_VALUES:
        return raw
    return ""


def _theme_from_session(default: str = "dark") -> str:
    """Retourne le thème courant avec le sombre comme valeur sûre par défaut."""
    if "theme_toggle" not in st.session_state:
        return default
    return "dark" if bool(st.session_state.get("theme_toggle", True)) else "light"


def _apply_theme_choice(profile: str, theme: str, *, save: bool = True) -> None:
    theme = _normalized_theme(theme) or "dark"
    st.session_state["theme_toggle"] = theme == "dark"
    st.session_state["_anatole_theme"] = theme
    if save:
        try:
            save_preferences(profile, {"theme": theme})
            st.session_state.pop("_preferences_profile", None)
        except Exception:
            pass
    _set_query_param_value(THEME_QUERY_PARAM, theme)


def _install_theme_persistence_bridge(current_theme: str) -> None:
    """Persiste le thème et les paramètres bêta dans tous les liens internes."""
    theme = _normalized_theme(current_theme) or "dark"
    try:
        components.html(
            f"""
            <script>
            (function() {{
                try {{
                    const THEME_KEY = {THEME_STORAGE_KEY!r};
                    const THEME_PARAM = {THEME_QUERY_PARAM!r};
                    const CURRENT_THEME = {theme!r};
                    const win = window.parent || window;
                    const doc = win.document;
                    if (!doc) return;
                    const url = new URL(win.location.href);
                    const validThemes = new Set(["light", "dark"]);
                    const PARAMS_TO_KEEP = [
                        "anatole_guest",
                        "anatole_guest_mode",
                        "anatole_accepted",
                        "anatole_theme",
                        "universe",
                        "ticker",
                        "symbol"
                    ];
                    const STORAGE_MAP = {{
                        "anatole_guest": "anatole_guest_profile",
                        "anatole_guest_mode": "anatole_guest_mode",
                        "anatole_accepted": "anatole_legal_acceptance_version",
                        "anatole_theme": THEME_KEY
                    }};

                    function getStorage() {{
                        try {{ return win.localStorage; }} catch (e) {{ return null; }}
                    }}

                    const store = getStorage();
                    let changed = false;

                    // Le terminal sombre est la base. Le bleu ciel n'est conservé que s'il est explicitement demandé.
                    if (!validThemes.has(url.searchParams.get(THEME_PARAM))) {{
                        url.searchParams.set(THEME_PARAM, CURRENT_THEME);
                        changed = true;
                    }}
                    if (store) {{
                        try {{ store.setItem(THEME_KEY, url.searchParams.get(THEME_PARAM) || CURRENT_THEME); }} catch (e) {{}}
                        PARAMS_TO_KEEP.forEach((param) => {{
                            const value = url.searchParams.get(param);
                            const key = STORAGE_MAP[param];
                            if (key && value) {{ try {{ store.setItem(key, value); }} catch (e) {{}} }}
                        }});
                        // Si un lien interne a perdu les paramètres de bêta, on les restaure depuis le navigateur.
                        PARAMS_TO_KEEP.forEach((param) => {{
                            if (url.searchParams.get(param)) return;
                            const key = STORAGE_MAP[param];
                            if (!key) return;
                            let stored = null;
                            try {{ stored = store.getItem(key); }} catch (e) {{ stored = null; }}
                            if (stored) {{
                                url.searchParams.set(param, stored);
                                changed = true;
                            }}
                        }});
                    }}
                    if (changed) {{
                        try {{ win.history.replaceState({{}}, "", url.toString()); }} catch (e) {{}}
                    }}

                    function patchLinks() {{
                        try {{
                            const current = new URL(win.location.href);
                            doc.querySelectorAll('a[href]').forEach((anchor) => {{
                                const href = anchor.getAttribute('href') || '';
                                if (href.startsWith('#') || href.startsWith('mailto:') || href.startsWith('tel:')) return;
                                const target = new URL(anchor.href, win.location.origin);
                                if (target.origin !== win.location.origin) return;
                                PARAMS_TO_KEEP.forEach((param) => {{
                                    const value = current.searchParams.get(param);
                                    if (value && !target.searchParams.get(param)) {{
                                        target.searchParams.set(param, value);
                                    }}
                                }});
                                if (!target.searchParams.get(THEME_PARAM)) {{
                                    target.searchParams.set(THEME_PARAM, CURRENT_THEME);
                                }}
                                anchor.href = target.toString();
                                anchor.setAttribute('target', '_self');
                                anchor.removeAttribute('rel');
                            }});
                        }} catch (e) {{}}
                    }}

                    patchLinks();
                    setTimeout(patchLinks, 120);
                    setTimeout(patchLinks, 450);
                    setTimeout(patchLinks, 1200);
                    if (!win.__anatolePersistentLinkBridge) {{
                        win.__anatolePersistentLinkBridge = win.setInterval(patchLinks, 700);
                    }}
                }} catch (e) {{}}
            }})();
            </script>
            """,
            height=0,
            width=0,
        )
    except Exception:
        pass


def force_anatole_browser_brand(page_title: str = "Anatole") -> None:
    """Applique un titre navigateur Anatole et neutralise le branding Streamlit visible.

    La fonction doit rester non bloquante : si le navigateur ou Streamlit bloque
    l'injection, l'application continue sans erreur.
    """
    safe_title = html.escape(str(page_title or "Anatole"), quote=True)
    try:
        components.html(
            f"""
            <script>
            (function() {{
              try {{
                const win = window.parent || window;
                const doc = win.document;
                if (!doc) return;
                doc.title = "{safe_title}";
                const hide = () => {{
                  try {{
                    doc.title = "{safe_title}";
                    const selectors = [
                      '#MainMenu',
                      'footer',
                      'header [data-testid="stToolbar"]',
                      '[data-testid="stToolbar"]',
                      '[data-testid="stDecoration"]',
                      '[data-testid="stStatusWidget"]',
                      '[aria-label="Main menu"]',
                      '[title="Main menu"]'
                    ];
                    selectors.forEach((sel) => {{
                      doc.querySelectorAll(sel).forEach((el) => {{
                        el.style.visibility = 'hidden';
                        el.style.display = 'none';
                        el.style.pointerEvents = 'none';
                      }});
                    }});
                    doc.querySelectorAll('*').forEach((el) => {{
                      const txt = (el.innerText || '').trim();
                      if (txt === 'Made with Streamlit' || txt.includes('Made with Streamlit')) {{
                        el.style.display = 'none';
                        el.style.visibility = 'hidden';
                      }}
                    }});
                  }} catch (e) {{}}
                }};
                hide();
                setTimeout(hide, 80);
                setTimeout(hide, 400);
                setTimeout(hide, 1200);
                if (!win.__anatoleBrandInterval) {{
                  win.__anatoleBrandInterval = win.setInterval(hide, 1500);
                }}
              }} catch (e) {{}}
            }})();
            </script>
            """,
            height=0,
            width=0,
        )
    except Exception:
        pass


def configure_page(title: str, icon: str = "📈") -> None:
    page_title = "Anatole" if str(title).strip().lower() == "anatole" else f"{title} · Anatole"
    if not st.session_state.get("_page_configured"):
        st.set_page_config(
            page_title=page_title,
            page_icon=icon,
            layout="wide",
            initial_sidebar_state="expanded",
            menu_items={
                "Get help": None,
                "Report a bug": None,
                "About": None,
            },
        )
        st.session_state["_page_configured"] = True

    st.session_state["_anatole_page_title"] = page_title
    force_anatole_browser_brand(page_title)



def enforce_same_tab_navigation() -> None:
    """Force les liens internes à rester dans le même onglet et à garder l'état bêta."""
    components.html(
        """
        <script>
        (function() {
          try {
            const win = window.parent || window;
            const doc = win.document;
            if (!doc || doc.__anatoleSameTabInstalledV2) return;
            doc.__anatoleSameTabInstalledV2 = true;
            const KEEP = [
              "anatole_guest",
              "anatole_guest_mode",
              "anatole_accepted",
              "anatole_theme",
              "universe",
              "ticker",
              "symbol"
            ];

            function isInternalLink(anchor) {
              if (!anchor || !anchor.href) return false;
              try {
                const url = new URL(anchor.href, win.location.href);
                return url.origin === win.location.origin;
              } catch (error) {
                return false;
              }
            }

            function patchedHref(anchor) {
              const current = new URL(win.location.href);
              const target = new URL(anchor.href, win.location.href);
              KEEP.forEach((param) => {
                const value = current.searchParams.get(param);
                if (value && !target.searchParams.get(param)) {
                  target.searchParams.set(param, value);
                }
              });
              return target.toString();
            }

            function patchLinks() {
              doc.querySelectorAll('a[href]').forEach((anchor) => {
                if (isInternalLink(anchor)) {
                  anchor.href = patchedHref(anchor);
                  anchor.setAttribute('target', '_self');
                  anchor.removeAttribute('rel');
                }
              });
            }

            doc.addEventListener('click', function(event) {
              const anchor = event.target && event.target.closest ? event.target.closest('a') : null;
              if (!isInternalLink(anchor)) return;
              const destination = patchedHref(anchor);
              if (anchor.href !== destination || (anchor.target && anchor.target !== '_self')) {
                event.preventDefault();
                win.location.href = destination;
              }
            }, true);

            patchLinks();
            setTimeout(patchLinks, 100);
            setTimeout(patchLinks, 450);
            setTimeout(patchLinks, 1000);
            win.setInterval(patchLinks, 900);
          } catch (error) {}
        })();
        </script>
        """,
        height=0,
        width=0,
    )


def install_sidebar_rescue_navigation() -> None:
    """Garde une navigation utilisable quand Streamlit replie ou masque la sidebar.

    Streamlit peut conserver l'état "sidebar collapsed" dans le navigateur. Sur
    Render, après redimensionnement ou changement de session, cela donne une app
    fonctionnelle mais sans sections à gauche. Ce garde fait deux choses :
    1) il tente de rouvrir la sidebar officielle sur desktop;
    2) s'il ne la voit toujours pas, il affiche un rail Anatole de secours.
    """
    theme = _normalized_theme(str(st.session_state.get("_anatole_theme", "dark"))) or "dark"
    nav_items = [
        ("🏠", "Cockpit", "accueil"),
        ("⚡", "Aujourd’hui", "aujourdhui"),
        ("🔎", "Screener", "screener"),
        ("🎯", "Focus", "focus"),
        ("⭐", "Liste", "watchlist"),
        ("🧠", "Psychologie", "psychologie"),
        ("🧺", "ETF", "etf"),
        ("🚀", "IPO", "ipo"),
        ("🕵️", "Insiders", "insiders"),
        ("💎", "Terminal", "terminal"),
        ("⚙️", "Préférences", "preferences"),
    ]
    links = "".join(
        f'<a href="/{html.escape(_navigation_query_suffix(nav=nav), quote=True)}" target="_self" title="{html.escape(label)}">'
        f'<span class="sky-rescue-icon">{html.escape(icon)}</span><span>{html.escape(label)}</span></a>'
        for icon, label, nav in nav_items
    )
    components.html(
        f"""
        <script>
        (function() {{
            try {{
                const win = window.parent || window;
                const doc = win.document;
                if (!doc) return;

                const NAV_ID = "anatole-sidebar-rescue-nav";
                const STYLE_ID = "anatole-sidebar-rescue-style";

                function isTouchMobile() {{
                    try {{
                        return win.matchMedia("(max-width: 760px) and (hover: none) and (pointer: coarse)").matches;
                    }} catch (e) {{ return false; }}
                }}

                function sidebarVisible() {{
                    const sidebar = doc.querySelector('[data-testid="stSidebar"]');
                    if (!sidebar) return false;
                    const rect = sidebar.getBoundingClientRect();
                    const style = win.getComputedStyle(sidebar);
                    return (
                        style.display !== "none" &&
                        style.visibility !== "hidden" &&
                        rect.width >= 165 &&
                        rect.right > 120 &&
                        rect.left > -80
                    );
                }}

                function clickFirst(selectors) {{
                    for (const selector of selectors) {{
                        const node = doc.querySelector(selector);
                        if (node && typeof node.click === "function") {{
                            node.click();
                            return true;
                        }}
                    }}
                    return false;
                }}

                function tryOpenOfficialSidebar() {{
                    if (isTouchMobile() || sidebarVisible()) return;
                    clickFirst([
                        '[data-testid="collapsedControl"] button',
                        '[data-testid="collapsedControl"]',
                        '[data-testid="stSidebarCollapsedControl"] button',
                        '[data-testid="stSidebarCollapsedControl"]',
                        'button[aria-label*="sidebar" i]',
                        'button[title*="sidebar" i]',
                        'button[aria-label*="menu" i]',
                        'button[title*="menu" i]'
                    ]);
                }}

                function ensureStyle() {{
                    if (doc.getElementById(STYLE_ID)) return;
                    const style = doc.createElement("style");
                    style.id = STYLE_ID;
                    style.textContent = `
                        @media (min-width: 761px) {{
                            html.anatole-sidebar-missing [data-testid="stSidebarCollapsedControl"],
                            html.anatole-sidebar-missing [data-testid="collapsedControl"] {{
                                display: block !important;
                                visibility: visible !important;
                                opacity: 1 !important;
                            }}
                            .sky-desktop-rescue-nav {{
                                position: fixed;
                                z-index: 999999;
                                left: 14px;
                                top: 96px;
                                width: 206px;
                                max-height: calc(100vh - 122px);
                                overflow-y: auto;
                                display: none;
                                flex-direction: column;
                                gap: 6px;
                                padding: 12px;
                                border-radius: 22px;
                                background: rgba(7, 23, 39, .92);
                                border: 1px solid rgba(96, 165, 250, .26);
                                box-shadow: 0 22px 70px rgba(0,0,0,.36);
                                backdrop-filter: blur(24px) saturate(1.1);
                            }}
                            html.anatole-sidebar-missing .sky-desktop-rescue-nav {{
                                display: flex !important;
                            }}
                            .sky-desktop-rescue-nav .sky-rescue-title {{
                                color: #EAF6FF;
                                font: 900 13px/1.1 system-ui, -apple-system, Segoe UI, sans-serif;
                                letter-spacing: .08em;
                                text-transform: uppercase;
                                padding: 5px 8px 9px;
                                opacity: .92;
                            }}
                            .sky-desktop-rescue-nav a {{
                                display: flex;
                                align-items: center;
                                gap: 9px;
                                text-decoration: none;
                                color: #BFD3E6;
                                font: 800 13px/1.2 system-ui, -apple-system, Segoe UI, sans-serif;
                                padding: 10px 10px;
                                border-radius: 15px;
                                border: 1px solid transparent;
                                transition: all .16s ease;
                            }}
                            .sky-desktop-rescue-nav a:hover {{
                                color: #FFFFFF;
                                background: rgba(37,99,235,.18);
                                border-color: rgba(96,165,250,.28);
                                transform: translateX(2px);
                            }}
                            .sky-desktop-rescue-nav .sky-rescue-icon {{
                                width: 26px;
                                height: 26px;
                                display: inline-flex;
                                align-items: center;
                                justify-content: center;
                                border-radius: 10px;
                                background: rgba(255,255,255,.08);
                            }}
                            html.anatole-sidebar-missing .block-container {{
                                padding-left: min(240px, 18vw) !important;
                            }}
                        }}
                        @media (max-width: 760px) {{
                            .sky-desktop-rescue-nav {{ display: none !important; }}
                        }}
                    `;
                    doc.head.appendChild(style);
                }}

                function ensureNav() {{
                    if (doc.getElementById(NAV_ID)) return;
                    const nav = doc.createElement("nav");
                    nav.id = NAV_ID;
                    nav.className = "sky-desktop-rescue-nav";
                    nav.setAttribute("aria-label", "Navigation Anatole de secours");
                    nav.innerHTML = `<div class="sky-rescue-title">Anatole</div>{links}`;
                    doc.body.appendChild(nav);
                }}

                function refresh() {{
                    ensureStyle();
                    ensureNav();
                    tryOpenOfficialSidebar();
                    const missing = !isTouchMobile() && !sidebarVisible();
                    doc.documentElement.classList.toggle("anatole-sidebar-missing", missing);
                }}

                refresh();
                setTimeout(refresh, 250);
                setTimeout(refresh, 900);
                setTimeout(refresh, 1800);
                if (!win.__anatoleSidebarRescueInterval) {{
                    win.__anatoleSidebarRescueInterval = win.setInterval(refresh, 2200);
                }}
                win.addEventListener("resize", function() {{ setTimeout(refresh, 80); }});
            }} catch (error) {{}}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def hide_streamlit_chrome() -> None:
    """Masque le menu natif Streamlit et son popover publicitaire."""
    st.markdown(
        """
        <style>
            #MainMenu,
            #MainMenu *,
            header[data-testid="stHeader"],
            div[data-testid="stToolbar"],
            div[data-testid="stToolbar"] *,
            div[data-testid="stStatusWidget"],
            div[data-testid="stStatusWidget"] *,
            div[data-testid="stDecoration"],
            div[data-testid="stDeployButton"],
            div[data-testid="stMainMenu"],
            div[data-testid="stMainMenu"] *,
            div[data-testid="stActionButton"],
            div[data-testid="stActionButton"] *,
            button[title="View fullscreen"],
            button[title="Exit fullscreen"],
            button[aria-label="Main menu"],
            button[aria-label="Open menu"],
            button[aria-label="More"],
            button[kind="header"],
            a[title="Streamlit"],
            div[title="Streamlit"],
            img[alt="Streamlit"],
            footer,
            footer * {
                display: none !important;
                visibility: hidden !important;
                opacity: 0 !important;
                pointer-events: none !important;
                width: 0 !important;
                height: 0 !important;
                max-width: 0 !important;
                max-height: 0 !important;
                overflow: hidden !important;
            }
            .stApp > header {
                display: none !important;
                height: 0 !important;
            }
            .stApp {
                margin-top: 0 !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
    try:
        components.html(
            """
            <script>
            (function() {
                try {
                    const win = window.parent || window;
                    const doc = win.document;
                    if (!doc) return;
                    const selectors = [
                        '#MainMenu',
                        '[data-testid="stToolbar"]',
                        '[data-testid="stStatusWidget"]',
                        '[data-testid="stDecoration"]',
                        '[data-testid="stDeployButton"]',
                        '[data-testid="stMainMenu"]',
                        '[aria-label="Main menu"]',
                        '[aria-label="Open menu"]',
                        'button[title="View fullscreen"]',
                        'button[title="Exit fullscreen"]',
                        'footer'
                    ];
                    function hideNode(node) {
                        if (!node) return;
                        node.style.setProperty('display', 'none', 'important');
                        node.style.setProperty('visibility', 'hidden', 'important');
                        node.style.setProperty('opacity', '0', 'important');
                        node.style.setProperty('pointer-events', 'none', 'important');
                        node.style.setProperty('width', '0px', 'important');
                        node.style.setProperty('height', '0px', 'important');
                        node.setAttribute('aria-hidden', 'true');
                    }
                    function hideByText() {
                        doc.querySelectorAll('div, section, aside, ul').forEach((node) => {
                            const text = (node.innerText || '').trim();
                            if (text.includes('Made with Streamlit') || (text.includes('Record screen') && text.includes('About'))) {
                                hideNode(node);
                            }
                        });
                    }
                    function apply() {
                        selectors.forEach((selector) => doc.querySelectorAll(selector).forEach(hideNode));
                        hideByText();
                    }
                    apply();
                    setTimeout(apply, 100);
                    setTimeout(apply, 500);
                    setTimeout(apply, 1200);
                    if (!win.__anatoleHideStreamlitChrome) {
                        win.__anatoleHideStreamlitChrome = win.setInterval(apply, 600);
                    }
                } catch (e) {}
            })();
            </script>
            """,
            height=0,
            width=0,
        )
    except Exception:
        pass


def _hydrate_preferences_for_current_page() -> None:
    """Charge les préférences avant le rendu visuel de chaque page.

    Streamlit exécute `apply_style()` au début de chaque section, souvent
    avant que la barre latérale ait eu le temps de réhydrater le profil.
    Sans cette étape, le thème sombre peut sembler fonctionner sur une page
    puis revenir au thème clair lors du changement de section.
    """
    try:
        init_db()
        from core.public_beta import current_context

        context = current_context()
        profile = str(getattr(context, "profile", "") or st.session_state.get("profile") or DEFAULT_PROFILE)
        profile = ensure_profile(profile)
        st.session_state["profile"] = profile

        requested_theme = _normalized_theme(_query_param_value(THEME_QUERY_PARAM))
        if requested_theme:
            _apply_theme_choice(profile, requested_theme, save=True)

        hydrate_preferences(profile)

        if requested_theme:
            # Le query param a priorité. Bleu ciel reste possible seulement lorsqu'il est demandé explicitement.
            st.session_state["theme_toggle"] = requested_theme == "dark"
            st.session_state["_anatole_theme"] = requested_theme
        else:
            # V5.8.4 : le sombre devient la base unique par défaut.
            # Cela neutralise les anciennes préférences "light" enregistrées avant la migration.
            st.session_state["theme_toggle"] = True
            st.session_state["_anatole_theme"] = "dark"
            try:
                save_preferences(profile, {"theme": "dark"})
                st.session_state.pop("_preferences_profile", None)
            except Exception:
                pass
    except Exception:
        # Le style ne doit jamais empêcher l'application de charger.
        pass


def is_dark_mode() -> bool:
    _hydrate_preferences_for_current_page()
    return bool(st.session_state.get("theme_toggle", False))


def apply_style() -> None:
    _hydrate_preferences_for_current_page()
    try:
        from core.device import bootstrap_mobile_mode
        bootstrap_mobile_mode()
    except Exception:
        pass
    dark = bool(st.session_state.get("theme_toggle", False))
    compact = bool(st.session_state.get("compact_toggle", False))
    current_theme = "dark" if dark else "light"
    st.session_state["_anatole_theme"] = current_theme

    if dark:
        background = """
            radial-gradient(circle at 8% 8%, rgba(37,99,235,.18) 0, rgba(37,99,235,0) 30%),
            radial-gradient(circle at 92% 12%, rgba(14,165,233,.14) 0, rgba(14,165,233,0) 28%),
            linear-gradient(135deg, #071522 0%, #0B1E2E 46%, #0E263B 100%)
        """
        sidebar_background = """
            linear-gradient(180deg, rgba(7,21,34,.98) 0%, rgba(10,31,48,.98) 100%)
        """
        surface = "rgba(15, 39, 59, .82)"
        surface_strong = "rgba(18, 48, 72, .96)"
        surface_soft = "rgba(20, 53, 78, .62)"
        text = "#EAF6FF"
        muted = "#9AB6CC"
        border = "rgba(125, 211, 252, .17)"
        header_bg = "rgba(7, 21, 34, .78)"
        shadow = "0 20px 55px rgba(0, 0, 0, .28)"
        shadow_soft = "0 10px 30px rgba(0, 0, 0, .22)"
        input_bg = "rgba(12, 35, 53, .92)"
        hero_bg = """
            radial-gradient(circle at 88% 18%, rgba(56,189,248,.19), rgba(56,189,248,0) 30%),
            linear-gradient(135deg, rgba(17,44,67,.98), rgba(12,34,52,.88))
        """
        metric_bg = "linear-gradient(145deg, rgba(18,48,72,.94), rgba(10,31,48,.86))"
        plot_bg = "rgba(11,31,48,.76)"
    else:
        background = """
            radial-gradient(circle at 8% 8%, rgba(255,255,255,.96) 0, rgba(255,255,255,0) 30%),
            radial-gradient(circle at 92% 16%, rgba(125,211,252,.34) 0, rgba(125,211,252,0) 30%),
            linear-gradient(135deg, #DDF3FF 0%, #F3FBFF 42%, #DCEEFF 100%)
        """
        sidebar_background = """
            linear-gradient(180deg, rgba(255,255,255,.95) 0%, rgba(225,244,255,.94) 100%)
        """
        surface = "rgba(255,255,255,.80)"
        surface_strong = "rgba(255,255,255,.96)"
        surface_soft = "rgba(255,255,255,.62)"
        text = "#0F2742"
        muted = "#5B7088"
        border = "rgba(76,145,201,.22)"
        header_bg = "rgba(226,244,255,.72)"
        shadow = "0 20px 55px rgba(24, 83, 132, .11)"
        shadow_soft = "0 10px 30px rgba(35, 92, 138, .09)"
        input_bg = "rgba(255,255,255,.90)"
        hero_bg = """
            radial-gradient(circle at 88% 18%, rgba(125,211,252,.36), rgba(125,211,252,0) 30%),
            linear-gradient(135deg, rgba(255,255,255,.97), rgba(239,249,255,.82))
        """
        metric_bg = "linear-gradient(145deg, rgba(255,255,255,.96), rgba(237,248,255,.82))"
        plot_bg = "rgba(255,255,255,.76)"

    block_padding = ".65rem" if compact else "1.05rem"
    metric_padding = "12px 14px" if compact else "16px 17px"
    metric_height = "88px" if compact else "108px"

    css = f"""
    <style>
        :root {{
            --sky-primary: #2563EB;
            --sky-primary-2: #0EA5E9;
            --sky-accent: #38BDF8;
            --sky-text: {text};
            --sky-muted: {muted};
            --sky-surface: {surface};
            --sky-surface-strong: {surface_strong};
            --sky-surface-soft: {surface_soft};
            --sky-border: {border};
            --sky-shadow: {shadow};
            --sky-shadow-soft: {shadow_soft};
            --sky-input: {input_bg};
            --sky-plot: {plot_bg};
        }}

        html {{
            scroll-behavior: smooth;
        }}

        html, body, [data-testid="stAppViewContainer"] {{
            background: {background} !important;
            color: var(--sky-text);
        }}

        [data-testid="stPlotlyChart"] .modebar {{
            opacity: 0;
            transition: opacity .16s ease;
        }}

        [data-testid="stPlotlyChart"]:hover .modebar {{
            opacity: .82;
        }}

        [data-testid="stDataFrame"] {{
            border-radius: 18px;
            overflow: hidden;
        }}

        [data-testid="stAppViewContainer"] > .main {{
            background: transparent;
        }}

        .block-container {{
            padding-top: calc({block_padding} + 4.15rem);
            padding-bottom: 4rem;
            max-width: 1780px;
        }}

        [data-testid="stHeader"] {{
            background: {header_bg};
            backdrop-filter: blur(22px);
            border-bottom: 1px solid var(--sky-border);
        }}

        [data-testid="stToolbar"] {{
            right: 1rem;
        }}

        [data-testid="stSidebar"] {{
            background: {sidebar_background};
            border-right: 1px solid var(--sky-border);
            box-shadow: 14px 0 42px rgba(24, 83, 132, .08);
        }}

        [data-testid="stSidebar"] > div:first-child {{
            padding-top: .75rem;
        }}

        /* V5.9.5 — garde-fou robuste : sidebar desktop visible + rail de secours */
        @media (min-width: 761px) {{
            [data-testid="stSidebar"] {{
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
            }}
            [data-testid="stSidebar"] > div:first-child {{
                display: block !important;
                visibility: visible !important;
            }}
            [data-testid="stSidebarNav"] {{
                display: block !important;
                visibility: visible !important;
            }}
        }}


        [data-testid="stSidebarNav"] a {{
            border-radius: 14px;
            margin: 4px 8px;
            color: var(--sky-muted);
            transition: all .18s ease;
            border: 1px solid transparent;
            padding-top: 4px !important;
            padding-bottom: 4px !important;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            font-weight: 720;
            letter-spacing: -.01em;
        }}

        [data-testid="stSidebarNav"] a:hover {{
            background: var(--sky-surface-soft);
            border-color: var(--sky-border);
            color: var(--sky-text);
            transform: translateX(3px);
        }}

        [data-testid="stSidebarNav"] a[aria-current="page"] {{
            background: linear-gradient(135deg, #2563EB, #0EA5E9);
            color: white !important;
            box-shadow: 0 11px 26px rgba(37,99,235,.26);
        }}

        .sky-brand {{
            background: linear-gradient(135deg, rgba(37,99,235,.99), rgba(14,165,233,.96));
            color: white;
            border-radius: 24px;
            padding: 19px 18px 17px;
            margin: 0 0 15px;
            box-shadow: 0 18px 42px rgba(37,99,235,.23);
            position: relative;
            overflow: hidden;
            animation: sky-rise .55s ease both;
        }}

        .sky-brand::before,
        .sky-brand::after {{
            content: "";
            position: absolute;
            border-radius: 50%;
            background: rgba(255,255,255,.14);
        }}

        .sky-brand::before {{
            width: 110px;
            height: 110px;
            right: -38px;
            top: -50px;
        }}

        .sky-brand::after {{
            width: 62px;
            height: 62px;
            left: -24px;
            bottom: -28px;
        }}

        .sky-brand-kicker {{
            font-size: .68rem;
            letter-spacing: .16em;
            text-transform: uppercase;
            opacity: .82;
            font-weight: 850;
        }}

        .sky-brand-title {{
            font-size: 1.22rem;
            line-height: 1.2;
            font-weight: 920;
            margin-top: 5px;
            letter-spacing: -.025em;
        }}

        .sky-brand-subtitle {{
            font-size: .78rem;
            opacity: .88;
            margin-top: 7px;
            line-height: 1.45;
        }}

        .sky-terminal-bar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            padding: 10px 14px;
            margin: 8px 0 14px;
            border-radius: 16px;
            background: var(--sky-surface);
            border: 1px solid var(--sky-border);
            box-shadow: var(--sky-shadow-soft);
            backdrop-filter: blur(18px);
            animation: sky-fade .45s ease both;
        }}

        .sky-terminal-left,
        .sky-terminal-right {{
            display: flex;
            align-items: center;
            gap: 10px;
            min-width: 0;
        }}

        .sky-terminal-logo {{
            width: 34px;
            height: 34px;
            display: grid;
            place-items: center;
            border-radius: 11px;
            color: white;
            font-weight: 900;
            background: linear-gradient(145deg, #2563EB, #38BDF8);
            box-shadow: 0 8px 20px rgba(37,99,235,.24);
        }}

        .sky-terminal-name {{
            color: var(--sky-text);
            font-weight: 900;
            letter-spacing: -.02em;
        }}

        .sky-terminal-nav {{
            color: var(--sky-muted);
            font-size: .80rem;
            white-space: nowrap;
        }}

        .sky-live-pill {{
            display: inline-flex;
            align-items: center;
            gap: 7px;
            padding: 6px 10px;
            border-radius: 999px;
            color: #047857;
            background: rgba(16,185,129,.11);
            border: 1px solid rgba(16,185,129,.22);
            font-size: .75rem;
            font-weight: 850;
            white-space: nowrap;
        }}

        .sky-live-dot {{
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: #10B981;
            box-shadow: 0 0 0 0 rgba(16,185,129,.46);
            animation: sky-pulse 1.7s infinite;
        }}

        .sky-time {{
            color: var(--sky-muted);
            font-size: .78rem;
            white-space: nowrap;
        }}

        .sky-hero {{
            position: relative;
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 24px;
            padding: 28px 30px;
            margin: 2px 0 18px;
            border: 1px solid var(--sky-border);
            border-radius: 30px;
            background: {hero_bg};
            box-shadow: var(--sky-shadow);
            backdrop-filter: blur(22px);
            animation: sky-rise .55s ease both;
        }}

        .sky-hero::before {{
            content: "";
            position: absolute;
            inset: 0;
            pointer-events: none;
            background:
                linear-gradient(110deg, rgba(37,99,235,.06), transparent 42%),
                radial-gradient(circle at 12% 110%, rgba(14,165,233,.16), transparent 28%);
        }}

        .sky-hero-copy {{
            position: relative;
            z-index: 1;
        }}

        .sky-hero-kicker {{
            display: inline-flex;
            align-items: center;
            gap: 7px;
            padding: 6px 11px;
            border-radius: 999px;
            color: #1D4ED8;
            background: rgba(219,234,254,.76);
            border: 1px solid rgba(96,165,250,.26);
            font-size: .70rem;
            letter-spacing: .10em;
            text-transform: uppercase;
            font-weight: 880;
        }}

        .sky-hero-title {{
            color: var(--sky-text);
            font-size: clamp(2rem, 3.2vw, 3.25rem);
            line-height: 1.02;
            letter-spacing: -.052em;
            margin: 13px 0 9px;
            font-weight: 940;
        }}

        .sky-hero-subtitle {{
            color: var(--sky-muted);
            font-size: 1rem;
            line-height: 1.58;
            max-width: 980px;
            white-space: pre-line;
        }}

        .sky-hero-chips {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 15px;
        }}

        .sky-chip {{
            padding: 6px 10px;
            border-radius: 999px;
            background: var(--sky-surface-soft);
            border: 1px solid var(--sky-border);
            color: var(--sky-muted);
            font-size: .72rem;
            font-weight: 760;
        }}

        .sky-hero-icon {{
            position: relative;
            z-index: 1;
            flex: 0 0 auto;
            width: 88px;
            height: 88px;
            display: grid;
            place-items: center;
            border-radius: 28px;
            font-size: 2.35rem;
            background: linear-gradient(145deg, #2563EB, #38BDF8);
            box-shadow: 0 20px 42px rgba(37,99,235,.27);
            border: 1px solid rgba(255,255,255,.58);
            animation: sky-float 4.5s ease-in-out infinite;
        }}

        .sky-launchpad-title {{
            color: var(--sky-muted);
            font-size: .73rem;
            text-transform: uppercase;
            letter-spacing: .12em;
            font-weight: 850;
            margin: 2px 0 9px;
        }}

        [data-testid="stPageLink"] a {{
            min-height: 72px;
            border-radius: 18px;
            background: var(--sky-surface);
            border: 1px solid var(--sky-border);
            color: var(--sky-text) !important;
            box-shadow: var(--sky-shadow-soft);
            transition: all .18s ease;
            backdrop-filter: blur(18px);
            font-weight: 820;
        }}

        [data-testid="stPageLink"] a:hover {{
            transform: translateY(-3px);
            border-color: rgba(37,99,235,.35);
            box-shadow: 0 16px 36px rgba(37,99,235,.14);
        }}

        .sky-ticker-wrap {{
            overflow: hidden;
            border-radius: 16px;
            border: 1px solid var(--sky-border);
            background: var(--sky-surface);
            box-shadow: var(--sky-shadow-soft);
            margin: 10px 0 16px;
        }}

        .sky-ticker-track {{
            display: flex;
            width: max-content;
            gap: 10px;
            padding: 9px 11px;
            animation: sky-scroll 34s linear infinite;
        }}

        .sky-ticker-wrap:hover .sky-ticker-track {{
            animation-play-state: paused;
        }}

        .sky-ticker-item {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 10px;
            border-radius: 11px;
            background: var(--sky-surface-soft);
            border: 1px solid var(--sky-border);
            white-space: nowrap;
            color: var(--sky-text);
            font-size: .78rem;
            font-weight: 770;
        }}

        .sky-up {{ color: #059669; }}
        .sky-down {{ color: #DC2626; }}


        .sky-hero-search-card {{
            margin: -4px 0 18px;
            padding: 16px 18px 10px;
            border-radius: 22px;
            background: var(--sky-surface);
            border: 1px solid var(--sky-border);
            box-shadow: var(--sky-shadow-soft);
            backdrop-filter: blur(18px);
            animation: sky-fade .4s ease both;
        }}

        .sky-hero-search-title {{
            color: var(--sky-text);
            font-size: .86rem;
            font-weight: 850;
            margin-bottom: 4px;
            letter-spacing: -.01em;
        }}

        .sky-hero-search-note {{
            color: var(--sky-muted);
            font-size: .78rem;
            margin-bottom: 10px;
        }}
        h1, h2, h3, h4, h5, h6 {{
            color: var(--sky-text) !important;
            letter-spacing: -.028em;
        }}

        h2 {{
            margin-top: 1.35rem !important;
        }}

        p, label, .stCaption, [data-testid="stCaptionContainer"] {{
            color: var(--sky-muted);
        }}

        [data-testid="stMetric"] {{
            background: {metric_bg};
            border: 1px solid var(--sky-border);
            padding: {metric_padding};
            border-radius: 20px;
            min-height: {metric_height};
            box-shadow: var(--sky-shadow-soft);
            transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
            animation: sky-rise .45s ease both;
        }}

        [data-testid="stMetric"]:hover {{
            transform: translateY(-3px);
            box-shadow: 0 18px 38px rgba(30, 102, 158, .15);
            border-color: rgba(37,99,235,.34);
        }}

        [data-testid="stMetricLabel"] {{
            color: var(--sky-muted);
            font-weight: 740;
        }}

        [data-testid="stMetricValue"] {{
            color: var(--sky-text);
            font-weight: 900;
            letter-spacing: -.038em;
        }}

        [data-testid="stMetricDelta"] {{
            font-weight: 790;
        }}

        [data-testid="stPlotlyChart"],
        [data-testid="stDataFrame"],
        [data-testid="stTable"],
        [data-testid="stForm"],
        [data-testid="stExpander"],
        [data-testid="stAlert"] {{
            border-radius: 20px;
        }}

        [data-testid="stPlotlyChart"] {{
            overflow: hidden;
            background: var(--sky-plot);
            border: 1px solid var(--sky-border);
            box-shadow: var(--sky-shadow-soft);
            padding: 8px;
            backdrop-filter: blur(18px);
            animation: sky-fade .45s ease both;
        }}

        [data-testid="stDataFrame"] {{
            overflow: hidden;
            border: 1px solid var(--sky-border);
            box-shadow: var(--sky-shadow-soft);
        }}

        [data-testid="stForm"], [data-testid="stExpander"] {{
            background: var(--sky-surface-soft);
            border: 1px solid var(--sky-border) !important;
            box-shadow: var(--sky-shadow-soft);
        }}

        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        div[data-baseweb="textarea"] > div,
        [data-testid="stNumberInput"] input,
        [data-testid="stTextInput"] input {{
            background: var(--sky-input) !important;
            border-color: var(--sky-border) !important;
            border-radius: 14px !important;
            color: var(--sky-text) !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.05);
        }}

        [data-testid="stMultiSelect"] span[data-baseweb="tag"] {{
            background: linear-gradient(135deg, #2563EB, #0EA5E9) !important;
            color: white !important;
            border-radius: 999px !important;
            border: none !important;
        }}

        [data-testid="stSlider"] [role="slider"] {{
            background: #2563EB !important;
            border: 3px solid white !important;
            box-shadow: 0 5px 15px rgba(37,99,235,.25);
        }}

        .stButton > button,
        .stDownloadButton > button,
        [data-testid="stFormSubmitButton"] button {{
            border-radius: 999px !important;
            min-height: 42px;
            border: 1px solid rgba(37,99,235,.22) !important;
            background: linear-gradient(135deg, #2563EB, #0EA5E9) !important;
            color: #FFFFFF !important;
            font-weight: 820 !important;
            box-shadow: 0 9px 22px rgba(37,99,235,.22);
            transition: all .18s ease;
        }}

        .stButton > button *,
        .stDownloadButton > button *,
        [data-testid="stFormSubmitButton"] button * {{
            color: #FFFFFF !important;
            opacity: 1 !important;
        }}

        .stButton > button:hover,
        .stDownloadButton > button:hover,
        [data-testid="stFormSubmitButton"] button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 14px 30px rgba(37,99,235,.29);
        }}

        [data-baseweb="tab-list"] {{
            gap: 8px;
            background: var(--sky-surface-soft);
            border: 1px solid var(--sky-border);
            padding: 7px;
            border-radius: 17px;
            box-shadow: var(--sky-shadow-soft);
        }}

        [data-baseweb="tab"] {{
            height: 42px;
            border-radius: 12px;
            padding: 0 16px;
            color: var(--sky-muted);
            font-weight: 760;
        }}

        [aria-selected="true"][data-baseweb="tab"] {{
            background: linear-gradient(135deg, #2563EB, #0EA5E9);
            color: white !important;
            box-shadow: 0 8px 18px rgba(37,99,235,.20);
        }}

        [data-baseweb="tab-highlight"] {{
            display: none;
        }}

        hr {{
            border-color: var(--sky-border) !important;
        }}

        [data-testid="stAlert"] {{
            border: 1px solid var(--sky-border);
            box-shadow: var(--sky-shadow-soft);
        }}

        .market-open {{ color:#10B981; font-weight:850; }}
        .market-closed {{ color:#EF4444; font-weight:850; }}

        .sky-footer {{
            margin-top: 30px;
            padding: 17px 18px;
            border-radius: 18px;
            border: 1px solid var(--sky-border);
            background: var(--sky-surface-soft);
            color: var(--sky-muted);
            font-size: .82rem;
            line-height: 1.55;
            text-align: center;
        }}

        @keyframes sky-rise {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        @keyframes sky-fade {{
            from {{ opacity: 0; }}
            to {{ opacity: 1; }}
        }}

        @keyframes sky-float {{
            0%, 100% {{ transform: translateY(0); }}
            50% {{ transform: translateY(-7px); }}
        }}

        @keyframes sky-pulse {{
            0% {{ box-shadow: 0 0 0 0 rgba(16,185,129,.48); }}
            70% {{ box-shadow: 0 0 0 8px rgba(16,185,129,0); }}
            100% {{ box-shadow: 0 0 0 0 rgba(16,185,129,0); }}
        }}

        @keyframes sky-scroll {{
            from {{ transform: translateX(0); }}
            to {{ transform: translateX(-50%); }}
        }}

        .sky-command-hint {{
            display:inline-flex;align-items:center;gap:6px;padding:5px 9px;border-radius:9px;
            background:var(--sky-surface-soft);border:1px solid var(--sky-border);
            color:var(--sky-muted);font-size:.72rem;font-weight:760;
        }}
        .sky-kbd {{
            padding:2px 6px;border-radius:6px;background:var(--sky-surface-strong);
            border:1px solid var(--sky-border);box-shadow:0 1px 2px rgba(0,0,0,.08);
            color:var(--sky-text);font-size:.68rem;
        }}
        .sky-skeleton {{
            min-height:100px;border-radius:18px;position:relative;overflow:hidden;
            background:var(--sky-surface-soft);border:1px solid var(--sky-border);
        }}
        .sky-skeleton::after {{
            content:"";position:absolute;inset:0;transform:translateX(-100%);
            background:linear-gradient(90deg,transparent,rgba(255,255,255,.45),transparent);
            animation:sky-shimmer 1.4s infinite;
        }}
        .sky-mobile-nav {{ display:none; }}
        @keyframes sky-shimmer {{ 100% {{ transform:translateX(100%); }} }}

        /* Anatole V5 — mobile first refinements */
        .sky-mobile-only {{ display:none; }}
        .sky-quality-chip {{
            display:inline-flex;align-items:center;gap:7px;padding:7px 10px;
            border-radius:999px;background:var(--sky-surface-soft);
            border:1px solid var(--sky-border);font-size:.78rem;font-weight:800;
            color:var(--sky-muted);margin:2px 4px 2px 0;
        }}
        .sky-home-grid {{
            display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:12px 0 18px;
        }}
        .sky-home-panel {{
            border:1px solid var(--sky-border);background:var(--sky-surface);
            border-radius:22px;padding:16px;box-shadow:var(--sky-shadow-soft);
            min-height:124px;
        }}
        .sky-home-panel-title {{
            color:var(--sky-muted);font-size:.74rem;text-transform:uppercase;
            letter-spacing:.08em;font-weight:900;margin-bottom:8px;
        }}
        .sky-home-panel-value {{font-size:1.35rem;font-weight:900;color:var(--sky-text);line-height:1.15;}}
        .sky-home-panel-text {{color:var(--sky-muted);font-size:.88rem;margin-top:6px;line-height:1.38;}}
        .sky-universe-strip {{
            margin: -2px 0 18px 0;
            padding: 11px 14px;
            border-radius: 18px;
            border: 1px solid var(--sky-border);
            background: var(--sky-surface-soft);
            box-shadow: var(--sky-shadow-soft);
        }}
        .sky-universe-strip [role="radiogroup"] {{
            gap: 8px;
        }}
        .sky-universe-strip label {{
            font-weight: 800;
        }}

        @media (max-width: 650px) {{
            .sky-mobile-only {{ display:block; }}
            .sky-home-grid {{grid-template-columns:1fr;gap:10px;}}
            .sky-home-panel {{min-height:auto;padding:14px;border-radius:18px;}}
            .sky-home-panel-value {{font-size:1.15rem;}}
            .sky-hero {{
                padding:18px 16px !important;
                border-radius:20px !important;
                margin-bottom:12px !important;
            }}
            .sky-hero-title {{font-size:1.55rem !important;line-height:1.1 !important;}}
            .sky-hero-subtitle {{font-size:.9rem !important;line-height:1.38 !important;}}
            .sky-hero-chips {{gap:6px !important;}}
            .sky-chip {{font-size:.68rem !important;padding:5px 8px !important;}}
            div[data-testid="stMetric"] {{
                min-height:auto !important;
            }}
            div[data-testid="stMetric"] label {{
                font-size:.72rem !important;
            }}
            div[data-testid="stMetricValue"] {{
                font-size:1.05rem !important;
            }}
            .stPlotlyChart {{
                overflow-x:auto;
            }}
            [data-testid="stDataFrame"] {{
                max-width:100%;
                overflow-x:auto;
            }}
            div[data-testid="stHorizontalBlock"] {{
                gap:.7rem !important;
            }}
            button, div[role="button"], .stButton button {{
                min-height:42px !important;
            }}
        }}




        /* Anatole V5.1 — mobile magic polish */
        html {{ -webkit-tap-highlight-color: transparent; scroll-behavior: smooth; }}
        body {{ overscroll-behavior-y: contain; }}
        .sky-terminal-bar {{
            position: sticky;
            top: .6rem;
            z-index: 900;
        }}
        .sky-command-link {{
            display:inline-flex;
            align-items:center;
            gap:7px;
        }}
        @media (max-width: 760px) {{
            .block-container {{
                padding-left: .78rem !important;
                padding-right: .78rem !important;
                padding-top: .72rem !important;
                padding-bottom: calc(5.6rem + env(safe-area-inset-bottom, 0px)) !important;
                max-width: 100% !important;
            }}
            header[data-testid="stHeader"] {{
                height: 0 !important;
                min-height: 0 !important;
                visibility: hidden !important;
            }}
            .sky-terminal-bar {{
                top: .35rem;
                border-radius: 18px;
                padding: 8px 9px !important;
                margin-bottom: .72rem !important;
                box-shadow: 0 16px 42px rgba(15,39,66,.13);
            }}
            .sky-terminal-left {{
                gap: 8px !important;
                min-width: 0;
            }}
            .sky-terminal-logo {{
                width: 34px !important;
                height: 34px !important;
                border-radius: 12px !important;
                flex: 0 0 auto;
            }}
            .sky-command-hint {{
                font-size: .72rem !important;
                min-height: 34px;
                display:flex;
                align-items:center;
                justify-content:center;
            }}
            .sky-live-pill {{
                padding: 7px 9px !important;
                font-size: .72rem !important;
                white-space: nowrap;
            }}
            .sky-hero {{
                padding: 16px 14px !important;
                border-radius: 22px !important;
                margin-bottom: 10px !important;
                box-shadow: 0 18px 48px rgba(15,39,66,.10) !important;
            }}
            .sky-hero-kicker {{
                font-size: .64rem !important;
                letter-spacing: .09em !important;
                padding: 6px 9px !important;
            }}
            .sky-hero-title {{
                font-size: 1.72rem !important;
                letter-spacing: -.04em !important;
                line-height: 1.04 !important;
            }}
            .sky-hero-subtitle {{
                font-size: .92rem !important;
                line-height: 1.35 !important;
                margin-top: 8px !important;
            }}
            .sky-hero-chips {{
                overflow-x: auto;
                flex-wrap: nowrap !important;
                -webkit-overflow-scrolling: touch;
                padding-bottom: 3px;
                scrollbar-width: none;
            }}
            .sky-hero-chips::-webkit-scrollbar {{ display:none; }}
            .sky-chip {{
                flex: 0 0 auto;
                font-size: .68rem !important;
            }}
            .sky-universe-strip {{
                position: sticky;
                top: 4.65rem;
                z-index: 750;
                margin: 0 0 12px 0 !important;
                padding: 9px 10px !important;
                border-radius: 17px !important;
                backdrop-filter: blur(22px);
            }}
            .sky-universe-strip [role="radiogroup"] {{
                display: grid !important;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 6px !important;
            }}
            .sky-universe-strip label {{
                justify-content: center;
                text-align: center;
                min-height: 38px;
                border-radius: 12px;
            }}
            div[data-testid="stMetric"] {{
                border-radius: 16px !important;
                padding: 10px 10px !important;
            }}
            div[data-testid="stMetricValue"] {{
                font-size: 1.08rem !important;
                line-height: 1.1 !important;
            }}
            div[data-testid="stHorizontalBlock"] {{
                flex-wrap: wrap !important;
            }}
            [data-testid="stDataFrame"] {{
                border-radius: 16px !important;
                overflow: hidden !important;
            }}
            .stPlotlyChart {{
                border-radius: 18px;
                overflow: hidden;
                touch-action: manipulation;
            }}
            div[data-testid="stSelectbox"], div[data-testid="stMultiSelect"] {{
                min-width: 100%;
            }}
            div[data-testid="stSegmentedControl"] {{
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
            }}
            div[data-testid="stSegmentedControl"] label {{
                min-height: 39px;
                white-space: nowrap;
            }}
            .sky-mobile-nav {{
                bottom: max(10px, env(safe-area-inset-bottom, 0px)) !important;
                left: 8px !important;
                right: 8px !important;
                padding: 7px !important;
                border-radius: 22px !important;
                background: color-mix(in srgb, var(--sky-surface-strong) 92%, transparent) !important;
                box-shadow: 0 18px 46px rgba(15,39,66,.22) !important;
            }}
            .sky-mobile-nav a {{
                min-height: 48px;
                display:flex;
                flex-direction:column;
                align-items:center;
                justify-content:center;
                gap:2px;
                border-radius: 15px !important;
                font-size: .66rem !important;
            }}
            .sky-mobile-nav a.active {{
                color: #fff !important;
                background: linear-gradient(135deg, #2563EB, #0EA5E9) !important;
                box-shadow: 0 8px 20px rgba(37,99,235,.22);
            }}
            .sky-footer {{
                margin-bottom: 88px;
            }}
        }}

        @media (prefers-reduced-motion: reduce) {{
            *, *::before, *::after {{
                animation-duration: .01ms !important;
                animation-iteration-count: 1 !important;
                scroll-behavior: auto !important;
            }}
        }}

        @media (max-width: 980px) {{
            .block-container {{
                padding-left: 1rem;
                padding-right: 1rem;
                padding-top: 5.2rem;
            }}
            .sky-terminal-nav {{
                display: none;
            }}
            .sky-hero {{
                padding: 22px;
                border-radius: 23px;
            }}
            .sky-hero-icon {{
                width: 64px;
                height: 64px;
                border-radius: 19px;
            }}
            .sky-terminal-bar {{
                padding: 9px 11px;
            }}
        }}

        /* V5.9.4 — le menu latéral reste accessible sur ordinateur, même si la fenêtre est étroite.
           On ne masque la sidebar que sur les vrais écrans tactiles étroits. */
        @media (max-width: 650px) {{
            .block-container {{ padding-bottom: 6.5rem; }}
            .sky-hero-icon {{
                display: none;
            }}
            .sky-terminal-name {{
                display: none;
            }}
            .sky-time {{
                display: none;
            }}
        }}

        @media (max-width: 650px) and (hover: none) and (pointer: coarse) {{
            [data-testid="stSidebar"] {{ display:none; }}
            .sky-mobile-nav {{
                display:flex;position:fixed;z-index:9999;left:10px;right:10px;bottom:10px;
                justify-content:space-around;gap:4px;padding:8px;border-radius:18px;
                background:var(--sky-surface-strong);border:1px solid var(--sky-border);
                box-shadow:0 16px 40px rgba(0,0,0,.20);backdrop-filter:blur(20px);
            }}
            .sky-mobile-nav a {{
                flex:1;text-align:center;text-decoration:none;color:var(--sky-muted);
                font-size:.68rem;font-weight:800;padding:8px 3px;border-radius:11px;
            }}
            .sky-mobile-nav a:hover {{ background:rgba(37,99,235,.12);color:var(--sky-text); }}
        }}

        /* V5.7.7 — mobile premium polish */
        @media (max-width: 760px) {{
            .block-container {{
                padding-left: .88rem !important;
                padding-right: .88rem !important;
                padding-bottom: calc(6.3rem + env(safe-area-inset-bottom, 0px)) !important;
                max-width: 100% !important;
            }}
            .sky-terminal-bar {{
                position: sticky !important;
                top: .45rem !important;
                z-index: 950 !important;
                border-radius: 22px !important;
                box-shadow: 0 18px 48px rgba(15,39,66,.14) !important;
                backdrop-filter: blur(24px) saturate(1.15) !important;
            }}
            .sky-hero {{
                border-radius: 24px !important;
                padding: 18px 16px !important;
                margin-bottom: 14px !important;
            }}
            .sky-hero-title, h1 {{
                font-size: clamp(2.05rem, 11vw, 3.1rem) !important;
                letter-spacing: -.055em !important;
                line-height: 1.02 !important;
            }}
            h2 {{ font-size: 1.55rem !important; letter-spacing: -.035em !important; }}
            h3 {{ font-size: 1.12rem !important; }}
            p, .stMarkdown, [data-testid="stCaptionContainer"] {{
                line-height: 1.55 !important;
            }}
            div[data-testid="stMetric"] {{
                border-radius: 20px !important;
                min-height: 92px !important;
            }}
            div[data-testid="stMetricValue"] {{
                font-size: 1.28rem !important;
                line-height: 1.05 !important;
            }}
            .stPlotlyChart {{
                border-radius: 24px !important;
                overflow: hidden !important;
                border: 1px solid var(--sky-border) !important;
                box-shadow: 0 18px 44px rgba(15,39,66,.08) !important;
                background: rgba(255,255,255,.56) !important;
                touch-action: pan-y !important;
            }}
            .stPlotlyChart .modebar,
            .stPlotlyChart .modebar-container,
            .stPlotlyChart .draglayer {{
                display: none !important;
                pointer-events: none !important;
            }}
            .stTabs [data-baseweb="tab-list"] {{
                gap: 6px !important;
                overflow-x: auto !important;
                scrollbar-width: none !important;
                padding-bottom: 4px !important;
            }}
            .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {{ display:none !important; }}
            .stTabs [data-baseweb="tab"] {{
                border-radius: 999px !important;
                min-width: max-content !important;
                padding: 10px 14px !important;
                background: rgba(255,255,255,.68) !important;
                border: 1px solid var(--sky-border) !important;
                box-shadow: 0 8px 18px rgba(15,39,66,.05) !important;
            }}
            .stSelectbox, .stTextInput, .stNumberInput, .stMultiSelect {{
                border-radius: 18px !important;
            }}
            .sky-mobile-nav {{
                left: 18px !important;
                right: 18px !important;
                bottom: calc(18px + env(safe-area-inset-bottom, 0px)) !important;
                border-radius: 28px !important;
                padding: 10px 10px !important;
                box-shadow: 0 22px 60px rgba(15,39,66,.18) !important;
                backdrop-filter: blur(28px) saturate(1.2) !important;
            }}
            .sky-mobile-nav a {{
                border-radius: 20px !important;
                padding: 8px 7px !important;
                transition: transform .16s ease, background .16s ease, color .16s ease !important;
            }}
            .sky-mobile-nav a:active {{ transform: scale(.96); }}
        }}

    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
    hide_streamlit_chrome()
    force_anatole_browser_brand(str(st.session_state.get("_anatole_page_title", "Anatole")))
    enforce_same_tab_navigation()
    install_sidebar_rescue_navigation()
    _install_theme_persistence_bridge(str(st.session_state.get("_anatole_theme", current_theme)))
    try:
        from core.mobile_experience import install_mobile_viewport_probe
        install_mobile_viewport_probe()
    except Exception:
        pass


    if not bool(st.session_state.get("show_animations", True)):
        st.markdown(
            """
            <style>
                *, *::before, *::after {
                    animation: none !important;
                    transition-duration: 0.01ms !important;
                }
            </style>
            """,
            unsafe_allow_html=True,
        )


def sidebar_context() -> str:
    init_db()

    from core.public_beta import current_context
    from core.notifications import unread_count

    # Le profil et ses préférences doivent être chargés AVANT la création
    # des widgets qui utilisent les mêmes clés de session.
    active_profile = st.session_state.get("profile", DEFAULT_PROFILE)
    context = current_context()

    if context.public_beta:
        profile = ensure_profile(context.profile)
    else:
        profile = ensure_profile(active_profile)

    st.session_state.profile = profile
    requested_theme = _normalized_theme(_query_param_value(THEME_QUERY_PARAM))
    if requested_theme:
        _apply_theme_choice(profile, requested_theme, save=True)
    hydrate_preferences(profile)
    if requested_theme:
        st.session_state["theme_toggle"] = requested_theme == "dark"
        st.session_state["_anatole_theme"] = requested_theme
    else:
        st.session_state["theme_toggle"] = True
        st.session_state["_anatole_theme"] = "dark"

    st.sidebar.markdown(
        """
        <div class="sky-brand">
            <div class="sky-brand-kicker">Market intelligence</div>
            <div class="sky-brand-title">Anatole</div>
            <div class="sky-brand-subtitle">Données, signaux, portefeuille et actualités dans un seul terminal.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.caption("Recherche intégrée : disponible dans le cockpit.")

    from core.universe import render_universe_selector

    render_universe_selector(profile)

    # Les valeurs existent déjà dans session_state grâce à hydrate_preferences.
    # Ne pas fournir value= évite tout conflit entre la valeur du widget
    # et la valeur persistée.
    st.sidebar.toggle(
        "Terminal sombre",
        key="theme_toggle",
        help="Activé par défaut. Désactive uniquement si tu veux utiliser le thème bleu ciel optionnel.",
    )
    st.sidebar.toggle(
        "Affichage compact",
        key="compact_toggle",
        help="Réduit légèrement l'espacement et la hauteur des cartes.",
    )

    sidebar_pref_signature = (
        profile,
        bool(st.session_state.get("theme_toggle", False)),
        bool(st.session_state.get("compact_toggle", False)),
    )
    if st.session_state.get("_sidebar_preference_signature") != sidebar_pref_signature:
        selected_theme = "dark" if sidebar_pref_signature[1] else "light"
        save_preferences(
            profile,
            {
                "theme": selected_theme,
                "density": "compact" if sidebar_pref_signature[2] else "comfortable",
            },
        )
        st.session_state["_anatole_theme"] = selected_theme
        _set_query_param_value(THEME_QUERY_PARAM, selected_theme)
        st.session_state["_sidebar_preference_signature"] = sidebar_pref_signature
        _install_theme_persistence_bridge(selected_theme)

    if context.public_beta:
        identity_label = context.display_name
        if context.email:
            st.sidebar.caption(f"Connecté : **{identity_label}**")
            st.sidebar.caption(context.email)
            if st.sidebar.button("Se déconnecter", use_container_width=True):
                st.logout()
        else:
            st.sidebar.caption("Session : **Invité temporaire**")
            st.sidebar.caption(
                "Les données de cette session ne sont pas garanties après fermeture."
            )
    else:
        profile_input = st.sidebar.text_input(
            "Profil local",
            value=profile,
            help="Profil utilisé uniquement pour le développement local.",
        )
        requested_profile = ensure_profile(profile_input)
        if requested_profile != profile:
            st.session_state.profile = requested_profile
            st.session_state.pop("_preferences_profile", None)
            st.rerun()
        profile = requested_profile

    unread = unread_count(profile)
    st.sidebar.page_link(
        "screens/16_Notifications.py",
        label=f"Centre de notifications ({unread})",
        icon="🔔",
        width="stretch",
    )

    st.sidebar.page_link(
        "screens/17_Preferences.py",
        label="Préférences d'affichage",
        icon="⚙️",
        width="stretch",
    )

    is_open, label = market_status()
    css = "market-open" if is_open else "market-closed"
    st.sidebar.markdown(
        f'<div style="padding:10px 12px;border-radius:14px;'
        f'background:var(--sky-surface-soft);border:1px solid var(--sky-border);">'
        f'<span class="{css}">● {html.escape(label)}</span>'
        "</div>",
        unsafe_allow_html=True,
    )
    st.sidebar.caption("Statut indicatif; les jours fériés ne sont pas tous intégrés.")
    st.sidebar.divider()
    if not current_context().public_beta:
        st.sidebar.caption(f"Profil actif : **{profile}**")
    else:
        st.sidebar.caption("Version : **Bêta publique**")

    if bool(st.session_state.get("show_mobile_nav", True)):
        mobile_navigation()

    return profile

def terminal_topbar() -> None:
    now = datetime.now(TORONTO_TZ)
    is_open, _ = market_status()
    live_label = "Marché ouvert" if is_open else "Marché fermé"
    st.markdown(
        f"""
        <div class="sky-terminal-bar">
            <div class="sky-terminal-left">
                <div class="sky-terminal-logo">S</div>
                <div class="sky-terminal-nav">Marchés&nbsp;&nbsp;•&nbsp;&nbsp;Screener&nbsp;&nbsp;•&nbsp;&nbsp;Portefeuille&nbsp;&nbsp;•&nbsp;&nbsp;Actualités</div>
            </div>
            <div class="sky-terminal-right">
                <div class="sky-live-pill"><span class="sky-live-dot"></span>{html.escape(live_label)}</div>
                <div class="sky-time">{now:%H:%M:%S ET}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )




# V5.7.4 global hotfix: keep the full UI helper surface available.
NO_UNIVERSE_SELECTOR_TITLES = {
    "Diagnostics et qualité des données",
    "Espaces de travail personnalisables",
    "Rapports",
    "Assistant financier",
    "Centre de notifications",
    "Préférences",
    "Votre avis sur Anatole",
    "Avis de confidentialité",
    "Conditions d’utilisation de la bêta",
    "État de la bêta publique",
    "IPO à venir",
    "ETF sectoriels",
}

def page_header(
    title: str,
    subtitle: str,
    icon: str = "📈",
    show_hero_search: bool = False,
    hero_search_profile: str | None = None,
    show_universe_selector: bool = True,
) -> None:
    """Render the page header without raw HTML blocks.

    V5.7.5 hotfix: use native Streamlit elements for the hero header. This
    avoids Streamlit/Render showing literal HTML tags on some pages while
    keeping the app stable across all sections.
    """
    terminal_topbar()

    title_text = str(title or "")
    subtitle_text = str(subtitle or "")
    try:
        from core.live_refresh import apply_auto_live_refresh

        apply_auto_live_refresh(title_text)
    except Exception:
        # Le moteur live ne doit jamais empêcher une page de s'afficher.
        pass
    icon_text = str(icon or "📈")
    # Garde-fou : le troisième argument de page_header doit rester une icône.
    # Si une page passe accidentellement une phrase, on évite le débordement
    # visuel dans le hero, surtout en mobile.
    if len(icon_text.strip()) > 4 or any(ch.isspace() for ch in icon_text):
        icon_text = "📈"
    show_market_universe = bool(show_universe_selector) and title_text not in NO_UNIVERSE_SELECTOR_TITLES

    chips: list[str] = []
    if show_market_universe:
        try:
            chips.append(str(current_universe().short_label))
        except Exception:
            pass
    chips.extend(["Données de marché", "Analyse claire", "Actualités", "Bêta"])

    chip_html = "".join(
        f'<span class="sky-chip">{html.escape(chip)}</span>'
        for chip in chips
        if chip
    )
    st.markdown(
        f"""
        <section class="sky-hero sky-hero-pro">
            <div class="sky-hero-copy">
                <div class="sky-hero-kicker"><span>●</span> Bêta publique sur Render</div>
                <div class="sky-hero-title">{html.escape(title_text)}</div>
                <div class="sky-hero-subtitle">{html.escape(subtitle_text)}</div>
                <div class="sky-hero-chips">{chip_html}</div>
            </div>
            <div class="sky-hero-icon" aria-hidden="true">{html.escape(icon_text)}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    if show_hero_search:
        try:
            from core.search import render_universal_search

            st.subheader("Recherche rapide")
            st.caption("Tape un symbole, un ISIN ou le nom d’un titre pour le retrouver rapidement.")
            render_universal_search(
                location="page",
                profile=hero_search_profile,
                label="Recherche rapide",
                placeholder="Symbole, ISIN ou nom du titre…",
                navigate_on_select=False,
                show_inline_results=True,
            )
        except Exception:
            pass

    if show_market_universe:
        try:
            from core.universe import render_universe_selector_inline

            render_universe_selector_inline(
                st.session_state.get("profile", DEFAULT_PROFILE),
                key_suffix=title_text.lower().replace(" ", "_").replace("'", ""),
            )
        except Exception:
            # Le sélecteur d'univers ne doit jamais empêcher la page de s'afficher.
            pass

    if bool(st.session_state.get("show_mobile_nav", True)):
        mobile_navigation()

def summary_card(text: str, label: str = "Résumé du marché") -> None:
    st.markdown(
        f"""
        <div class="sky-summary">
            <div class="sky-summary-label">{html.escape(label)}</div>
            <div class="sky-summary-text">{html.escape(text)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def home_launchpad() -> None:
    st.markdown('<div class="sky-launchpad-title">Accès rapide</div>', unsafe_allow_html=True)
    columns = st.columns(4)
    with columns[0]:
        st.page_link("screens/1_Screener.py", label="Screener avancé", icon="🔎", width="stretch")
    with columns[1]:
        st.page_link("screens/2_Comparateur.py", label="Comparer des titres", icon="⚖️", width="stretch")
    with columns[2]:
        st.page_link("screens/3_Portefeuille.py", label="Mon portefeuille", icon="💼", width="stretch")
    with columns[3]:
        st.page_link("screens/23_Psychologie.py", label="Psychologie du marché", icon="🧠", width="stretch")
    st.page_link("screens/5_Actualites.py", label="Flux d'actualités", icon="📰", width="stretch")


def ticker_tape(items: Iterable[dict]) -> None:
    cards = []
    for item in items:
        ticker = html.escape(str(item.get("ticker", "N/D")))
        price = html.escape(str(item.get("price", "N/D")))
        change_value = item.get("change")
        try:
            change_number = float(change_value)
            change_text = f"{change_number:+.2f}%"
            css_class = "sky-up" if change_number >= 0 else "sky-down"
        except (TypeError, ValueError):
            change_text = "N/D"
            css_class = ""
        cards.append(
            f'<span class="sky-ticker-item"><strong>{ticker}</strong>'
            f'<span>{price}</span><span class="{css_class}">{change_text}</span></span>'
        )

    if not cards:
        return

    repeated = "".join(cards + cards)
    st.markdown(
        f'<div class="sky-ticker-wrap"><div class="sky-ticker-track">{repeated}</div></div>',
        unsafe_allow_html=True,
    )




def render_mobile_watchlist_card(
    ticker: str,
    name: str,
    sector: str,
    price: str,
    change: str,
    volume: str,
) -> None:
    """Carte mobile pure HTML/CSS, sans JavaScript, pour la watchlist."""
    st.markdown(
        f"""
        <div class="sky-mobile-card">
            <div class="sky-mobile-card-top">
                <div>
                    <div class="sky-mobile-card-title">{html.escape(str(ticker))}</div>
                    <div class="sky-mobile-card-sub">{html.escape(str(name))}</div>
                </div>
                <div class="sky-mobile-card-sector">{html.escape(str(sector))}</div>
            </div>
            <div class="sky-mobile-card-grid">
                <div class="sky-mobile-stat">
                    <div class="sky-mobile-stat-label">Prix</div>
                    <div class="sky-mobile-stat-value">{html.escape(str(price))}</div>
                </div>
                <div class="sky-mobile-stat">
                    <div class="sky-mobile-stat-label">Variation</div>
                    <div class="sky-mobile-stat-value">{html.escape(str(change))}</div>
                </div>
                <div class="sky-mobile-stat">
                    <div class="sky-mobile-stat-label">Volume</div>
                    <div class="sky-mobile-stat-value">{html.escape(str(volume))}</div>
                </div>
                <div class="sky-mobile-stat">
                    <div class="sky-mobile-stat-label">Lecture</div>
                    <div class="sky-mobile-stat-value">Suivi</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )



def plotly_mobile_config(*, interactive: bool = False) -> dict:
    """Configuration Plotly stable pour Render/mobile."""
    try:
        from core.device import mobile_mode_enabled
        is_mobile = bool(mobile_mode_enabled())
    except Exception:
        is_mobile = False
    config = {
        "displayModeBar": False,
        "displaylogo": False,
        "responsive": True,
        "scrollZoom": False,
        "doubleClick": False,
        "modeBarButtonsToRemove": [
            "zoom2d", "pan2d", "select2d", "lasso2d",
            "zoomIn2d", "zoomOut2d", "autoScale2d", "resetScale2d",
        ],
    }
    if is_mobile and not interactive:
        config["staticPlot"] = True
    return config

def mobile_navigation() -> None:
    """Navigation mobile stable qui conserve aussi le thème actif."""
    if not bool(st.session_state.get("show_mobile_nav", True)):
        return
    st.markdown(
        f"""
        <nav class="sky-mobile-nav" aria-label="Navigation mobile Anatole">
          <a data-path="cockpit" href="/{html.escape(_navigation_query_suffix(nav='cockpit'), quote=True)}" target="_self" aria-label="Accueil">🏠<br>Accueil</a>
          <a data-path="terminal" href="/{html.escape(_navigation_query_suffix(nav='terminal'), quote=True)}" target="_self" aria-label="Terminal Pro">💎<br>Terminal</a>
          <a data-path="screener" href="/{html.escape(_navigation_query_suffix(nav='screener'), quote=True)}" target="_self" aria-label="Screener">🔎<br>Screener</a>
          <a data-path="focus" href="/{html.escape(_navigation_query_suffix(nav='focus'), quote=True)}" target="_self" aria-label="Focus">🎯<br>Focus</a>
          <a data-path="watchlist" href="/{html.escape(_navigation_query_suffix(nav='watchlist'), quote=True)}" target="_self" aria-label="Liste">⭐<br>Liste</a>
        </nav>
        <script>
        (function() {{
          try {{
            const params = new URLSearchParams(window.location.search || '');
            const nav = (params.get('nav') || '').toLowerCase();
            const path = window.location.pathname.toLowerCase().replace(/^\//, '');
            document.querySelectorAll('.sky-mobile-nav a').forEach((node) => {{
              const target = (node.getAttribute('data-path') || '').toLowerCase();
              const active = target && (nav === target || path.startsWith(target) || (!nav && !path && target === 'cockpit'));
              node.classList.toggle('active', Boolean(active));
            }});
          }} catch (error) {{}}
        }})();
        </script>
        """,
        unsafe_allow_html=True,
    )

def skeleton_cards(count: int = 4, height: int = 110) -> None:
    columns = st.columns(count)
    for column in columns:
        column.markdown(
            f'<div class="sky-skeleton" style="min-height:{int(height)}px"></div>',
            unsafe_allow_html=True,
        )


def dependency_version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "Non installé"


def footer() -> None:
    generated = datetime.now(TORONTO_TZ).strftime("%d-%m-%Y à %H:%M:%S ET")
    st.markdown(
        f"""
        <div class="sky-footer">
            Données de tiers pouvant être différées, incomplètes ou révisées. Les analyses sont informatives
            et ne constituent pas une recommandation personnalisée.<br>
            Dernière génération de la page : <strong>{generated}</strong>.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# V5.9.9 — Safe Render UI overrides
# ---------------------------------------------------------------------------
# Ces définitions remplacent les anciennes versions basées sur
# st.components.v1.html. Le but est d'éviter les iframes invisibles qui peuvent
# provoquer un écran blanc sur Render / mobile et de supprimer les avertissements
# Streamlit répétés dans les logs. Les fonctions gardent le même nom pour rester
# compatibles avec le reste du code.


def _install_theme_persistence_bridge(current_theme: str) -> None:  # type: ignore[override]
    theme = _normalized_theme(current_theme) or "dark"
    st.session_state["_anatole_theme"] = theme
    try:
        if _query_param_value(THEME_QUERY_PARAM) != theme:
            st.query_params[THEME_QUERY_PARAM] = theme
    except Exception:
        pass


def force_anatole_browser_brand(page_title: str = "Anatole") -> None:  # type: ignore[override]
    st.session_state["_anatole_page_title"] = str(page_title or "Anatole")


def enforce_same_tab_navigation() -> None:  # type: ignore[override]
    return


def hide_streamlit_chrome() -> None:  # type: ignore[override]
    st.markdown(
        """
        <style>
            #MainMenu, footer, header [data-testid="stToolbar"],
            [data-testid="stToolbar"], [data-testid="stDecoration"],
            [data-testid="stStatusWidget"], [data-testid="stDeployButton"],
            [data-testid="stMainMenu"], [aria-label="Main menu"],
            [aria-label="Open menu"], button[title="View fullscreen"],
            button[title="Exit fullscreen"] {
                display: none !important;
                visibility: hidden !important;
                opacity: 0 !important;
                pointer-events: none !important;
                width: 0 !important;
                height: 0 !important;
                max-width: 0 !important;
                max-height: 0 !important;
                overflow: hidden !important;
            }
            .stApp > header {
                display: none !important;
                height: 0 !important;
            }
            .stApp {
                margin-top: 0 !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def install_sidebar_rescue_navigation() -> None:  # type: ignore[override]
    if not bool(st.session_state.get("show_mobile_nav", True)):
        return
    nav_items = [
        ("🏠", "Cockpit", "cockpit"),
        ("⚡", "Aujourd’hui", "aujourdhui"),
        ("🔎", "Screener", "screener"),
        ("🎯", "Focus", "focus"),
        ("⭐", "Liste", "watchlist"),
        ("🧠", "Psychologie", "psychologie"),
        ("🧺", "ETF", "etf"),
        ("🚀", "IPO", "ipo"),
        ("🕵️", "Insiders", "insiders"),
        ("💎", "Terminal", "terminal"),
        ("⚙️", "Préférences", "preferences"),
    ]
    links = "".join(
        f'<a href="/{html.escape(_navigation_query_suffix(nav=nav), quote=True)}" target="_self" title="{html.escape(label)}">'
        f'<span class="sky-rescue-icon">{html.escape(icon)}</span><span>{html.escape(label)}</span></a>'
        for icon, label, nav in nav_items
    )
    st.markdown(
        f"""
        <style>
            .sky-desktop-rescue-nav {{
                display: none;
            }}
            @media (min-width: 900px) {{
                .sky-desktop-rescue-nav {{
                    position: fixed;
                    z-index: 999;
                    top: 108px;
                    left: 14px;
                    width: 178px;
                    max-height: calc(100vh - 140px);
                    overflow-y: auto;
                    padding: 12px 10px;
                    border: 1px solid rgba(125, 211, 252, .18);
                    border-radius: 22px;
                    background: rgba(8, 21, 34, .72);
                    backdrop-filter: blur(22px) saturate(1.15);
                    box-shadow: 0 22px 60px rgba(0, 0, 0, .22);
                }}
                .sky-desktop-rescue-nav a {{
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    padding: 10px 10px;
                    margin: 2px 0;
                    border-radius: 16px;
                    color: #dbeafe !important;
                    text-decoration: none !important;
                    font-weight: 800;
                    font-size: .88rem;
                }}
                .sky-desktop-rescue-nav a:hover {{
                    background: rgba(56, 189, 248, .14);
                    color: #ffffff !important;
                }}
                .sky-rescue-icon {{
                    display: inline-flex;
                    width: 26px;
                    height: 26px;
                    align-items: center;
                    justify-content: center;
                    border-radius: 10px;
                    background: rgba(148, 163, 184, .12);
                }}
                /* Quand la sidebar Streamlit est déjà visible, on masque le rail. */
                section[data-testid="stSidebar"] ~ div .sky-desktop-rescue-nav {{
                    display: none;
                }}
            }}
            @media (max-width: 899px) {{
                .sky-desktop-rescue-nav {{ display: none !important; }}
            }}
        </style>
        <nav class="sky-desktop-rescue-nav" aria-label="Navigation Anatole">{links}</nav>
        """,
        unsafe_allow_html=True,
    )
