from __future__ import annotations

from pathlib import Path
import html

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
    "source_name",
    "source_url",
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
    fallback["source_name"] = ""
    fallback["source_url"] = ""
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
    columns = ["Secteur", "Contribution", "Acteurs ou activités concernés", "Confiance", "Lecture", "Source", "Lien source"]
    if rows.empty:
        return pd.DataFrame(columns=columns)
    sectors = rows[rows["layer"] == "Secteurs impactés"].copy()
    if sectors.empty:
        sectors = rows.copy()
    keep = [col for col in ["sector", "relation", "entity", "confidence", "note", "source_name", "source_url"] if col in sectors.columns]
    output = sectors[keep].copy()
    output = output.rename(
        columns={
            "sector": "Secteur",
            "relation": "Contribution",
            "entity": "Acteurs ou activités concernés",
            "confidence": "Confiance",
            "note": "Lecture",
            "source_name": "Source",
            "source_url": "Lien source",
        }
    )
    for column in columns:
        if column not in output.columns:
            output[column] = ""
    return output[columns].reset_index(drop=True)

def affiliation_table(rows: pd.DataFrame) -> pd.DataFrame:
    columns = ["Niveau", "Relation", "Acteur", "Catégorie", "Secteur", "Confiance", "Source", "Lien source"]
    if rows.empty:
        return pd.DataFrame(columns=columns)
    keep = [col for col in ["layer", "relation", "entity", "category", "sector", "confidence", "source_name", "source_url"] if col in rows.columns]
    table = rows[keep].copy()
    table = table.rename(
        columns={
            "layer": "Niveau",
            "relation": "Relation",
            "entity": "Acteur",
            "category": "Catégorie",
            "sector": "Secteur",
            "confidence": "Confiance",
            "source_name": "Source",
            "source_url": "Lien source",
        }
    )
    for column in columns:
        if column not in table.columns:
            table[column] = ""
    return table[columns].reset_index(drop=True)

def _safe_text(value: object, max_len: int = 82) -> str:
    clean = str(value or "").strip()
    if len(clean) > max_len:
        return clean[: max_len - 1].rstrip() + "…"
    return clean


def _layer_items(rows: pd.DataFrame, layer: str, limit: int = 5) -> list[dict[str, str]]:
    if rows.empty or "layer" not in rows:
        return []
    subset = rows[rows["layer"] == layer].head(limit).copy()
    items: list[dict[str, str]] = []
    for _, row in subset.iterrows():
        items.append(
            {
                "relation": _safe_text(row.get("relation", "Relation"), 46),
                "entity": _safe_text(row.get("entity", "Non documenté"), 72),
                "sector": _safe_text(row.get("sector", ""), 34),
                "confidence": _safe_text(row.get("confidence", ""), 22),
                "source_name": _safe_text(row.get("source_name", ""), 34),
                "source_url": str(row.get("source_url", "") or "").strip(),
            }
        )
    return items


def _layer_total(rows: pd.DataFrame, layer: str) -> int:
    if rows.empty or "layer" not in rows:
        return 0
    return int((rows["layer"] == layer).sum())


def _confidence_total(rows: pd.DataFrame, confidence: str) -> int:
    if rows.empty or "confidence" not in rows:
        return 0
    return int((rows["confidence"].astype(str).str.strip() == confidence).sum())


def _source_total(rows: pd.DataFrame) -> int:
    if rows.empty or "source_url" not in rows:
        return 0
    return int(rows["source_url"].astype(str).str.strip().ne("").sum())


def _items_html(items: list[dict[str, str]], empty_label: str) -> str:
    if not items:
        return f'<div class="eco-mini-empty">{html.escape(empty_label)}</div>'
    chunks: list[str] = []
    for item in items:
        relation = html.escape(item.get("relation", ""))
        entity = html.escape(item.get("entity", ""))
        sector = html.escape(item.get("sector", ""))
        confidence = html.escape(item.get("confidence", ""))
        source_name = html.escape(item.get("source_name", "") or "Source publique")
        source_url = html.escape(item.get("source_url", ""), quote=True)
        meta = " · ".join(part for part in [sector, confidence] if part)
        source_html = (
            f'<a class="eco-source-chip" href="{source_url}" target="_blank" rel="noreferrer">{source_name}</a>'
            if source_url
            else '<span class="eco-source-chip eco-source-muted">À documenter</span>'
        )
        chunks.append(
            f"""
            <div class="eco-mini-card">
                <div class="eco-mini-relation">{relation}</div>
                <div class="eco-mini-entity">{entity}</div>
                <div class="eco-mini-meta">{html.escape(meta)}</div>
                {source_html}
            </div>
            """
        )
    return "".join(chunks)


