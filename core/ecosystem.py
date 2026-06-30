from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "company_ecosystem.csv"

REQUIRED_COLUMNS = [
    "ticker",
    "layer",
    "relation",
    "entity",
    "category",
    "sector",
    "confidence",
    "note",
]

SECTOR_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "Finance": [
        {"layer": "Intrants", "relation": "Technologie et conformité", "entity": "Paiements, données, cybersécurité et risque", "category": "Fournisseurs", "sector": "Technologie", "confidence": "Indicatif", "note": "Infrastructure nécessaire aux services financiers."},
        {"layer": "Clients servis", "relation": "Crédit et capital", "entity": "Ménages, PME, grandes entreprises et investisseurs", "category": "Clients", "sector": "Finance", "confidence": "Indicatif", "note": "Le titre est relié au financement et à l’allocation du capital."},
        {"layer": "Secteurs impactés", "relation": "Financement", "entity": "Immobilier, consommation, industrie et marchés financiers", "category": "Secteur", "sector": "Économie réelle", "confidence": "Indicatif", "note": "Contribution par crédit, paiements et services d’investissement."},
    ],
    "Énergie": [
        {"layer": "Intrants", "relation": "Équipement et services", "entity": "Services industriels, ingénierie, transport et maintenance", "category": "Fournisseurs", "sector": "Industrie", "confidence": "Indicatif", "note": "Intrants nécessaires aux actifs énergétiques."},
        {"layer": "Clients servis", "relation": "Approvisionnement", "entity": "Raffineries, utilities, industrie et distributeurs", "category": "Clients", "sector": "Énergie", "confidence": "Indicatif", "note": "Clients ou utilisateurs de la production et des infrastructures énergétiques."},
        {"layer": "Secteurs impactés", "relation": "Usage final", "entity": "Transport, industrie, chauffage et chimie", "category": "Secteur", "sector": "Économie réelle", "confidence": "Indicatif", "note": "L’énergie soutient plusieurs usages économiques finaux."},
    ],
    "Technologie": [
        {"layer": "Intrants", "relation": "Infrastructure numérique", "entity": "Cloud, cybersécurité, logiciels et données", "category": "Fournisseurs", "sector": "Technologie", "confidence": "Indicatif", "note": "Intrants typiques des plateformes numériques."},
        {"layer": "Clients servis", "relation": "Solutions numériques", "entity": "Entreprises, développeurs, consommateurs et partenaires", "category": "Clients", "sector": "Services numériques", "confidence": "Indicatif", "note": "Utilisateurs directs ou indirects de la plateforme."},
        {"layer": "Secteurs impactés", "relation": "Numérisation", "entity": "Commerce, finance, marketing, productivité et données", "category": "Secteur", "sector": "Technologie", "confidence": "Indicatif", "note": "Contribution à la numérisation d’autres secteurs."},
    ],
    "Industrie": [
        {"layer": "Intrants", "relation": "Chaîne industrielle", "entity": "Équipement, pièces, énergie, transport et main-d’œuvre", "category": "Fournisseurs", "sector": "Industrie", "confidence": "Indicatif", "note": "Intrants nécessaires aux activités industrielles."},
        {"layer": "Clients servis", "relation": "Production et services", "entity": "Entreprises, infrastructures, distribution et gouvernements", "category": "Clients", "sector": "Industrie", "confidence": "Indicatif", "note": "Clients qui utilisent biens ou services industriels."},
        {"layer": "Secteurs impactés", "relation": "Capacité économique", "entity": "Construction, transport, énergie, commerce et exportations", "category": "Secteur", "sector": "Économie réelle", "confidence": "Indicatif", "note": "Contribution aux chaînes physiques de l’économie."},
    ],
    "Consommation": [
        {"layer": "Intrants", "relation": "Approvisionnement", "entity": "Marques, distribution, logistique, publicité et paiement", "category": "Fournisseurs", "sector": "Commerce", "confidence": "Indicatif", "note": "Intrants typiques d’un modèle orienté consommateur."},
        {"layer": "Clients servis", "relation": "Marché final", "entity": "Ménages, détaillants et canaux numériques", "category": "Clients", "sector": "Consommation", "confidence": "Indicatif", "note": "Exposition à la demande des consommateurs."},
        {"layer": "Secteurs impactés", "relation": "Demande finale", "entity": "Retail, publicité, logistique, finance et immobilier commercial", "category": "Secteur", "sector": "Consommation", "confidence": "Indicatif", "note": "Contribution indirecte aux secteurs liés à la demande finale."},
    ],
}

SECTOR_ALIASES = {
    "Financial Services": "Finance",
    "Financial": "Finance",
    "Banks": "Finance",
    "Energy": "Énergie",
    "Technology": "Technologie",
    "Industrials": "Industrie",
    "Industrial": "Industrie",
    "Consumer Cyclical": "Consommation",
    "Consumer Defensive": "Consommation",
    "Communication Services": "Technologie",
    "Utilities": "Industrie",
    "Basic Materials": "Industrie",
    "Real Estate": "Finance",
}


def _clean_ticker(ticker: str) -> str:
    return str(ticker or "").strip().upper()


def load_ecosystem_catalog() -> pd.DataFrame:
    if not DATA_PATH.exists():
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    data = pd.read_csv(DATA_PATH).fillna("")
    for column in REQUIRED_COLUMNS:
        if column not in data.columns:
            data[column] = ""
    data["ticker"] = data["ticker"].map(_clean_ticker)
    return data[REQUIRED_COLUMNS]


