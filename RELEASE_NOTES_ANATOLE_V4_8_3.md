# Anatole V4.8.3 — Correction Moteurs du marché

## Correction

La page `Moteurs du marché` utilise un snapshot léger pour préserver la
performance. La fonction `market_pulse()` attendait encore certaines colonnes
techniques présentes seulement dans le chargement complet.

## Résultat

- La page Moteurs du marché accepte les données légères.
- Les métriques techniques absentes sont affichées comme non disponibles au lieu
  de déclencher une erreur.
- Le clic sectoriel et les contributions par action restent actifs.
- Aucune migration PostgreSQL.
- Aucune nouvelle dépendance.
