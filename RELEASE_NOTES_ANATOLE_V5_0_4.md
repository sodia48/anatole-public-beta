# Anatole V5.0.4 — Mobile hotfix

## Problèmes corrigés

1. Sur téléphone, certains liens internes pouvaient s'ouvrir dans une nouvelle fenêtre.
2. Des erreurs 502 apparaissaient encore de temps en temps lorsque des pages lourdes chargeaient trop de données.
3. Sur téléphone, la recherche dépendait trop du raccourci clavier Ctrl/Cmd + K.

## Correctifs

- Ajout d'un garde `same-tab navigation` pour forcer les liens internes à rester dans le même onglet.
- Ajout d'une vraie page Recherche accessible par `/recherche`.
- Ajout de Recherche dans la navigation mobile.
- Le bouton Recherche du topbar pointe vers la page Recherche.
- La recherche ne dépend plus du raccourci clavier sur mobile.
- Limites Render/Yahoo plus conservatrices :
  - news : 4 tickers max, 1 worker, timeout 12s ;
  - TSX Composite et TSX étendu réduits par défaut ;
  - Actualités limitées à 4 titres.
- Détection mobile silencieuse et anti-crash conservée.
- Aucun message public de performance.
- Aucune migration PostgreSQL.
- Aucune nouvelle dépendance.
