# Anatole V5.2.3 — Hard rollback stable

## Objectif

Revenir à la dernière base stable après les erreurs redacted provoquées par les essais V5.2.x.

## Ce rollback fait

- Repart de la base stable V5.1.0 Mobile Magic.
- Retire la page expérimentale `screens/23_Aujourd_hui.py`.
- Retire les ajouts V5.2.x risqués.
- Garde l'expérience mobile V5.1.0 validée.
- Aucune migration PostgreSQL.
- Aucune nouvelle dépendance.

## Instruction importante

Remplacer le projet complet, ou au minimum remplacer tous les fichiers clés listés.
Ne pas faire un remplacement partiel si des fichiers V5.2.x sont encore présents.
