# Anatole V4.7 — Smooth Public Beta

Anatole est un terminal financier Streamlit consacré principalement au S&P/TSX 60. Cette édition a fait l’objet d’un audit complet des pages, graphiques, flux de données, préférences, caches et accès PostgreSQL afin de rendre la bêta publique plus stable et plus fluide.

## Fonctions principales

- cockpit du marché et heatmap cliquable;
- screener, comparateur et graphique Focus;
- informations fondamentales, consensus des analystes et activité des initiés;
- moteurs sectoriels cliquables avec actions contributrices;
- portefeuille, watchlist, alertes et notifications;
- actualités, calendrier économique officiel et calendrier d’entreprise;
- backtesting, corrélations, rapports PDF/Excel et espaces de travail;
- authentification OIDC facultative, PostgreSQL et pages de confidentialité;
- assistant contextuel facultatif, avec fonctionnement local sans clé externe.

## Améliorations V4.7

- les 22 pages enregistrées sont exécutées dans un test automatique Streamlit;
- les appels lourds d’actualités et de calendriers sont parallélisés;
- les pages sectorielles et de notifications n’effectuent plus de téléchargement historique inutile;
- un dernier snapshot valide protège le cockpit lors d’une panne temporaire de la source;
- les caches sont bornés pour limiter la mémoire consommée sur Render;
- la base PostgreSQL est initialisée une seule fois par processus;
- les préférences sont lues et enregistrées en lot;
- les erreurs techniques des services externes ne sont plus exposées aux testeurs;
- un bouton permet d’actualiser uniquement les données live;
- l’interface bénéficie d’un défilement fluide et de contrôles Plotly plus discrets.

## Installation locale

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## Déploiement

Le projet contient un `Dockerfile`, un `render.yaml` et un healthcheck Streamlit. Consulte `DEPLOYMENT_PUBLIC_BETA.md` avant la mise en ligne.

Pour une expérience publique sans écran de réveil de l’hébergeur, utilise une instance web qui ne se met pas en veille. Les optimisations du code accélèrent Anatole une fois le service lancé, mais elles ne peuvent pas supprimer le démarrage à froid d’un hébergement gratuit.

## Secrets

Ne publie jamais `.streamlit/secrets.toml`. Utilise `.streamlit/secrets.toml.example` comme modèle et configure les vraies valeurs dans l’interface de l’hébergeur.

## Validation

```bash
python -m pytest -q
python -m ruff check core screens app.py alert_worker.py tests
```

Le rapport complet se trouve dans `AUDIT_ANATOLE_V4_7_0.md`.

## Limites

- les données de marché gratuites peuvent être différées, limitées ou temporairement indisponibles;
- la couverture fondamentale, des analystes et des initiés dépend des sources disponibles;
- les contributions sectorielles sont des estimations fondées sur les poids et variations disponibles;
- les analyses présentées ne constituent pas des conseils financiers personnalisés.
