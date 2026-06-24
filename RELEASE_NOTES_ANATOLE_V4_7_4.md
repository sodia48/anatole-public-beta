# Anatole V4.7.4 — Correctif définitif du chrome Streamlit

## Correction

- Retire le correctif CSS problématique des versions V4.7.2/V4.7.3.
- Ajoute le masquage du chrome Streamlit dans une fonction séparée,
  hors f-string, pour éviter les erreurs `NameError`.
- Masque :
  - l'indicateur de statut Streamlit ;
  - la barre d'outils Streamlit ;
  - le bouton Deploy ;
  - le menu natif en haut à droite.

## Note

Il peut encore y avoir un micro-affichage pendant le tout premier chargement
du navigateur, avant que Streamlit exécute le code de l'application. Après le
premier rendu, les éléments Streamlit sont masqués.
