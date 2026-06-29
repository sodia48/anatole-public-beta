# Anatole V5.0.5 — Sélecteur d'univers accessible sur mobile

## Problème corrigé

Sur téléphone, les utilisateurs ne voyaient que le TSX 60 parce que le sélecteur
d'univers était principalement dans la barre latérale, masquée sur mobile.

## Correction

- Ajout d'un sélecteur d'univers dans l'interface principale.
- Choix disponibles :
  - TSX 60 ;
  - Composite ;
  - TSX étendu.
- Le choix reste synchronisé avec la session et le paramètre d'URL `universe`.
- Les caches live sont vidés automatiquement lors du changement d'univers.
- Garde anti-crash : le sélecteur ne peut pas empêcher la page de s'afficher.
- Aucune migration PostgreSQL.
- Aucune nouvelle dépendance.

## Fichiers clés

- `core/universe.py`
- `core/ui.py`
