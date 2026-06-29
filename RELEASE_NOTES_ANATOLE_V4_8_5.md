# Anatole V4.8.5 — Correction consentement mobile

## Problème corrigé

Sur mobile, certains utilisateurs devaient accepter les conditions à chaque
changement de section. La cause probable était la perte des query params ou la
recréation de session Streamlit pendant la navigation mobile.

## Changements

- Ajout d'un pont navigateur via `localStorage`.
- L'acceptation est copiée dans l'URL avec `anatole_accepted`.
- Le profil invité est restauré depuis `localStorage` si l'URL le perd.
- Les liens internes Streamlit sont patchés pour conserver :
  - `anatole_guest`;
  - `anatole_guest_mode`;
  - `anatole_accepted`;
  - `universe`.
- Le consentement restauré côté navigateur est resynchronisé en base.
- Aucune migration PostgreSQL.
- Aucune nouvelle dépendance.
