# Audit complet — Anatole V4.7.0

## Portée

L’audit couvre les 22 pages déclarées dans `app.py`, les modules `core`, les graphiques, la navigation, SQLite/PostgreSQL, les préférences, les sources économiques et les principaux parcours de la bêta publique.

## Vérifications réalisées

- analyse syntaxique de tous les fichiers Python;
- contrôle Ruff de `core`, `screens`, `app.py`, `alert_worker.py` et `tests`;
- exécution de la suite Pytest;
- rendu automatisé de chaque page avec `streamlit.testing.v1.AppTest`;
- sérialisation des graphiques Plotly;
- test des insertions multiples PostgreSQL;
- test de la base SQLite, des préférences, du feedback et de la suppression de profil;
- test du fallback BLS;
- test des données fondamentales, du consensus, des initiés et du clic sectoriel;
- contrôle des mots-clés Streamlit par rapport à la version épinglée.

## Résultats

- pages enregistrées testées : 22;
- tests automatisés : 15 réussis;
- erreurs Ruff : 0;
- erreurs de rendu détectées dans les tests : 0;
- fichiers Python invalides : 0.

## Correctifs structurants

### Données et réseau

Les actualités, calendriers économiques et calendriers d’entreprise sont désormais chargés en parallèle. Les requêtes utilisent des délais plus courts afin qu’une source lente ne bloque pas toute une page. Le cockpit conserve le dernier snapshot valide pour éviter un écran vide pendant une panne temporaire de Yahoo Finance.

### Base de données

La conversion des placeholders dépend maintenant du backend de la connexion utilisée. Le schéma n’est plus recréé à chaque appel de la sidebar. Les profils déjà initialisés sont mémorisés dans le processus. Des index améliorent les notifications, alertes, événements d’alertes et retours de bêta.

### Expérience utilisateur

Les pages qui n’ont pas besoin d’un historique annuel utilisent le bundle léger. Les sections techniques lourdes restent chargées à la demande. La barre Plotly est moins intrusive, le scroll est fluide et un bouton renouvelle seulement les cotations live.

## Limites qui ne peuvent pas être éliminées uniquement par le code

- le démarrage à froid d’une instance Render gratuite;
- les restrictions, délais ou changements de format des sources gratuites;
- l’absence éventuelle de couverture analyste ou initié pour certains titres;
- l’absence d’un flux boursier officiel temps réel sans contrat de données.

Pour une expérience comparable à un produit financier commercial, le déploiement doit utiliser une instance toujours active et, à terme, une source de données autorisée avec garanties de service.
