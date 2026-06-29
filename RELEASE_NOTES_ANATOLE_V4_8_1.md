# Anatole V4.8.1 — Stabilité Render pour multi-univers

## Correctifs

- Réduit les limites de chargement pour `S&P/TSX Composite` et `TSX complet`.
- Le TSX complet passe en mode aperçu rapide sur Render Free.
- Si un univers étendu échoue, Anatole revient automatiquement au TSX 60 au
  lieu de laisser Render afficher une erreur 502.
- Les timeouts réseau sont raccourcis.
- Aucun changement de base de données.

## Limites recommandées

- TSX 60 : complet.
- Composite : aperçu large.
- TSX complet : aperçu rapide.
- Pour charger tout le TSX sans compromis, il faudra une instance Render payante
  et une source de données plus stable.
