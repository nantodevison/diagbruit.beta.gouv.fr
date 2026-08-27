# Veille bruit & santé — diagBruit

Veille hebdomadaire automatisée des publications scientifiques sur le lien entre bruit et
santé, alimentant une base Notion "Études" sans intervention humaine. Voir
`docs/plan-veille-bruit-sante-diagbruit.md` pour le cadrage complet et
`docs/etape-N-conception-technique.md` pour le détail d'implémentation de chaque étape.

## Installation

```bash
cd veille-bruit-sante
pip install -r requirements.txt
cp .env.example .env  # puis renseigner les 3 cles
```

## Création de la base Notion (une seule fois)

```bash
python -m etape1_base_notion.creer_base_notion <id_page_notion_parente>
```

Partager ensuite la base créée avec l'intégration Notion (dans Notion : `···` sur la page
parente → `Connexions` → sélectionner l'intégration), puis reporter l'identifiant affiché
dans `NOTION_DATABASE_ID`.

## Exécution du run hebdomadaire

```bash
python main.py
```

Automatisé chaque semaine via `.github/workflows/veille-bruit-sante.yml` (voir
`docs/etape-4-conception-technique.md` pour le détail : secrets, horaire, gestion des
échecs).

## Statut de cette implémentation

Premier essai en conditions réelles fait le 26/08/2026, avec les 3 clés API. A révélé un
écart entre le cadrage initial et l'API Notion actuelle : depuis sa mise à jour du
2025-09-03, une base ("database") Notion peut contenir plusieurs "data sources" — le
schéma de colonnes et les pages vivent sur le data source, pas sur la base elle-même.
`databases.query` n'existe plus dans `notion-client`, et créer une page attend un
`data_source_id` en parent, pas un `database_id`. Corrigé (`notion_utils.py` résout
`database_id` -> `data_source_id` une fois en début de run) et reporté dans
`docs/etape-1-conception-technique.md` (Décision 4) et
`docs/etape-3-conception-technique.md` (Décision 1 et 3). `NOTION_DATABASE_ID` reste
inchangé pour l'utilisateur — c'est toujours l'ID de base copié depuis l'URL Notion.

Reste à vérifier en priorité, non encore couvert par un run complet réussi :

- le format exact des blocs renvoyés par l'outil `web_search`
  (`etape2_recherche_extraction/recherche_web.py` suppose des champs `title`/`url` sur
  chaque résultat — à confirmer sur un vrai appel) ;
- le rendu des propriétés `select`/`multi_select` Notion sur un premier lot de fiches
  réelles, notamment la création à la volée des valeurs de `revue` ;
- que la base pointée par `NOTION_DATABASE_ID` soit bien partagée avec l'intégration
  Notion (`···` → `Connexions` sur la page qui l'héberge) — un premier essai a échoué en
  404 sur ce point, à vérifier côté Notion.

Un essai avec `--limit` (à ajouter si utile, sur le modèle de
`poc-urbanisme-plu/etape2_analyse_reglements`) permettrait de valider le pipeline sur
quelques études avant un run complet.

**Note d'environnement local :** `pip install -r requirements.txt` installe dans
l'environnement Python global si aucun environnement virtuel n'est actif — a mis à jour
`anyio` vers une version incompatible avec `jupyter-server` déjà installé sur ce poste.
Préférer un environnement virtuel dédié (`python -m venv .venv`) pour ce projet.
