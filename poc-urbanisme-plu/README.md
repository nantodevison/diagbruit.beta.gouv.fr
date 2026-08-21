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
- [`etape-5-redaction-messages-diagbruit.md`](docs/etape-5-redaction-messages-diagbruit.md) — détail de l'étape 5
- [`etape-5-conception-technique.md`](docs/etape-5-conception-technique.md) — décisions techniques de l'étape 5
- [`etape-6-mise-en-forme-diagbruit.md`](docs/etape-6-mise-en-forme-diagbruit.md) — note initiale, minimale, à développer

*(Les étapes 3 et 4 ont aussi leurs documents dans `docs/`, non listés ici — cette liste n'a pas été tenue à jour à chaque étape ; à corriger si vous voulez qu'elle serve de sommaire fiable.)*

## Installation

```bash
python -m venv venv
source venv/bin/activate   # ou venv\Scripts\activate sous Windows
pip install -r requirements.txt
```

### Clé API Anthropic (nécessaire pour les étapes 2 et 5)

L'étape 2 (analyse des règlements) et l'étape 5 (rédaction des messages, Phase 2) appellent l'API Anthropic. Copier
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
- `etape5_redaction_messages/` — garde-fou de cohérence géométrique puis
  rédaction des messages (nécessite un `etape4_{dept}.gpkg` existant, ainsi
  que la clé API Anthropic ci-dessus pour la Phase 2). Entre la Phase 2 et la
  Phase 4, ouvrir `etape5_redaction_messages/outil_validation.html` dans un
  navigateur pour relire/corriger (voir `etape-5-conception-technique.md`,
  "Phase 3").
  ```bash
  python -m etape5_redaction_messages.controle_similarite --dept 067
  python -m etape5_redaction_messages.preparer_messages --dept 067
  # ouvrir outil_validation.html, charger les CSV produits, exporter
  python -m etape5_redaction_messages.synthese_messages --dept 067
  python -m etape5_redaction_messages.verifier_orthographe --dept 067
  # ouvrir etape5_067.gpkg dans QGIS, filtrer sur "_validation_orthographe" != ''
  ```
