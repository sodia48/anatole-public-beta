from __future__ import annotations

import html
import importlib.metadata
from datetime import datetime
from typing import Iterable

import streamlit as st

from core.config import DEFAULT_PROFILE, TORONTO_TZ
from core.database import ensure_profile, init_db
from core.preferences import hydrate_preferences
from core.utils import market_status


def configure_page(title: str, icon: str = "📈") -> None:
    if st.session_state.get("_page_configured"):
        return
    st.set_page_config(
        page_title=f"{title} · Anatole",
        page_icon=icon,
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "Get help": None,
            "Report a bug": None,
            "About": "TSX 60 Skyline — terminal canadien d'analyse de marché.",
        },
    )
    st.session_state["_page_configured"] = True


def is_dark_mode() -> bool:
    return bool(st.session_state.get("theme_toggle", False))


def apply_style() -> None:
    dark = is_dark_mode()
    compact = bool(st.session_state.get("compact_toggle", False))

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

        html, body, [data-testid="stAppViewContainer"] {{
            background: {background} !important;
            color: var(--sky-text);
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
            color: white !important;
            font-weight: 820 !important;
            box-shadow: 0 9px 22px rgba(37,99,235,.22);
            transition: all .18s ease;
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

        @media (max-width: 650px) {{
            .block-container {{ padding-bottom: 6.5rem; }}
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
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


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
    from core.search import render_universal_search
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
    hydrate_preferences(profile)

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

    render_universal_search("sidebar", profile=profile)

    # Les valeurs existent déjà dans session_state grâce à hydrate_preferences.
    # Ne pas fournir value= évite tout conflit entre la valeur du widget
    # et la valeur persistée.
    st.sidebar.toggle(
        "Mode sombre",
        key="theme_toggle",
        help="Bascule entre le thème bleu ciel et le terminal sombre.",
    )
    st.sidebar.toggle(
        "Affichage compact",
        key="compact_toggle",
        help="Réduit légèrement l'espacement et la hauteur des cartes.",
    )

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
                <div class="sky-command-hint">Recherche <span class="sky-kbd">Ctrl K</span></div>
            </div>
            <div class="sky-terminal-right">
                <div class="sky-live-pill"><span class="sky-live-dot"></span>{html.escape(live_label)}</div>
                <div class="sky-time">{now:%H:%M:%S ET}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str, icon: str = "📈") -> None:
    terminal_topbar()
    safe_title = html.escape(title)
    safe_subtitle = html.escape(subtitle)
    safe_icon = html.escape(icon)
    st.markdown(
        f"""
        <section class="sky-hero">
            <div class="sky-hero-copy">
                <div class="sky-hero-kicker">● Bêta publique sur Render</div>
                <div class="sky-hero-title">{safe_title}</div>
                <div class="sky-hero-subtitle">{safe_subtitle}</div>
                <div class="sky-hero-chips">
                    <span class="sky-chip">TSX 60</span>
                    <span class="sky-chip">Données live</span>
                    <span class="sky-chip">Analyse technique</span>
                    <span class="sky-chip">Actualités</span>
                    <span class="sky-chip">IA optionnelle</span>
                </div>
            </div>
            <div class="sky-hero-icon">{safe_icon}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


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


def mobile_navigation() -> None:
    st.markdown(
        """
        <nav class="sky-mobile-nav">
          <a href="/cockpit">🏠<br>Accueil</a>
          <a href="/screener">🔎<br>Marchés</a>
          <a href="/focus">🎯<br>Focus</a>
          <a href="/portefeuille">💼<br>Portfolio</a>
          <a href="/notifications">🔔<br>Alertes</a>
        </nav>
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
