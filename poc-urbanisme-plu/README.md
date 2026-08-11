# POC — Automatisation des règles PLU (diagBruit)

Preuve de concept, indépendante du produit diagBruit, qui automatise
l'identification et l'analyse des règles d'urbanisme liées au bruit issues
des documents disponibles sur le Géoportail de l'urbanisme.

Le cadrage complet (objectif, étapes, décisions techniques) est documenté
dans [`docs/`](docs/) :
- [`plan-automatisation-regles-plu-diagbruit.md`](docs/plan-automatisation-regles-plu-diagbruit.md) — plan d'ensemble
- [`etape-1-identification-documents-urbanisme-diagbruit.md`](docs/etape-1-identification-documents-urbanisme-diagbruit.md) — détail de l'étape 1
- [`etape-1-conception-technique.md`](docs/etape-1-conception-technique.md) — décisions techniques (structure du code, gestion des erreurs, formats)

## Installation

```bash
python -m venv venv
source venv/bin/activate   # ou venv\Scripts\activate sous Windows
pip install -r requirements.txt
```

## Structure

Chaque étape du plan est un sous-dossier autonome, prenant en entrée le
fichier produit par l'étape précédente et écrivant sa propre sortie dans
`output/` (non versionné). Voir `etape-1-conception-technique.md` pour le
détail de ce découpage et son raisonnement.

- `etape1_identification/` — identification des documents d'urbanisme en
  vigueur d'un département.
