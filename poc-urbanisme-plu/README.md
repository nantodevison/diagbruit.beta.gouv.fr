# POC — Automatisation des règles PLU (diagBruit)

Preuve de concept, indépendante du produit diagBruit, qui automatise
l'identification et l'analyse des règles d'urbanisme liées au bruit issues
des documents disponibles sur le Géoportail de l'urbanisme.

Le cadrage complet (objectif, étapes, décisions techniques) est documenté
dans [`docs/`](docs/) :
- [`plan-automatisation-regles-plu-diagbruit.md`](docs/plan-automatisation-regles-plu-diagbruit.md) — plan d'ensemble
- [`etape-1-identification-documents-urbanisme-diagbruit.md`](docs/etape-1-identification-documents-urbanisme-diagbruit.md) — détail de l'étape 1
- [`etape-1-conception-technique.md`](docs/etape-1-conception-technique.md) — décisions techniques (structure du code, gestion des erreurs, formats)
- [`etape-2-analyse-documents-urbanisme-diagbruit.md`](docs/etape-2-analyse-documents-urbanisme-diagbruit.md) — détail de l'étape 2
- [`etape-2-conception-technique.md`](docs/etape-2-conception-technique.md) — décisions techniques de l'étape 2 (SDK Anthropic, structured outputs, OCR)

## Installation

```bash
python -m venv venv
source venv/bin/activate   # ou venv\Scripts\activate sous Windows
pip install -r requirements.txt
```

### Clé API Anthropic (nécessaire pour l'étape 2)

L'étape 2 (analyse des règlements) appelle l'API Anthropic. Copier
`.env.example` vers `.env` à la racine de `poc-urbanisme-plu/` et y
renseigner une clé créée sur la [Console Anthropic](https://console.anthropic.com/) :

```bash
cp .env.example .env
# puis éditer .env et remplacer sk-ant-... par la vraie clé
```

`.env` n'est jamais versionné (voir `.gitignore`).

### OCR (Tesseract + Poppler) — pour les PDF scannés de l'étape 2

`pytesseract` et `pdf2image` (déjà dans `requirements.txt`) s'appuient
chacun sur un programme externe à installer séparément, hors `pip` :

1. **Tesseract OCR** — build Windows communautaire UB-Mannheim :
   https://github.com/UB-Mannheim/tesseract/wiki. Lancer l'installeur en
   cochant le paquet linguistique **French** (`fra.traineddata`), puis
   ajouter le dossier d'installation (par défaut
   `C:\Program Files\Tesseract-OCR`) au `PATH`.
2. **Poppler** (dépendance de `pdf2image`) — build Windows précompilé :
   https://github.com/oschwartz10612/poppler-windows/releases. Extraire
   l'archive et ajouter le sous-dossier `Library\bin` au `PATH`.
3. Vérifier l'installation (ouvrir un nouveau terminal après modification
   du `PATH`) :
   ```powershell
   tesseract --version
   tesseract --list-langs   # "fra" doit apparaître dans la liste
   pdftoppm -h
   ```

Alternative plus rapide si [Chocolatey](https://chocolatey.org/) est
installé (gère le `PATH` automatiquement) :
```powershell
choco install tesseract poppler -y
```

Sans ces deux outils, l'OCR échoue proprement pour les PDF scannés
rencontrés : la pièce concernée part en erreur documentée dans
`etape2_{dept}_erreurs.csv`, sans jamais bloquer le reste du traitement.

## Structure

Chaque étape du plan est un sous-dossier autonome, prenant en entrée le
fichier produit par l'étape précédente et écrivant sa propre sortie dans
`output/` (non versionné). Voir `etape-1-conception-technique.md` pour le
détail de ce découpage et son raisonnement.

- `etape1_identification/` — identification des documents d'urbanisme en
  vigueur d'un département.
  ```bash
  python -m etape1_identification.main --dept 067
  ```
- `etape2_analyse_reglements/` — analyse des documents identifiés à l'étape 1
  pour repérer les règles liées au bruit (nécessite un `etape1_{dept}.csv`
  existant, ainsi que la clé API Anthropic ci-dessus).
  ```bash
  # --limit plafonne le nombre de pièces traitées, utile pour un premier
  # essai maîtrisé en coût (chaque passage classifié est un appel facturé).
  python -m etape2_analyse_reglements.main --dept 067 --limit 5
  ```
