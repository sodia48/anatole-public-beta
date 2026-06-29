# Anatole V5.0 — Public Beta Stable

## Objectif

Cette version se concentre sur les priorités produit retenues :

1. Corriger l'expérience mobile.
2. Améliorer la performance.
3. Rendre l'accueil plus professionnel.
4. Renforcer la qualité des données.

## Expérience mobile

- Ajout d'un module `core/device.py`.
- Ajout d'un mode mobile allégé activable dans la barre latérale.
- Support du query param `?mobile=1` pour testeurs mobiles.
- Navigation mobile affichée dans les pages.
- CSS responsive renforcé :
  - cartes plus compactes ;
  - métriques plus lisibles ;
  - boutons plus grands ;
  - tableaux mieux contenus ;
  - graphiques adaptés aux petits écrans.
- Accueil mobile simplifié avec message V5.

## Performance

- Ajout d'un module `core/performance.py`.
- Chronométrage discret des chargements :
  - cockpit ;
  - screener ;
  - actualités ;
  - historique Focus.
- Messages discrets lorsque le chargement dépasse un seuil.
- Résultats du Screener limités à l'affichage sur mobile, avec CSV complet disponible.
- Actualités plus légères sur mobile.
- Les calculs techniques avancés restent sur demande.

## Accueil professionnel

- Message d'accueil remplacé par une présentation plus crédible :
  `Terminal canadien de marché — lecture claire du TSX, des secteurs, des nouvelles et des titres à surveiller.`
- Ajout d'un cockpit professionnel :
  - lecture du marché ;
  - secteur dominant ;
  - titre moteur ;
  - risque à surveiller.
- Les données clés sont visibles en haut de page avant les graphiques lourds.

## Qualité des données

- Ajout d'un module `core/data_quality.py`.
- Bandeau de qualité des données :
  - qualité ;
  - univers actif ;
  - nombre de titres affichés ;
  - dernière mise à jour ;
  - source des cotations.
- Diagnostics enrichis avec statut des sources.
- Meilleure explication des données manquantes ou partielles.

## Fichiers clés

- `core/ui.py`
- `core/device.py`
- `core/performance.py`
- `core/data_quality.py`
- `screens/0_Accueil.py`
- `screens/1_Screener.py`
- `screens/5_Actualites.py`
- `screens/10_Diagnostics.py`
- `screens/14_Focus.py`

## Notes

- Aucune migration PostgreSQL.
- Aucune nouvelle dépendance.
- Les changements sont compatibles avec Render Starter.
