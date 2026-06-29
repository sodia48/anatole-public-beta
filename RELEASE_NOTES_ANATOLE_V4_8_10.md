# Anatole V4.8.10 — Correction page blanche au lancement

## Problème corrigé

La V4.8.9 utilisait un masquage trop agressif du branding natif. Sur certains
navigateurs, ce script pouvait bloquer le rendu et laisser Anatole sur un écran
bleu vide.

## Correction

- Retrait de l'observation globale du DOM.
- Retrait de la réécriture massive de la page.
- Conservation du branding Anatole sûr :
  - titre navigateur ;
  - favicon ;
  - manifest mobile ;
  - masquage toolbar/menu natifs.
- Le rendu de la page est prioritaire sur le masquage total du branding.

## Note

Une fraction de seconde de branding natif peut encore apparaître au tout premier
chargement. Pour une suppression absolue dès le HTML initial, il faudra un
reverse proxy ou un frontend personnalisé.

Aucune migration PostgreSQL et aucune nouvelle dépendance.
