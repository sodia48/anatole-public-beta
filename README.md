# Anatole V4.6 — Public Beta Ready

Cette version est préparée pour un test public contrôlé avec authentification optionnelle, PostgreSQL, consentement, protections anti-abus, pages légales et fichiers de déploiement.

Consulte `DEPLOYMENT_PUBLIC_BETA.md` avant la mise en ligne.

# TSX 60 Market Dashboard Ultimate

Version multipage du tableau de bord Streamlit consacrée au S&P/TSX 60.
Elle ajoute les douze fonctions proposées : Market Pulse, screener, comparateur,
portefeuille, persistance SQLite, alertes hors session, explication des mouvements,
analyse des nouvelles, calendrier, backtesting, corrélations et rafraîchissement
partiel avec `st.fragment`.

## Fonctions incluses

1. **Market Pulse** : variation moyenne, largeur du marché, titres au-dessus des
   SMA 50/200, nouveaux sommets et creux, secteurs forts/faibles et volume relatif.
2. **Screener TSX 60** : RSI, momentum, tendances, volatilité, volume relatif,
   cassures et filtres fondamentaux optionnels.
3. **Comparateur** : performance en base 100, rendement annualisé, volatilité,
   Sharpe, drawdown et corrélations.
4. **Portefeuille virtuel** : positions modifiables, P&L, allocation, risque,
   VaR, Sharpe et drawdown.
5. **Watchlist persistante** : enregistrement dans `data/dashboard.db`.
6. **Alertes persistantes** : prix, variation quotidienne, RSI, volume relatif
   et croisements SMA20/SMA50. Un worker indépendant peut envoyer Telegram ou email.
7. **Pourquoi ça bouge ?** : explication heuristique combinant prix, secteur,
   volume, technique et manchettes.
8. **Actualités et sentiment** : dédoublonnage, catégorisation, importance,
   tonalité et synthèse française optionnelle avec OpenAI.
9. **Calendrier financier** : résultats, dividendes et événements macro ajoutés
   par l'utilisateur.
10. **Backtesting** : RSI, croisements de moyennes, SMA50, Bollinger et achat-conservation,
    avec frais et signaux décalés d'une séance.
11. **Corrélations** : matrice, paires fortes/faibles et corrélation mobile.
12. **Fragments Streamlit** : les métriques live se rafraîchissent sans relancer
    toute la page principale.

Un écran **Diagnostics** contrôle aussi le problème des 59/60 titres, la couverture
des données, les dépendances et les intégrations.

## Structure du projet

```text
tsx60_dashboard_ultimate/
├── app.py
├── alert_worker.py
├── requirements.txt
├── run_dashboard.bat
├── run_alert_worker.bat
├── core/
│   ├── ai.py
│   ├── analytics.py
│   ├── charts.py
│   ├── config.py
│   ├── data.py
│   ├── database.py
│   ├── runtime.py
│   ├── ui.py
│   └── utils.py
├── pages/
│   ├── 1_🔎_Screener.py
│   ├── 2_⚖️_Comparateur.py
│   ├── 3_💼_Portefeuille.py
│   ├── 4_🔔_Alertes.py
│   ├── 5_📰_Actualites.py
│   ├── 6_🗓️_Calendrier.py
│   ├── 7_🧪_Backtesting.py
│   ├── 8_🧩_Correlations.py
│   ├── 9_⭐_Watchlist.py
│   └── 10_🛠️_Diagnostics.py
└── .streamlit/
    └── secrets.toml.example
```

## Installation rapide sous Windows

Décompresse le projet, ouvre PowerShell dans le dossier, puis lance :

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Tu peux aussi double-cliquer sur `run_dashboard.bat`. Le premier démarrage installe
les dépendances.

## Configuration optionnelle

Copie :

```text
.streamlit/secrets.toml.example
```

vers :

```text
.streamlit/secrets.toml
```

Puis renseigne seulement les services utilisés.

### OpenAI

```toml
OPENAI_API_KEY = "..."
OPENAI_MODEL = "gpt-5.5"
```

La clé active la synthèse française des nouvelles. Le modèle reste configurable.

### Telegram

