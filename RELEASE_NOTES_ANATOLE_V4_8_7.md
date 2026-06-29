# Anatole V4.8.7 — Événements visibles sur Plotly

## Correction

Depuis l'activation automatique du graphique Plotly dans Mode Focus, les
événements étaient récupérés mais n'étaient plus dessinés sur le graphique.

## Résultat

- Les événements sont maintenant transmis au graphique Plotly principal.
- Chaque événement visible ajoute :
  - une ligne verticale pointillée ;
  - un marqueur en losange ;
  - un tooltip avec titre, date et source lorsque disponible.
- La cible analystes est aussi affichée comme ligne horizontale.
- Si aucun événement daté n'est trouvé, Anatole affiche un message propre.
- Aucune migration PostgreSQL.
- Aucune nouvelle dépendance.
