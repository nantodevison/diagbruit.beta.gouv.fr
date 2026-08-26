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

Première implémentation d'après les documents de conception technique, non encore testée
en conditions réelles (nécessite les 3 clés API pour un essai de bout en bout). À vérifier
en priorité avant le premier run planifié :

- le format exact des blocs renvoyés par l'outil `web_search`
  (`etape2_recherche_extraction/recherche_web.py` suppose des champs `title`/`url` sur
  chaque résultat — à confirmer sur un vrai appel) ;
- le rendu des propriétés `select`/`multi_select` Notion sur un premier lot de fiches
  réelles, notamment la création à la volée des valeurs de `revue`.

Un essai avec `--limit` (à ajouter si utile, sur le modèle de
`poc-urbanisme-plu/etape2_analyse_reglements`) permettrait de valider le pipeline sur
quelques études avant un run complet.