```toml
TELEGRAM_BOT_TOKEN = "..."
TELEGRAM_CHAT_ID = "..."
```

### Courriel SMTP

```toml
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = "587"
SMTP_USERNAME = "adresse@gmail.com"
SMTP_PASSWORD = "mot-de-passe-application"
SMTP_USE_TLS = "true"
ALERT_EMAIL_FROM = "adresse@gmail.com"
ALERT_EMAIL_TO = "destinataire@example.com"
```

Pour Gmail, utilise un mot de passe d'application plutôt que ton mot de passe principal.

## Worker d'alertes hors session

Les alertes sont conservées dans SQLite. Pour les vérifier même lorsque la page
Streamlit n'est pas ouverte, garde ce programme en marche :

```powershell
.\.venv\Scripts\python.exe alert_worker.py --interval 60
```

Ou double-clique sur `run_alert_worker.bat`.

Test unique :

```powershell
.\.venv\Scripts\python.exe alert_worker.py --once
```

Le worker doit tourner sur une machine ou un serveur actif. Streamlit Community
Cloud n'est pas conçu pour exécuter durablement ce deuxième processus; pour un
déploiement public, place le worker sur un service planifié distinct.

## Base de données

Les informations persistantes sont stockées dans :

```text
data/dashboard.db
```

Chaque nom saisi dans le champ **Profil local** possède sa propre watchlist, ses
positions, ses alertes et ses événements macro. Ce système est pratique en local,
mais ce n'est pas une authentification sécurisée. Pour un service public, remplace
SQLite et le profil libre par une vraie connexion utilisateur et PostgreSQL.

## Temps réel

Yahoo Finance est utilisé en mode indicatif et peut être différé. Le rafraîchissement
ne transforme pas une source différée en flux de marché officiel. Pour un produit
professionnel, il faut un fournisseur autorisé et les droits de données TSX adaptés.

## Limites importantes

- Les dates de calendrier fournies par les services gratuits peuvent être absentes
  ou modifiées.
- Les événements macro sont modifiables manuellement afin d'éviter de présenter une
  date obsolète comme officielle.
- Le sentiment des nouvelles repose sur un lexique déterministe; il peut manquer
  l'ironie, la nuance ou le contexte.
- Les explications de mouvements sont des facteurs potentiels, pas des causes prouvées.
- Le backtesting ne tient pas pleinement compte de la liquidité, de la fiscalité,
  des écarts acheteur-vendeur et des limites d'exécution.
- Les données et analyses ne constituent pas un conseil financier personnalisé.

## Dépannage

### `No module named streamlit_plotly_events2`

Installe les dépendances avec le Python du même environnement :

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Puis vérifie :

```powershell
.\.venv\Scripts\python.exe -c "from streamlit_plotly_events2 import plotly_events; print('OK')"
```

### La composition affiche moins de 60 titres

Ouvre la page **Diagnostics**. Elle affiche les symboles manquants, les nouveaux
symboles, les doublons et la source utilisée. La composition du fonds XIU peut
contenir des lignes techniques ou différer temporairement de la liste attendue.

### Réinitialiser les données locales

Arrête l'application et supprime `data/dashboard.db`. La base sera recréée au
prochain démarrage.

## Interface Anatole bleu ciel

Cette édition ajoute une identité visuelle complète inspirée des terminaux financiers modernes :

- fond bleu ciel en dégradé;
- cartes semi-transparentes de type glassmorphism;
- en-têtes et métriques modernisés;
- navigation latérale arrondie;
- boutons et filtres bleus;
- onglets en forme de capsules;
- graphiques Plotly harmonisés;
- meilleure adaptation aux écrans portables et mobiles.

Le thème natif se trouve dans `.streamlit/config.toml`. Les styles avancés communs à toutes les pages sont centralisés dans `core/ui.py`, tandis que le style des graphiques se trouve dans `core/charts.py`.

Après avoir remplacé les fichiers, arrête puis redémarre Streamlit afin que `config.toml` soit entièrement rechargé :

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## Prochain niveau pour rivaliser avec les grandes plateformes

Les développements suivants constitueraient une nouvelle phase produit :

