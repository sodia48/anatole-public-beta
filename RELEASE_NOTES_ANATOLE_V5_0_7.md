# Anatole V5.0.7 — Volume coloré et lecture actionnariale

## Ajouts

- Le sous-graphe des volumes dans la section Focus utilise maintenant un code couleur explicite :
  - vert = volume d'entrée / séance haussière ;
  - rouge = volume de sortie / séance baissière.
- Ajout sous le graphique de quatre indicateurs rapides :
  - volume de la séance ;
  - flux dominant ;
  - part institutionnelle ;
  - retail estimé.
- Ajout d'une note méthodologique : le retail exact n'est pas publié en temps réel ; Anatole l'estime comme la part restante hors institutions et initiés quand les données sont disponibles.

## Fichiers clés

- `core/charts.py`
- `screens/14_Focus.py`
