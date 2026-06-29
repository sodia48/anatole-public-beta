from __future__ import annotations

import numpy as np
import pandas as pd


def daily_market_summary(market: pd.DataFrame) -> str:
    if market is None or market.empty or "Variation" not in market:
        return "Les données de marché ne sont pas encore disponibles."

    frame = market.copy()
    frame["Variation"] = pd.to_numeric(frame["Variation"], errors="coerce")
    valid = frame.dropna(subset=["Variation"])
    if valid.empty:
        return "La variation du marché ne peut pas encore être calculée."

    if "PoidsIndice" in valid:
        weights = pd.to_numeric(valid["PoidsIndice"], errors="coerce").fillna(1)
    else:
        weights = pd.Series(1.0, index=valid.index)
    weighted = np.average(valid["Variation"], weights=weights)
    advancers = int((valid["Variation"] > 0).sum())
    decliners = int((valid["Variation"] < 0).sum())

    sector = (
        valid.groupby("Secteur", as_index=False)["Variation"]
        .mean()
        .sort_values("Variation", ascending=False)
        if "Secteur" in valid
        else pd.DataFrame()
    )

    if not sector.empty:
        best = sector.iloc[0]
        worst = sector.iloc[-1]
        sector_sentence = (
            f"Le secteur {best['Secteur']} mène la séance ({best['Variation']:+.2f} %), "
            f"tandis que {worst['Secteur']} est le moins performant ({worst['Variation']:+.2f} %)."
        )
    else:
        sector_sentence = "La ventilation sectorielle n'est pas disponible."

    direction = "progresse" if weighted >= 0 else "recule"
    breadth = "positive" if advancers > decliners else "négative" if decliners > advancers else "équilibrée"
    return (
        f"Le TSX 60 {direction} d'environ {abs(weighted):.2f} %. "
        f"La largeur du marché est {breadth}, avec {advancers} titres en hausse et {decliners} en baisse. "
        f"{sector_sentence}"
    )