def _template_key(sector: str, industry: str | None = None) -> str:
    values = [str(sector or ""), str(industry or "")]
    joined = " ".join(values).lower()
    for key, label in SECTOR_ALIASES.items():
        if key.lower() in joined:
            return label
    if "finance" in joined or "bank" in joined or "insurance" in joined:
        return "Finance"
    if "energy" in joined or "oil" in joined or "gas" in joined or "pipeline" in joined:
        return "Énergie"
    if "technology" in joined or "software" in joined or "internet" in joined:
        return "Technologie"
    if "consumer" in joined or "retail" in joined:
        return "Consommation"
    return "Industrie"


def ecosystem_for_ticker(
    ticker: str,
    company_name: str,
    sector: str,
    industry: str | None = None,
) -> tuple[pd.DataFrame, str]:
    clean = _clean_ticker(ticker)
    catalog = load_ecosystem_catalog()
    direct = catalog[catalog["ticker"] == clean].copy()
    if not direct.empty:
        return direct.reset_index(drop=True), "Documenté localement"

    key = _template_key(sector, industry)
    template = SECTOR_TEMPLATES.get(key, SECTOR_TEMPLATES["Industrie"])
    fallback = pd.DataFrame(template)
    fallback.insert(0, "ticker", clean)
    fallback["confidence"] = "Indicatif"
    return fallback[REQUIRED_COLUMNS].reset_index(drop=True), f"Modèle indicatif par secteur : {key}"


def ecosystem_metrics(rows: pd.DataFrame) -> dict[str, int]:
    if rows.empty:
        return {"intrants": 0, "clients": 0, "secteurs": 0, "total": 0}
    return {
        "intrants": int((rows["layer"] == "Intrants").sum()),
        "clients": int((rows["layer"] == "Clients servis").sum()),
        "secteurs": int((rows["layer"] == "Secteurs impactés").sum()),
        "total": int(len(rows)),
    }


def contribution_table(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=["Secteur", "Contribution", "Lecture", "Confiance"])
    sectors = rows[rows["layer"] == "Secteurs impactés"].copy()
    if sectors.empty:
        sectors = rows.copy()
    output = sectors[["sector", "relation", "entity", "confidence", "note"]].copy()
    output = output.rename(
        columns={
            "sector": "Secteur",
            "relation": "Contribution",
            "entity": "Acteurs ou activités concernés",
            "confidence": "Confiance",
            "note": "Lecture",
        }
    )
    return output.reset_index(drop=True)


def affiliation_table(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=["Niveau", "Relation", "Acteur", "Catégorie", "Secteur", "Confiance"])
    table = rows[["layer", "relation", "entity", "category", "sector", "confidence"]].copy()
    return table.rename(
        columns={
            "layer": "Niveau",
            "relation": "Relation",
            "entity": "Acteur",
            "category": "Catégorie",
            "sector": "Secteur",
            "confidence": "Confiance",
        }
    ).reset_index(drop=True)


def ecosystem_sankey(rows: pd.DataFrame, ticker: str, company_name: str) -> go.Figure:
    company_label = f"{company_name} ({ticker})"
    if rows.empty:
        rows = pd.DataFrame(
            [
                {"layer": "Intrants", "entity": "Intrants non documentés"},
                {"layer": "Clients servis", "entity": "Clients non documentés"},
                {"layer": "Secteurs impactés", "entity": "Secteurs non documentés"},
            ]
        )

    sources: list[str] = []
    targets: list[str] = []
    values: list[int] = []

    for _, row in rows.iterrows():
        layer = str(row.get("layer", ""))
        entity = str(row.get("entity", "Non documenté"))
        sector = str(row.get("sector", "Secteur"))
        if layer == "Intrants":
            sources.append(entity)
            targets.append(company_label)
            values.append(1)
        elif layer == "Clients servis":
            sources.append(company_label)
            targets.append(entity)
            values.append(1)
        elif layer == "Secteurs impactés":
            sources.append(company_label)
            targets.append(entity)
            values.append(1)
            if sector and sector != entity:
                sources.append(entity)
                targets.append(sector)
                values.append(1)

    labels = list(dict.fromkeys(sources + targets))
    index = {label: idx for idx, label in enumerate(labels)}
    source_idx = [index[item] for item in sources]
    target_idx = [index[item] for item in targets]

    fig = go.Figure(
        data=[
            go.Sankey(
                arrangement="snap",
                node={
                    "label": labels,
                    "pad": 18,
                    "thickness": 16,
                    "line": {"color": "rgba(15,39,66,.20)", "width": 0.7},
                },
                link={
                    "source": source_idx,
                    "target": target_idx,
                    "value": values,
                    "hovertemplate": "%{source.label} → %{target.label}<extra></extra>",
                },
            )
        ]
    )
    fig.update_layout(
        height=430,
        margin={"l": 8, "r": 8, "t": 18, "b": 8},
        font={"size": 12},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def ecosystem_explainer(rows: pd.DataFrame, company_name: str, coverage: str) -> list[str]:
    metrics = ecosystem_metrics(rows)
    return [
        f"{company_name} est placé au centre d’une chaîne de valeur composée de {metrics['intrants']} intrant(s), {metrics['clients']} client(s) ou usages, et {metrics['secteurs']} secteur(s) impacté(s).",
        f"Couverture : {coverage}. Les liens affichés sont une cartographie économique informative, pas une preuve contractuelle exhaustive.",
        "Lecture : plus un titre dessert plusieurs secteurs, plus son activité peut être liée à des chaînes économiques larges — mais cela peut aussi accroître sa dépendance au cycle économique.",
    ]
