# Déploiement de la bêta publique Anatole

## Architecture recommandée

- Streamlit Community Cloud ou Render pour l’application
- PostgreSQL géré pour les données persistantes
- Google OIDC pour les comptes testeurs
- Worker séparé facultatif pour les alertes hors session

## Option A — Streamlit Community Cloud

1. Publie le dossier dans un dépôt GitHub privé.
2. Crée une application depuis `app.py`.
3. Choisis Python 3.12.
4. Dans les secrets, ajoute :

```toml
ANATOLE_PUBLIC_BETA = "true"
ANATOLE_ACCESS_MODE = "login"
ANATOLE_ADMIN_EMAILS = "ton-adresse@example.com"
DATABASE_URL = "postgresql://..."

[auth]
redirect_uri = "https://TON-APP.streamlit.app/oauth2callback"
cookie_secret = "UNE_LONGUE_CHAINE_ALEATOIRE"
client_id = "CLIENT_ID_GOOGLE"
client_secret = "CLIENT_SECRET_GOOGLE"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

5. Dans Google Cloud, ajoute exactement la même URI de redirection.
6. Commence avec 5 à 20 testeurs.

## Option B — Render

Le fichier `render.yaml` crée le service web et une base PostgreSQL.
Après la création :

1. Ajoute les secrets OIDC et les clés facultatives.
2. Configure `ANATOLE_ADMIN_EMAILS`.
3. Vérifie `/_stcore/health`.
4. Le worker d’alertes se déploie séparément avec :
   `python alert_worker.py --interval 60`

## Vérifications avant ouverture

- Connexion et déconnexion
- Isolation entre deux comptes
- Suppression des données
- Soumission d’un feedback
- Défaillance d’une source économique
- Fonctionnement sans clé OpenAI
- Test mobile
- Test Chrome, Edge et Safari
- Vérification des logs
- Vérification du nombre d’appels Yahoo
