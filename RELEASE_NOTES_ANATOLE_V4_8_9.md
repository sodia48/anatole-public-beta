# Anatole V4.8.9 — Suppression maximale du branding Streamlit

## Objectif

Réduire au maximum toute mention visible de `Streamlit` dans l'expérience
utilisateur : onglet, aperçu mobile, favicon, manifest, toolbar et éléments
injectés par le runtime.

## Changements

- Titre navigateur forcé à Anatole.
- Favicon forcé à une icône Anatole SVG.
- Manifest mobile/PWA forcé à Anatole.
- Méta `application-name` et `apple-mobile-web-app-title` forcées à Anatole.
- MutationObserver qui remplace les textes `Streamlit` injectés après rerun.
- Masquage CSS renforcé des éléments natifs visibles.
- Configuration `.streamlit/config.toml` renforcée :
  - toolbarMode viewer ;
  - détails d'erreurs masqués ;
  - usage stats désactivées.

## Limite technique

Avec une application Streamlit native, une mention peut apparaître une fraction
de seconde au tout premier chargement, avant que le JavaScript d'Anatole soit
exécuté. Pour une garantie absolue zéro mention dès le HTML initial, il faut un
reverse proxy HTML ou un frontend personnalisé.

Aucune migration PostgreSQL et aucune nouvelle dépendance.
