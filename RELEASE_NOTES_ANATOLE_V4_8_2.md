# Anatole V4.8.2 — Profil Render Starter

## Ajustements

- Ajout du profil `ANATOLE_HOSTING_PROFILE=starter`.
- Les limites des univers sont configurables par variable d'environnement.
- Le TSX complet reste progressif, mais avec des limites plus généreuses que le mode conservateur.
- Si un univers étendu échoue, Anatole revient au TSX 60 au lieu de laisser Render afficher une erreur 502.
- Les messages ne parlent plus de Render Free.

## Limites par défaut en profil Starter

- TSX 60 : 70 titres snapshot, 60 titres historique.
- S&P/TSX Composite : 160 titres snapshot, 80 titres historique.
- TSX complet / étendu : 150 titres snapshot, 60 titres historique.

## Variables avancées possibles

- `ANATOLE_HOSTING_PROFILE=conservative|starter|performance`
- `ANATOLE_TSX_FULL_SNAPSHOT_LIMIT=150`
- `ANATOLE_TSX_FULL_HISTORY_LIMIT=60`
- `ANATOLE_TSX_COMPOSITE_SNAPSHOT_LIMIT=160`
- `ANATOLE_TSX_COMPOSITE_HISTORY_LIMIT=80`

Aucune migration PostgreSQL et aucune nouvelle dépendance.
