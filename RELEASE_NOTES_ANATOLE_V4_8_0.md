# Anatole V4.8.0 — Multi-univers TSX

## Nouveautés

- Ajout d'un sélecteur d'univers dans la barre latérale :
  - S&P/TSX 60 ;
  - S&P/TSX Composite ;
  - TSX complet / étendu.
- Les pages existantes conservent les mêmes segments :
  Cockpit, Screener, Moteurs du marché, Actualités, Calendrier, Mode Focus,
  Comparateur, Portefeuille, Watchlist et Alertes.
- Chargement progressif :
  - TSX 60 : mode rapide ;
  - Composite : plus large, borné pour rester fluide ;
  - TSX complet / étendu : liste TMX/CSV si disponible, sinon proxy large XIC + XMD.
- Les caches sont séparés par univers.
- Le changement d'univers force uniquement le renouvellement des données live.
- Les titres affichés sont limités intelligemment pour préserver la performance.

## Configuration facultative pour le TSX complet exact

Ajoute un fichier `data/tsx_universe.csv` ou une variable d'environnement
`ANATOLE_TMX_ISSUERS_URL` pointant vers un CSV ayant au minimum une colonne
`Symbol` ou `Ticker`.

Colonnes reconnues :
- Symbol / Ticker ;
- Company / Company Name / Issuer Name ;
- Sector.

Sans fichier externe, Anatole utilise un univers élargi basé sur les holdings
XIC + XMD et une graine de secours intégrée.
