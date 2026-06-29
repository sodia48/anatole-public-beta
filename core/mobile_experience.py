from __future__ import annotations

import streamlit as st

from core.device import mobile_is_lite


def plotly_config() -> dict:
    """Plotly config tuned for public mobile usage."""
    is_mobile = mobile_is_lite()
    return {
        "displaylogo": False,
        "responsive": True,
        "scrollZoom": bool(is_mobile),
        "doubleClick": "reset+autosize",
        "showTips": False,
        "modeBarButtonsToRemove": [
            "lasso2d",
            "select2d",
            "autoScale2d",
            "toggleSpikelines",
            "hoverClosestCartesian",
            "hoverCompareCartesian",
        ],
        "displayModeBar": False if is_mobile else "hover",
    }


def mobile_chart_height(default: int, mobile: int) -> int:
    return mobile if mobile_is_lite() else default


def install_mobile_viewport_probe() -> None:
    """Safe viewport CSS vars for mobile browser address bars.

    No URL rewrite. No visible UI. No session mutation.
    """
    st.components.v1.html(
        """
        <script>
        (function() {
          try {
            const win = window.parent || window;
            const doc = win.document;
            if (!doc || doc.__anatoleViewportProbeInstalled) return;
            doc.__anatoleViewportProbeInstalled = true;

            function update() {
              const vh = (win.visualViewport ? win.visualViewport.height : win.innerHeight) * 0.01;
              doc.documentElement.style.setProperty('--anatole-vh', vh + 'px');
              doc.documentElement.style.setProperty('--anatole-safe-bottom', 'env(safe-area-inset-bottom, 0px)');
              if ((win.innerWidth || 1400) <= 760) {
                doc.documentElement.setAttribute('data-anatole-device', 'mobile');
              } else {
                doc.documentElement.setAttribute('data-anatole-device', 'desktop');
              }
            }

            update();
            win.addEventListener('resize', update, {passive:true});
            if (win.visualViewport) {
              win.visualViewport.addEventListener('resize', update, {passive:true});
            }
            setTimeout(update, 250);
            setTimeout(update, 1000);
          } catch (error) {}
        })();
        </script>
        """,
        height=0,
        width=0,
    )