def ecosystem_value_chain_html(rows: pd.DataFrame, ticker: str, company_name: str) -> str:
    intrants = _layer_items(rows, "Intrants")
    clients = _layer_items(rows, "Clients servis")
    sectors = _layer_items(rows, "Secteurs impactés")
    company = html.escape(_safe_text(company_name or ticker, 64))
    ticker_clean = html.escape(_safe_text(ticker, 18))
    intrants_total = _layer_total(rows, "Intrants")
    clients_total = _layer_total(rows, "Clients servis")
    sectors_total = _layer_total(rows, "Secteurs impactés")
    documented_total = _confidence_total(rows, "Documenté")
    sources_total = _source_total(rows)
    proof_label = "Documenté" if documented_total else "Indicatif"

    style = """
    <style>
      .eco-readable-wrap {
        border: 1px solid rgba(76,145,201,.22);
        border-radius: 22px;
        padding: 16px;
        background: rgba(255,255,255,.62);
        box-shadow: 0 10px 30px rgba(35, 92, 138, .08);
        margin: 8px 0 18px;
      }
      .eco-readable-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 12px;
      }
      .eco-readable-title {
        font-size: .78rem;
        letter-spacing: .08em;
        text-transform: uppercase;
        font-weight: 900;
        color: #5B7088;
      }
      .eco-readable-proof {
        border: 1px solid rgba(22,163,74,.22);
        border-radius: 999px;
        padding: 5px 10px;
        background: rgba(240,253,244,.88);
        color: #166534;
        font-size: .72rem;
        font-weight: 900;
        white-space: nowrap;
      }
      .eco-summary-grid {
        display: grid;
        grid-template-columns: repeat(5, minmax(0, 1fr));
        gap: 8px;
        margin-bottom: 12px;
      }
      .eco-summary-chip {
        border: 1px solid rgba(76,145,201,.18);
        border-radius: 14px;
        background: rgba(248,252,255,.88);
        padding: 9px 10px;
      }
      .eco-summary-value {
        color: #0F2742;
        font-size: 1rem;
        line-height: 1.1;
        font-weight: 950;
      }
      .eco-summary-label {
        color: #5B7088;
        font-size: .68rem;
        line-height: 1.2;
        font-weight: 800;
        margin-top: 3px;
      }
      .eco-chain-grid {
        display: grid;
        grid-template-columns: minmax(0, 1.18fr) 44px minmax(0, .92fr) 44px minmax(0, 1.18fr) 44px minmax(0, 1.18fr);
        gap: 10px;
        align-items: stretch;
      }
      .eco-column {
        border: 1px solid rgba(76,145,201,.22);
        border-radius: 18px;
        background: rgba(255,255,255,.72);
        padding: 12px;
        min-height: 220px;
      }
      .eco-column-title {
        font-size: .78rem;
        font-weight: 900;
        color: #0F2742;
        margin-bottom: 10px;
      }
      .eco-company-card {
        height: 100%;
        min-height: 220px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        border-radius: 18px;
        background: linear-gradient(135deg, rgba(37,99,235,.96), rgba(14,165,233,.92));
        color: white;
        padding: 18px;
        box-shadow: 0 16px 38px rgba(37,99,235,.22);
      }
      .eco-company-name {
        font-size: 1.05rem;
        line-height: 1.2;
        font-weight: 950;
        margin-bottom: 8px;
      }
      .eco-company-ticker {
        font-size: .80rem;
        font-weight: 850;
        opacity: .88;
      }
      .eco-company-proof {
        margin-top: 13px;
        border-radius: 999px;
        border: 1px solid rgba(255,255,255,.42);
        padding: 6px 10px;
        font-size: .70rem;
        font-weight: 900;
        background: rgba(255,255,255,.16);
      }
      .eco-arrow {
        display: grid;
        place-items: center;
        color: #2563EB;
        font-size: 1.55rem;
        font-weight: 950;
      }
      .eco-mini-card {
        border: 1px solid rgba(76,145,201,.18);
        border-radius: 14px;
        padding: 9px 10px;
        margin-bottom: 8px;
        background: rgba(243,251,255,.86);
      }
      .eco-mini-relation {
        font-size: .70rem;
        color: #2563EB;
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: .045em;
        margin-bottom: 3px;
      }
      .eco-mini-entity {
        color: #0F2742;
        font-size: .86rem;
        font-weight: 850;
        line-height: 1.25;
      }
      .eco-mini-meta {
        color: #5B7088;
        font-size: .72rem;
        margin-top: 4px;
        line-height: 1.25;
      }
      .eco-source-chip {
        display: inline-block;
        margin-top: 7px;
        border-radius: 999px;
        border: 1px solid rgba(22,163,74,.22);
        padding: 4px 8px;
        background: rgba(240,253,244,.88);
        color: #166534;
        font-size: .68rem;
        font-weight: 900;
        text-decoration: none;
      }
      .eco-source-muted {
        border-color: rgba(91,112,136,.22);
        background: rgba(241,245,249,.82);
        color: #5B7088;
      }
      .eco-mini-empty {
        color: #5B7088;
        font-size: .84rem;
        padding: 12px;
        border-radius: 14px;
        background: rgba(243,251,255,.75);
      }
      @media (max-width: 900px) {
        .eco-chain-grid {
          grid-template-columns: 1fr;
        }
        .eco-readable-head {
          align-items: flex-start;
          flex-direction: column;
        }
        .eco-summary-grid {
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }
        .eco-arrow {
          transform: rotate(90deg);
          min-height: 30px;
        }
        .eco-company-card, .eco-column {
          min-height: auto;
        }
      }
    </style>
    """

    return (
        style
        + f"""
        <div class="eco-readable-wrap">
          <div class="eco-readable-head">
            <div class="eco-readable-title">Chaîne de valeur lisible</div>
            <div class="eco-readable-proof">{html.escape(proof_label)}</div>
          </div>
          <div class="eco-summary-grid">
            <div class="eco-summary-chip">
              <div class="eco-summary-value">{intrants_total}</div>
              <div class="eco-summary-label">Intrants</div>
            </div>
            <div class="eco-summary-chip">
              <div class="eco-summary-value">{clients_total}</div>
              <div class="eco-summary-label">Clients / usages</div>
            </div>
            <div class="eco-summary-chip">
              <div class="eco-summary-value">{sectors_total}</div>
              <div class="eco-summary-label">Secteurs touchés</div>
            </div>
            <div class="eco-summary-chip">
              <div class="eco-summary-value">{documented_total}</div>
              <div class="eco-summary-label">Liens documentés</div>
            </div>
            <div class="eco-summary-chip">
              <div class="eco-summary-value">{sources_total}</div>
              <div class="eco-summary-label">Sources publiques</div>
            </div>
          </div>
          <div class="eco-chain-grid">
            <div class="eco-column">
              <div class="eco-column-title">1. Intrants / ressources</div>
              {_items_html(intrants, "Intrants non encore documentés")}
            </div>
            <div class="eco-arrow">→</div>
            <div class="eco-company-card">
              <div class="eco-company-name">{company}</div>
              <div class="eco-company-ticker">{ticker_clean}</div>
              <div class="eco-company-proof">{documented_total} lien(s) documenté(s)</div>
            </div>
            <div class="eco-arrow">→</div>
            <div class="eco-column">
              <div class="eco-column-title">2. Clients / usages servis</div>
              {_items_html(clients, "Clients ou usages non encore documentés")}
            </div>
            <div class="eco-arrow">→</div>
            <div class="eco-column">
              <div class="eco-column-title">3. Secteurs impactés</div>
              {_items_html(sectors, "Secteurs impactés non encore documentés")}
            </div>
          </div>
        </div>
        """
    )


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
        height=560,
        margin={"l": 8, "r": 8, "t": 18, "b": 8},
        font={"size": 15, "family": "Arial, sans-serif", "color": "#0F2742"},
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
