# Anatole V5.1.0 — Mobile Magic

## Objectif

Rendre Anatole beaucoup plus naturel sur téléphone, avec une expérience plus proche
d'une application mobile de marché : navigation rapide, graphique plus agréable,
moins de friction, et moins de chargements inutiles.

## Améliorations mobile

- Navigation inférieure plus premium, plus grande et plus lisible.
- Onglet actif mis en évidence automatiquement.
- Liens internes forcés dans le même onglet.
- Barre supérieure plus compacte et sticky sur mobile.
- Sélecteur d'univers compact et accessible sur téléphone.
- Cartes, métriques, boutons, tableaux et contrôles mieux dimensionnés.
- Meilleure gestion du viewport mobile et des barres navigateur.
- Suppression des messages visibles inutiles liés au mode mobile.
- Suppression du bloc visible `Version mobile V5`.

## Graphiques Focus

- Graphique principal plus adapté au mobile.
- Drag/pan activé côté Plotly.
- Spikes/crosshair améliorés.
- Configuration Plotly allégée sur mobile.
- Hauteur automatiquement adaptée au téléphone.
- Volume toujours coloré vert/rouge.
- Résumé institutions / retail estimé conservé.

## Performance

- La lecture rapide institutions/retail utilise maintenant les données déjà chargées
  dans `fetch_company_info`, au lieu de déclencher immédiatement le chargement complet
  des transactions d'initiés.
- Les données avancées restent chargées uniquement dans la section dédiée.

## Fichiers clés

- `core/ui.py`
- `core/charts.py`
- `core/mobile_experience.py`
- `screens/14_Focus.py`
- `screens/0_Accueil.py`

## Notes

- Aucune migration PostgreSQL.
- Aucune nouvelle dépendance.
- Compatible Render Starter.
