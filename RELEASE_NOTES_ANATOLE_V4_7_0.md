# Anatole V4.7.0 — Smooth Audit

## Stabilité

- audit syntaxique et fonctionnel des 22 pages;
- test Streamlit automatisé de chaque page enregistrée, y compris Diagnostics;
- validation de tous les graphiques Plotly;
- correction de la conversion des paramètres SQLite/PostgreSQL;
- initialisation du schéma et des profils rendue idempotente et mise en cache;
- index de base ajoutés sur les tables fréquemment consultées;
- préférences utilisateur lues et enregistrées en lot;
- compteur de notifications remplacé par une requête SQL dédiée.

## Performance

- snapshot live protégé par le dernier jeu de données valide;
- caches bornés afin d’éviter une croissance mémoire continue;
- chargement parallèle des calendriers économiques;
- chargement parallèle des nouvelles et calendriers d’entreprise;
- délais réseau raccourcis et erreurs externes isolées;
- fallback fondamental TradingView déclenché seulement lorsque nécessaire;
- Moteurs du marché et Notifications utilisent désormais le bundle léger;
- bouton d’actualisation sélective des données live.

## Interface

- défilement fluide;
- barre d’outils Plotly discrète et visible au survol;
- tableaux mieux intégrés visuellement;
- messages d’erreur publics simplifiés;
- indicateur lorsque le dernier snapshot valide est utilisé;
- page État de la bêta mise à jour vers V4.7 Smooth Audit.

## Qualité

- lint Ruff sans erreur;
- 15 tests automatisés réussis;
- tests de parallélisme, préférences, graphiques et toutes les pages ajoutés;
- aucune migration obligatoire pour les utilisateurs existants.
