# Anatole V4.7.1 — Persistance du consentement et du mode sombre

## Correctifs

- Le consentement aux conditions est maintenant enregistré pour tous les profils,
  y compris les sessions invitées.
- Le profil invité est stabilisé dans l'URL avec un identifiant `anatole_guest`.
- Le choix « Continuer comme invité » est également mémorisé avec
  `anatole_guest_mode=1`.
- Le mode sombre est enregistré immédiatement lorsqu'il est activé dans la
  barre latérale.
- L'affichage compact est enregistré immédiatement lorsqu'il est activé dans la
  barre latérale.

## Effet utilisateur

Un testeur ne devrait plus devoir accepter les conditions à chaque changement
de section. Le mode sombre ne devrait plus disparaître lorsqu'il change de page.

Aucune migration PostgreSQL et aucune nouvelle dépendance ne sont nécessaires.
