# Anatole V4.8.6 — Indicateurs Plotly automatiques

## Changement demandé

Les indicateurs Plotly du Mode Focus ne demandent plus d'activation manuelle.

## Résultat

- Suppression du bouton `Utiliser le graphique Plotly`.
- Suppression du panneau fermé `Indicateurs Plotly avancés`.
- Le graphique principal du Mode Focus utilise automatiquement Plotly.
- Les indicateurs intégrés automatiquement sont :
  - chandeliers ;
  - volume ;
  - SMA 20 ;
  - SMA 50 ;
  - SMA 200 ;
  - EMA 20 ;
  - bandes de Bollinger lorsque les données sont disponibles.
- Les bandes de Bollinger sont maintenant sécurisées si les colonnes ne sont pas disponibles.
- Aucune migration PostgreSQL.
- Aucune nouvelle dépendance.
