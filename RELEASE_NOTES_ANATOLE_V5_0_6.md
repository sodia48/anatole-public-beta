# Anatole V5.0.6 — Synchronisation complète de l'univers

## Problème corrigé

Sur mobile, lorsqu'un utilisateur sélectionnait `TSX étendu`, certains tableaux
changeaient, mais plusieurs blocs du cockpit pouvaient encore donner l'impression
d'utiliser les données du TSX 60.

## Correction

- Le changement d'univers vide maintenant les caches liés à l'univers.
- Les widgets de sélection mobile et sidebar sont synchronisés sans écraser le choix mobile.
- Les graphiques du cockpit utilisent une clé liée à l'univers sélectionné.
- Anatole ne remplace plus silencieusement `Composite` ou `TSX étendu` par `TSX 60` en cas de difficulté réseau.
- Les snapshots de secours sont filtrés par les tickers demandés pour éviter une fuite visuelle du TSX 60.
- Les diagnostics indiquent clairement l'univers sélectionné.
- Aucune migration PostgreSQL.
- Aucune nouvelle dépendance.

## Fichiers clés

- `core/data.py`
- `core/runtime.py`
- `core/universe.py`
- `screens/0_Accueil.py`
- `screens/1_Screener.py`