1. flux WebSocket sous licence pour les cotations et carnets d'ordres;
2. graphique avancé avec outils de dessin, annotations et sauvegarde de modèles;
3. comptes utilisateurs sécurisés et synchronisation multiappareil;
4. synchronisation avec des courtiers et import automatique des transactions;
5. estimations d'analystes, transcriptions de résultats et révisions de consensus;
6. options, volatilité implicite, chaînes d'options et scénarios de risque;
7. couverture actions, FNB, indices, devises, matières premières et cryptomonnaies;
8. moteur d'alertes distribué avec notifications mobiles;
9. fil d'actualité personnalisé et assistant conversationnel de marché;
10. version mobile/PWA et offre d'abonnement.


## Correctifs appliqués

- Correction de la heatmap : la propriété Plotly `titlefont` de la colorbar a été remplacée par la syntaxe compatible avec les versions récentes de Plotly.
- Correction de la barre latérale : les noms de fichiers des pages ont été simplifiés pour éviter les caractères/émojis qui pouvaient s'afficher de manière illisible sur certains environnements Windows.



## Anatole V2

Cette version ajoute :

- une heatmap plus lisible ;
- un arrondi strict à **2 chiffres après la virgule** dans les tuiles ;
- une sidebar plus propre ;
- une présentation visuelle encore plus moderne.

### Important

Si tu avais déjà une ancienne version, supprime d'abord l'ancien dossier `pages/`
avant de recopier ce projet, afin d'éviter les doublons de pages dans Streamlit.


## Anatole V3 Ultra Premium

La V3 ajoute :

- un thème **bleu ciel** et un **mode sombre** dynamique ;
- une barre supérieure façon terminal financier ;
- un ruban animé des principales hausses et baisses ;
- des raccourcis vers le screener, le comparateur, le portefeuille et les nouvelles ;
- une heatmap en mode **Vue cinéma** ;
- des graphiques adaptés au thème clair ou sombre ;
- des animations discrètes et accessibles ;
- une interface plus large, plus lisible et plus moderne.

Le mode sombre et l'affichage compact sont disponibles dans la barre latérale.

### Mise à niveau depuis une ancienne version

Supprime complètement l'ancien dossier `pages` avant de recopier ce projet :

```powershell
Remove-Item -Recurse -Force .\pages
```

Puis recopie tous les fichiers de la V3 dans ton dossier de projet.


## Correctif V3.1

La propriété invalide `marker.pad = 3` de la heatmap a été remplacée par
`tiling.pad = 3`, qui est la propriété Plotly prévue pour espacer les tuiles.


## Correctif V3.2

Le haut de l'affichage a été réajusté pour éviter que la topbar et le hero
soient partiellement masqués par l'en-tête fixe de Streamlit.

---

# V4.1 Minimal Performance

La V4.1 simplifie fortement l'interface et accélère l'accueil. Consulte `RELEASE_NOTES_V4_1.md` pour la liste complète des 14 améliorations.

## Installation rapide sous Windows

```powershell
Ctrl + C
Copy-Item .\data\dashboard.db .\dashboard_backup.db -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

La page **Préférences** permet de choisir le thème, la densité, le niveau d'information, les animations et les éléments visibles sur l'accueil.


## V4.2 Signature

Cette édition restaure l'interface riche de la V4, tout en gardant les
optimisations de performance de la V4.1. Le style Signature est désormais
le style par défaut.




## Anatole V4.5 — Calendrier officiel gratuit

La page Calendrier agrège désormais des sources publiques officielles sans
clé API et sans abonnement :

- Statistique Canada : calendrier JSON des principaux indicateurs ;
- Banque du Canada : flux des événements à venir ;
- BLS : calendrier iCalendar des publications américaines essentielles ;
- BEA : calendrier JSON du PIB, du PCE et du commerce américain ;
- Réserve fédérale : dates des décisions du FOMC.

La section américaine reste volontairement ciblée sur les publications les
plus importantes pour les marchés. Aucun secret supplémentaire n'est requis.

Les sources externes peuvent être temporairement indisponibles ou modifier
leur format. Anatole affiche l'état de chaque source dans la page Calendrier.
