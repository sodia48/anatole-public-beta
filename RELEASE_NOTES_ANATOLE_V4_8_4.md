# Anatole V4.8.4 — Stabilité Actualités

## Correction

La page Actualités pouvait provoquer une coupure WebSocket / 502 lorsque Yahoo
News répondait lentement ou lorsque trop de titres étaient interrogés en même
temps.

## Changements

- Maximum 6 titres à surveiller dans Actualités.
- Défaut réduit à 4 titres.
- Maximum 2 appels Yahoo News simultanés.
- Délai maximal global de 18 secondes.
- Maximum 8 articles par ticker.
- Maximum 60 articles au total.
- Déduplication des manchettes.
- Message propre si la source d'actualités est lente.
- Aucune migration PostgreSQL.
- Aucune nouvelle dépendance.

## Variables avancées possibles

- `ANATOLE_NEWS_MAX_TICKERS=6`
- `ANATOLE_NEWS_WORKERS=2`
- `ANATOLE_NEWS_TIMEOUT=18`
- `ANATOLE_NEWS_PER_TICKER=8`
- `ANATOLE_NEWS_MAX_ARTICLES=60`
