# POC — Automatisation des règles PLU (diagBruit)

Preuve de concept, indépendante du produit diagBruit, qui automatise
l'intégration dans diagBruit de nouvelles règles issues des plans locaux
d'urbanisme (PLU, PLUi, RNU, POS, cartes communales...) disponibles sur le
Géoportail de l'urbanisme, en complément des informations déjà fournies par
diagBruit (plan d'exposition au bruit, classement sonore des voies).

## Objectif

diagBruit fonctionne sur deux échelles distinctes :
- **Échelle d'intégration d'un territoire** : le **département** — diagBruit
  n'est pas disponible France entière, les territoires sont ajoutés
  progressivement, département par département.
- **Échelle d'utilisation** : la **parcelle cadastrale**, niveau auquel
  l'utilisateur final interroge l'outil.

Ce POC porte sur la **création de la donnée à l'échelle départementale** : à
partir d'un code département, il produit une **couverture SIG complète du
département**, composée de surfaces qui traduisent les endroits où
s'appliquent des règles d'urbanisme liées au bruit. diagBruit interrogera
ensuite cette couverture via une requête SIG d'intersection entre la
géométrie de la parcelle cadastrale et les géométries des zones produites.

Le détail du raisonnement (objectif, échelles, règles de construction de la
couverture, points de vigilance) est dans
[`docs/plan-automatisation-regles-plu-diagbruit.md`](docs/plan-automatisation-regles-plu-diagbruit.md).

## Documentation

Chaque étape a deux documents dans [`docs/`](docs/) :
- un document **métier** (objectif, logique, résultat — pour un chargé de projet) ;
- un document **conception technique** (structure du code, formats de données — pour un développeur).

| Étape | Métier | Conception technique |
|---|---|---|
| Plan d'ensemble | [`plan-automatisation-regles-plu-diagbruit.md`](docs/plan-automatisation-regles-plu-diagbruit.md) | — |
| 1 — Identification des documents | [`etape-1-identification-documents-urbanisme-diagbruit.md`](docs/etape-1-identification-documents-urbanisme-diagbruit.md) | [`etape-1-conception-technique.md`](docs/etape-1-conception-technique.md) |
| 2 — Analyse des règlements | [`etape-2-analyse-documents-urbanisme-diagbruit.md`](docs/etape-2-analyse-documents-urbanisme-diagbruit.md) | [`etape-2-conception-technique.md`](docs/etape-2-conception-technique.md) |
| 3 — Validation manuelle | [`etape-3-validation-manuelle.md`](docs/etape-3-validation-manuelle.md) | [`etape-3-conception-technique.md`](docs/etape-3-conception-technique.md) |
| 4 — Construction des géométries | [`etape-4-construction-geometries-diagbruit.md`](docs/etape-4-construction-geometries-diagbruit.md) | [`etape-4-conception-technique.md`](docs/etape-4-conception-technique.md) |
| 5 — Rédaction des messages | [`etape-5-redaction-messages-diagbruit.md`](docs/etape-5-redaction-messages-diagbruit.md) | [`etape-5-conception-technique.md`](docs/etape-5-conception-technique.md) |
| 6 — Mise en forme | [`etape-6-mise-en-forme-diagbruit.md`](docs/etape-6-mise-en-forme-diagbruit.md) | [`etape-6-conception-technique.md`](docs/etape-6-conception-technique.md) |
| 7 — Stockage (Strapi / Notion) | [`etape-7-stockage-diagbruit.md`](docs/etape-7-stockage-diagbruit.md) | [`etape-7-conception-technique.md`](docs/etape-7-conception-technique.md) |

Les limites connues du code actuel, non corrigées à ce stade, sont toutes regroupées dans un document unique, indépendant des étapes ci-dessus : [`ameliorations-identifiees.md`](docs/ameliorations-identifiees.md).

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

### Accès Strapi et Notion (nécessaires pour l'étape 7)

L'étape 7 (insertion dans Strapi et Notion) a besoin de quatre variables
supplémentaires dans le même `.env` : `PERSONNAL_NOTION_TOKEN`,
`NOTION_DATABASE_ID`, `STRAPI_API_TOKEN` et `STRAPI_URL` — voir les
commentaires de `.env.example` et
[`etape-7-conception-technique.md`](docs/etape-7-conception-technique.md)
pour le détail de chaque valeur.

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

## Structure et étapes

Chaque étape du plan est un sous-dossier autonome, prenant en entrée le ou
les fichiers produits par l'étape précédente et écrivant sa propre sortie
dans `output/` (non versionné). Toutes les commandes ci-dessous s'exécutent
depuis `poc-urbanisme-plu/`, avec un code département sur 3 chiffres
(exemple : `067`). Voir `etape-1-conception-technique.md` pour le
raisonnement détaillé de ce découpage.

### Étape 1 — Identification des documents d'urbanisme

Identifie, pour un département, les documents d'urbanisme actuellement en
vigueur (PLU, PLUi, RNU, POS, carte communale) via le Géoportail de
l'urbanisme.

```bash
python -m etape1_identification.main --dept 067
```

### Étape 2 — Analyse des règlements

Analyse les règlements écrits des documents identifiés à l'étape 1 (un
pré-filtrage par mots-clés réduit le texte soumis à l'IA) pour repérer les
mentions liées au bruit, via l'API Anthropic. Nécessite un `etape1_{dept}.csv`
existant et la clé API Anthropic.

```bash
# --limit plafonne le nombre de pièces traitées, utile pour un premier
# essai maîtrisé en coût (chaque passage classifié est un appel facturé).
python -m etape2_analyse_reglements.main --dept 067 --limit 5
```

### Étape 3 — Validation manuelle des occurrences

Un opérateur relit les occurrences produites à l'étape 2 dans un outil HTML
autonome, et l'étape réintègre aussi les communes RNU et les trous de
couverture. Nécessite un `etape2_{dept}.csv` existant.

```bash
python -m etape3_validation_manuelle.preparer_revue --dept 067
# ouvrir etape3_validation_manuelle/outil_validation.html, charger
# etape3_067_a_valider.csv, relire, exporter
python -m etape3_validation_manuelle.synthese_finale --dept 067
```

### Étape 4 — Construction des géométries

Construit la géométrie de chaque occurrence validée : récupération
automatique (contour administratif ou périmètre du document via l'API Carto
du GPU) quand la portée le permet, tracé manuel dans QGIS sinon. Nécessite un
`etape3_{dept}.csv` existant.

```bash
python -m etape4_geometries.preparer_geometries --dept 067
# ouvrir etape4_067_a_completer.gpkg dans QGIS (modele_validation_manuelle.qgz
# fournit un projet type), compléter la couche occurrences_a_georeferencer
python -m etape4_geometries.synthese_geometries --dept 067
```

### Étape 5 — Rédaction des messages

Rédige, par appel LLM, le message et le titre associés à chaque occurrence
validée des documents significatifs (messages fixes pour les documents non
significatifs, les communes RNU et les trous de couverture), avec relecture
humaine et vérification orthographique. Nécessite un `etape4_{dept}.gpkg`
existant et la clé API Anthropic.

```bash
python -m etape5_redaction_messages.controle_similarite --dept 067
python -m etape5_redaction_messages.preparer_messages --dept 067
# ouvrir etape5_redaction_messages/outil_validation.html, charger les CSV
# produits, relire, exporter
python -m etape5_redaction_messages.synthese_messages --dept 067
python -m etape5_redaction_messages.verifier_orthographe --dept 067
# ouvrir etape5_067.gpkg dans QGIS, filtrer sur "_validation_orthographe" != ''
```

### Étape 6 — Mise en forme

Assemble les messages validés à l'étape 5 et prépare tout ce dont l'équipe
métier a besoin pour saisir rapidement les entrées correspondantes dans
Strapi et Notion (territoire proposé, gabarit de message, géométries
exportées en `.geojson`). Nécessite un `etape4_{dept}.gpkg`, un
`etape5_{dept}.gpkg` et un `etape5_{dept}_documents_par_synthese.csv`
existants.

```bash
python -m etape6_mise_en_forme.generer_export --dept 067
# ouvrir etape6_mise_en_forme/outil_validation.html, charger
# etape6_067_export.csv, compléter le terme métier de l'alert_slug pour
# chaque ligne, exporter (renommer le dernier export en
# etape6_067_export.csv, ou l'utiliser tel quel)
```

### Étape 7 — Stockage (Strapi / Notion)

Crée ou met à jour automatiquement, via leurs API respectives, l'entrée
Strapi (texte du message) et la page Notion (géométrie jointe, `alert_slug`)
de chaque ligne préparée à l'étape 6. Nécessite un `etape6_{dept}_export.csv`
et un dossier `etape6_{dept}_geometries/` existants, ainsi que les identifiants
Strapi et Notion (voir "Installation" ci-dessus). Sans `--envoyer`, la
commande n'écrit rien et se contente d'afficher ce qu'elle ferait.

```bash
python -m etape7_stockage.inserer --dept 067
# → dry-run : liste ce qui serait créé/mis à jour, sur Strapi et Notion

python -m etape7_stockage.inserer --dept 067 --envoyer
# → exécute réellement les créations/mises à jour
```
