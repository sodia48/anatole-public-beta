# Anatole V4.8.8 — Branding navigateur Anatole

## Correction

Certains navigateurs affichaient encore `Streamlit` en grand dans l'aperçu,
l'onglet, le chargement ou l'expérience mobile/PWA.

## Résultat

- Le titre navigateur est forcé à `Anatole`.
- Le titre de page ne devient plus `Anatole · Anatole`.
- Le favicon est remplacé par une icône Anatole en SVG.
- Le manifest mobile/PWA est remplacé côté navigateur par un manifest Anatole.
- Le patch est relancé après les reruns pour éviter que Streamlit reprenne le titre.
- Le toolbar mode reste en mode `viewer`.
- Aucune migration PostgreSQL.
- Aucune nouvelle dépendance.

## Limite

Le navigateur peut encore afficher `Streamlit` pendant une fraction de seconde
avant que le JavaScript d'Anatole soit exécuté au tout premier chargement.
Après le premier rendu, le titre et l'icône doivent afficher Anatole.
