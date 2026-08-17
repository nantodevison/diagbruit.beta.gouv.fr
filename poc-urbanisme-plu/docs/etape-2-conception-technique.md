# Étape 2 — Conception technique : analyse des documents d'urbanisme pour repérer les règles liées au bruit

*Document de cadrage technique, faisant suite à `etape-2-analyse-documents-urbanisme-diagbruit.md` et à `etape-1-conception-technique.md`. Révisé le 17/08/2026 suite à la conception de l'étape 4 : ajout du champ `portee_geometrique` au schéma structuré et au prompt de classification.*

## Posture

Ce module reste un sous-dossier du même POC que l'étape 1, sous la même posture générale (voir `etape-1-conception-technique.md`) : code écrit par un non-développeur, isolé du reste du produit, preuve de concept plutôt que composant prêt à intégrer.

## Architecture des dossiers

```
poc-urbanisme-plu/
├── etape1_identification/               # existant
├── etape2_analyse_reglements/
│   ├── main.py                          # point d'entrée : python -m etape2_analyse_reglements.main --dept 033
│   ├── resolution_pieces.py             # Phase 1 — document-details : id_gpu → pièces + URLs
│   ├── extraction_texte.py              # Phase 2 — extraction PDF par page, OCR si besoin
│   ├── filtrage_lexical.py              # Phase 3 — inclusion + tag d'exclusion
│   ├── classification.py                # Phase 4 — appel API par passage retenu
│   └── synthese.py                      # Phase 5 — écriture etape2_{dept}.csv + fichier d'erreurs
└── output/
    ├── etape1_{dept}.csv
    ├── etape1_{dept}_erreurs.csv
    ├── etape2_{dept}.csv
    └── etape2_{dept}_erreurs.csv
```

Chaque module correspond à une phase du document descriptif et reste relançable indépendamment à partir de son fichier d'entrée : aucune dépendance de code entre `etape1_identification/` et `etape2_analyse_reglements/`, seulement une dépendance de données via les fichiers CSV.

## Résolution des pièces (Phase 1)

L'API `document/{id}/details` du GPU ne renvoie pas une liste de « pièces » typées avec leurs URLs, mais deux structures parallèles : `files` (la liste brute des noms de fichiers du document) et `writingMaterials` (un dictionnaire `{nom_fichier: url_de_téléchargement}` couvrant les mêmes fichiers).

Le nom de chaque fichier encode son rôle par un segment fixe (ex. `{siren}_reglement_{date}.pdf`, `{siren}_padd_{date}.pdf`, `{siren}_orientations_amenagement_{date}.pdf`, `{siren}_reglement_graphique_N_{date}.pdf`, `{siren}_prescription_surf_..._{date}.pdf`, `{siren}_rapport_N_{date}.pdf`...). Seuls les fichiers dont le nom correspond sans ambiguïté à l'une des quatre valeurs de `type_piece_source` (`règlement écrit`, `OAP`, `PADD`, `PSMV`) sont retenus comme pièce ; le reste (rapport de présentation, plans graphiques, couches de prescriptions structurées, procédure, servitudes...) est hors périmètre.

Point d'attention : le nom d'une annexe de prescription structurée peut lui-même contenir le mot "reglement" (ex. le règlement d'un PPRi annexé comme servitude, nommé `..._prescription_surf_..._reglement_..._.pdf`) — les motifs d'exclusion (`prescription_surf`/`prescription_lin`, `info_surf`/`info_lin`) sont donc testés avant le motif générique de règlement, pour ne pas classer ces annexes à tort comme le règlement écrit du document.

Pour un document dont la `nature_document` (colonne de l'étape 1) vaut `PSMV`, la pièce de règlement est typée `PSMV` plutôt que `règlement écrit` (nature juridique différente, voir la colonne `nature_juridique_piece` plus bas).

Un même `id_gpu` (typiquement un PLUi intercommunal) apparaît sur autant de lignes du CSV d'entrée que de communes couvertes : il est dédoublonné avant tout appel réseau, dans le même esprit que le dédoublonnage des EPCI à l'étape 1 — sans cela, un même document serait interrogé et téléchargé des centaines de fois pour un seul département.

Un `etape1_{dept}.csv` introuvable est une erreur irrécupérable pour l'étape 2 entière (rien d'exploitable en aval) ; l'échec de résolution d'un `id_gpu` individuel, lui, est isolé (voir "Gestion des erreurs").

## Extraction de texte (Phase 2)

`pdfplumber` extrait le texte PDF page par page. Un score de confiance sur le texte extrait (densité de caractères reconnus, présence de mots courants) détermine s'il s'agit d'un scan ; le cas échéant, `pytesseract` + `pdf2image` prennent le relais pour l'OCR, et le score de confiance renvoyé par l'OCR est traduit dans le champ `ocr_confiance` (élevée / moyenne / faible). Un échec d'OCR (binaire absent ou erreur de traitement) n'interrompt jamais le run : la pièce concernée part en erreur documentée (voir "Gestion des erreurs").

`pytesseract` et `pdf2image` sont de simples wrappers Python : ils s'appuient chacun sur un programme externe qui doit être installé séparément sur la machine (pas via `pip`) :

- **Tesseract OCR** — build Windows communautaire UB-Mannheim : `https://github.com/UB-Mannheim/tesseract/wiki`. Installer, en cochant le paquet linguistique **French** (`fra.traineddata`), puis ajouter le dossier d'installation (par défaut `C:\Program Files\Tesseract-OCR`) au `PATH`. Vérification : `tesseract --version` et `fra` présent dans `tesseract --list-langs`.
- **Poppler** (dépendance de `pdf2image`) — build Windows précompilé : `https://github.com/oschwartz10612/poppler-windows/releases`. Extraire l'archive et ajouter le sous-dossier `Library\bin` au `PATH`. Vérification : `pdftoppm -h`.
- Alternative pour les deux via Chocolatey si disponible : `choco install tesseract poppler -y` (gère le `PATH` automatiquement).

## Filtrage lexical (Phase 3)

Deux recherches textuelles simples (pas besoin de bibliothèque dédiée) sur le texte extrait, paragraphe par paragraphe : la liste d'inclusion retient un passage, la liste d'exclusion pose un tag sur les passages retenus qui contiennent en plus un terme évoquant classement sonore/PEB. Aucune suppression n'a lieu à ce stade — l'arbitrage revient à la phase de classification.

Le texte extrait par `pdfplumber` (ou par l'OCR) ne porte pas de marquage fiable de paragraphe : le découpage se fait d'abord sur les lignes vides ; si une page ne produit qu'un seul bloc (PDF sans ligne vide entre paragraphes, cas fréquent), le texte est regroupé ligne à ligne en blocs d'une taille cible de 400 caractères, en coupant aussi au début d'un nouvel "Article" pour ne pas mélanger deux articles dans un même bloc.

Le repérage de la référence (`reference_type`/`reference_precise`) recherche une numérotation "Article N" en tête de chaque paragraphe — jamais en milieu de phrase, pour ne pas confondre avec une citation d'un autre code (ex. "l'article L.302-1 du code de l'urbanisme") — et écarte explicitement les captures de la forme "L.302-1", "R. 111-2"... (lettre de code suivie d'un chiffre), caractéristiques d'une référence légale plutôt que d'un article du document lui-même. Un "Article N" (et éventuellement un "alinéa N") repéré reste la référence courante jusqu'au suivant ; à défaut de numérotation fiable, la référence retombe sur le numéro de page.

Chaque passage retenu est transmis à la phase 4 avec le bloc qui le précède (`contexte_avant`) et celui qui le suit (`contexte_apres`) dans le document, tronqués à 300 caractères chacun — en conservant, pour chacun, la partie la plus proche du passage (la fin du bloc précédent, le début du bloc suivant), pour que la phase 4 ait accès à la partie du contexte la plus susceptible de compléter une règle qui déborde du bloc central.

## Appel de classification (Phase 4)

Un appel à l'API Anthropic (SDK officiel `anthropic`, modèle `claude-sonnet-5`) par passage retenu, plutôt qu'un traitement par lot : un échec ne fait perdre qu'une ligne, jamais un document entier, et chaque ligne du CSV de sortie reste reliée à un appel identifiable individuellement. `claude-sonnet-5` offre un bon équilibre qualité/coût pour une tâche de classification de texte juridique français, une vérification humaine étant prévue en aval (étape 5).

La réponse est contrainte à un schéma JSON via la fonctionnalité **structured outputs** de l'API (`output_config.format`), qui garantit une réponse conforme au schéma par construction — pas de dépendance à un prompt demandant "réponds en JSON", ni de risque de réponse mal formée à gérer explicitement (voir "Gestion des erreurs").

Le prompt transmet le passage, son contexte immédiat (`contexte_avant`/`contexte_apres`) et le type de pièce source, puis demande au modèle :
- si le passage constitue une règle autonome liée au bruit dans le périmètre de diagBruit (voir `etape-2-analyse-documents-urbanisme-diagbruit.md`, phase 4, pour la définition complète — distinction renvoi simple/règle autonome pour le classement sonore/PEB, et cas des règles limitées à l'infrastructure de transport) ;
- sa nature (prescription/recommandation) et sa nature sonore ;
- la zone réglementaire mentionnée, le cas échéant ;
- **(ajouté le 17/08/2026)** sa portée géométrique — administrative (contour du zonage, de la commune ou de l'EPCI) ou zone spécifique (une zone réglementaire précise) — voir le nouveau bloc de prompt ci-dessous, qui reprend la distinction Alinéa 1/Alinéa 2 déjà posée dans `plan-automatisation-regles-plu-diagbruit.md` ;
- une citation verbatim (`extrait_significatif`) qui isole le mieux la règle, choisie librement dans le passage et son contexte immédiat — le contexte est transmis précisément pour que le modèle puisse y puiser si la règle y déborde (phrase commencée dans le contexte avant, terminée dans le contexte après, etc.) ;
- un niveau de confiance (`confiance_extrait`) sur la clarté de cette citation, qui signale aussi, le cas échéant, qu'une règle par ailleurs claire ne concerne que l'infrastructure de transport (la raison précise est alors à lire dans `justification`, le raisonnement complet renvoyé par le modèle).

Le raisonnement (thinking) est désactivé sur cet appel : `claude-sonnet-5` réfléchit par défaut (adaptive thinking) dès lors que ce paramètre n'est pas précisé, et ce raisonnement est décompté de `max_tokens` même s'il n'est pas affiché. Une tâche de classification structurée comme celle-ci n'a pas besoin de raisonnement approfondi ; le désactiver laisse tout le budget de tokens (`max_tokens=800`, calibré pour laisser la place à une justification détaillée) à la réponse, et réduit coût et latence.

La citation renvoyée par le modèle (`extrait_significatif`) est vérifiée côté code comme étant réellement un extrait verbatim du texte fourni (contexte avant + passage + contexte après, après normalisation des espaces) ; si elle ne l'est pas (le modèle a reformulé malgré la consigne), le code retombe sur un découpage mécanique du passage plutôt que de perdre l'occurrence. `confiance_extrait` peut valoir "faible" pour deux raisons distinctes (citation peu claire, ou règle limitée à l'infrastructure de transport) : plutôt qu'une colonne dédiée à chacune, la consigne exige que `justification` précise laquelle des deux s'applique — voir `etape-2-ameliorations-possibles.md` pour la piste d'un champ séparé si ce choix gêne la relecture à l'usage.

Note sur `contexte_documentaire` (colonne du CSV de synthèse, voir plus bas) : quand `extrait_significatif` déborde sur `contexte_avant` ou `contexte_apres`, la portion commune s'affiche deux fois dans cette colonne (concaténation simple, sans déduplication) — voir `etape-2-ameliorations-possibles.md` pour le détail.

```python
import json
import os
import re

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()
client = Anthropic()


def normaliser_espaces(texte):
    return re.sub(r"\s+", " ", texte).strip()


SCHEMA_CLASSIFICATION = {
    "type": "object",
    "properties": {
        "retenu": {"type": "boolean"},
        # Un enum nullable s'exprime via anyOf : "type": ["string", "null"]
        # combiné à "enum" est rejeté par le validateur de schéma de l'API.
        "nature_occurrence": {
            "anyOf": [
                {"type": "string", "enum": ["prescription", "recommandation"]},
                {"type": "null"},
            ]
        },
        "nature_sonore_zone": {
            "anyOf": [
                {"type": "string", "enum": ["lutte_bruit_existant", "preservation_zone_calme", "autre"]},
                {"type": "null"},
            ]
        },
        "zone_reglementaire_mentionnee": {"type": ["string", "null"]},
        # Ajouté le 17/08/2026 : portée géométrique de la règle, nécessaire à
        # l'étape 4 pour savoir si une géométrie automatique (contour administratif)
        # suffit, ou si un tracé manuel dédié est requis. Distinct de
        # zone_reglementaire_mentionnee ci-dessus : celui-ci dit QUELLE zone est
        # citée dans le texte (libre, informatif) ; portee_geometrique dit QUEL
        # PROCESSUS DE GÉOMÉTRIE appliquer (contrôlé, exploité par le code).
        "portee_geometrique": {
            "anyOf": [
                {"type": "string", "enum": ["administrative", "zone_specifique"]},
                {"type": "null"},
            ]
        },
        "justification": {"type": "string"},
        # Citation verbatim choisie par le modèle dans le passage et son
        # contexte immédiat — vérifiée côté code comme sous-ensemble du texte
        # fourni (voir plus bas).
        "extrait_significatif": {"type": ["string", "null"]},
        # Le découpage automatique en paragraphes produit parfois un extrait
        # qui mélange plusieurs sujets ou coupe une phrase. Ce score aide le
        # relecteur humain à prioriser sa vérification.
        "confiance_extrait": {
            "anyOf": [
                {"type": "string", "enum": ["faible", "moyenne", "forte", "totale"]},
                {"type": "null"},
            ]
        },
    },
    "required": [
        "retenu",
        "nature_occurrence",
        "nature_sonore_zone",
        "zone_reglementaire_mentionnee",
        "portee_geometrique",
        "justification",
        "extrait_significatif",
        "confiance_extrait",
    ],
    "additionalProperties": False,
}


def classifier_passage(passage_texte, contexte_avant, contexte_apres, type_piece, extrait_repli):
    prompt = f"""Tu analyses un extrait d'un document d'urbanisme français ({type_piece})
pour repérer des règles autonomes liées au bruit, dans le périmètre de
diagBruit : les projets de construction de bâtiments et les projets
d'aménagement urbain. Une règle qui ne concerne QUE la réalisation d'une
infrastructure de transport elle-même (voirie, voie ferrée...), sans rapport
avec des bâtiments ou l'urbanisation à proximité, reste à signaler
(retenu=true) mais avec une confiance faible (voir plus bas) — précise-le
explicitement dans justification.

Le classement sonore des voies et le plan d'exposition au bruit (PEB) d'un
aéroport sont déjà traités ailleurs par diagBruit : la mention d'un secteur
affecté par le bruit de ces infrastructures classées n'est donc PAS
automatiquement une règle autonome. Distingue deux cas :
- Simple renvoi (retenu=false) : le passage se contente de rappeler que
  l'isolement acoustique standard prévu par l'arrêté préfectoral (classement
  sonore) ou par le PEB s'applique dans ce secteur — aucune règle propre au
  document d'urbanisme n'est ajoutée.
- Règle autonome (retenu=true) : le secteur défini par le classement sonore
  ou le PEB sert de simple repère géographique pour une règle DIFFÉRENTE de
  l'isolement acoustique standard, ou une exigence d'isolement qui va
  au-delà de celle prévue par l'arrêté/le PEB.

Si retenu=true, détermine aussi la portée géométrique de la règle
(portee_geometrique) :
- "administrative" : la règle s'applique à l'ensemble du zonage couvert par
  le document, à l'ensemble d'une commune, ou à l'ensemble d'un EPCI — le
  contour administratif déjà connu suffit à la localiser.
- "zone_specifique" : la règle ne s'applique qu'à une zone réglementaire
  précise (ex. une zone "UA", un secteur identifié) qui n'a pas de contour
  automatiquement disponible et devra être tracée manuellement.
Si le passage ne précise aucune limite spatiale propre (silence total sur la
portée), pars du principe que la règle s'applique à l'ensemble du document
("administrative") plutôt que de la classer par défaut en "zone_specifique".

Contexte avant : {contexte_avant}
PASSAGE À ANALYSER : {passage_texte}
Contexte après : {contexte_apres}

Le passage a été extrait automatiquement d'un PDF et son découpage en blocs
n'est pas toujours fiable — utilise le contexte avant/après si la règle y
déborde, et pour juger du périmètre diagBruit et du cas "simple renvoi".

Si retenu=true, remplis extrait_significatif : une citation verbatim (copiée
exactement, sans reformulation), depuis le contexte avant, le passage et/ou
le contexte après ci-dessus, qui isole le plus précisément possible la règle.
Si retenu=false, mets extrait_significatif à null."""

    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=800,
        thinking={"type": "disabled"},
        output_config={"format": {"type": "json_schema", "schema": SCHEMA_CLASSIFICATION}},
        messages=[{"role": "user", "content": prompt}],
    )
    texte_reponse = next(bloc.text for bloc in response.content if bloc.type == "text")
    donnees = json.loads(texte_reponse)

    # Vérification de la citation : on ne fait confiance à extrait_significatif
    # que s'il s'agit bien d'un extrait verbatim du texte fourni — sinon repli
    # sur le découpage mécanique de la phase 3 (extrait_repli).
    if donnees["retenu"] and donnees["extrait_significatif"]:
        texte_source = normaliser_espaces(f"{contexte_avant} {passage_texte} {contexte_apres}")
        if normaliser_espaces(donnees["extrait_significatif"]) not in texte_source:
            donnees["extrait_significatif"] = extrait_repli

    return donnees
```

Une clé API Anthropic (`ANTHROPIC_API_KEY`) est nécessaire, à créer sur la Console Anthropic. Elle est stockée dans un fichier `.env` local à la racine de `poc-urbanisme-plu/` (non versionné, à l'image de `output/`), lu via `python-dotenv` — l'étape 1 n'avait pas eu besoin de ce mécanisme, ses APIs (geo.api.gouv.fr, GPU) étant publiques et sans authentification.

## Gestion des erreurs

Reprise à l'identique du pattern de l'étape 1 : `tenacity` enveloppe chaque appel externe (résolution de pièce, téléchargement/extraction, appel de classification) avec tentatives et délai progressif. Un échec persistant ne bloque pas le traitement — la ligne concernée part dans `etape2_{dept}_erreurs.csv` (phase concernée, type d'erreur, contenu brut disponible pour investigation) et le reste du département continue d'être traité. L'usage des structured outputs en phase 4 limite le risque de réponse JSON mal formée aux cas de refus de sécurité du modèle ou de troncature `max_tokens` — les deux sont détectés explicitement et traités comme un échec isolé, au même titre que les autres.

## Valeurs des champs du CSV de synthèse (`etape2_{dept}.csv`)

Les colonnes elles-mêmes sont définies dans `etape-2-analyse-documents-urbanisme-diagbruit.md` (phase 5) ; cette section documente les valeurs possibles de chacune et leur origine dans le code.

Colonnes dans l'ordre où elles apparaissent dans le CSV (`COLONNES_SYNTHESE` de `synthese.py`) ; `id_gpu`, `lien_web_document`, `zone_reglementaire_mentionnee` et `date_traitement` ne figurent pas ci-dessous, leur contenu (identifiant, URL, texte libre, date) ne nécessitant pas de table de valeurs.

| Colonne | Valeurs possibles | Origine / remarque |
|---|---|---|
| `id_occurrence` | `{compteur}_{nom_fichier}`, ex. `1_246700488_reglement_20260206.pdf` | `synthese.py` (phase 5). Compteur qui repart à 1 pour chaque pièce (`nom_fichier`, unique dans le département) — jamais vide pour une occurrence réelle. Vide uniquement sur les lignes "aucune occurrence trouvée". |
| `type_piece_source` | `règlement écrit` / `OAP` / `PADD` / `PSMV` | Déduit du nom de fichier par `resolution_pieces.py` (phase 1) ; `PSMV` s'applique au règlement d'un document dont la `nature_document` (étape 1) vaut `PSMV`, plutôt que `règlement écrit`. |
| `reference_type` | `alinea` / `page` | `filtrage_lexical.py` (phase 3). `alinea` dès qu'un "Article N" (et éventuellement un "alinéa N") a été repéré en tête de paragraphe avant le passage ; à défaut, repli sur `page`. |
| `reference_precise` | Texte libre, ex. `"Article 15, alinéa 6"`, `"Article 11"`, `"page 24"` | Idem — jamais une citation du code de l'urbanisme (voir "Filtrage lexical (Phase 3)" ci-dessus). |
| `extrait_significatif` | Texte libre | `classification.py` (phase 4) : citation verbatim choisie par le modèle dans le passage et son contexte immédiat (voir "Appel de classification (Phase 4)"), sans son contexte. Vide si `retenu=false` ou sur une ligne "aucune occurrence trouvée". |
| `contexte_documentaire` | Texte libre | `synthese.py` (phase 5) : concaténation, dans l'ordre de lecture du document, de `contexte_avant` + `extrait_significatif` + `contexte_apres`. Vide sur une ligne "aucune occurrence trouvée". |
| `confiance_extrait` | `faible` / `moyenne` / `forte` / `totale` / *(vide)* | Renvoyé par le modèle en phase 4 : à quel point la citation qu'il a choisie (`extrait_significatif`, incluse dans `contexte_documentaire`) exprime clairement et de façon autonome la règle, sans qu'il faille deviner du contexte. `faible` peut aussi signaler une règle hors périmètre diagBruit (limitée à un projet d'infrastructure de transport, voir "Appel de classification (Phase 4)") — les deux raisons sont à distinguer en lisant `justification`. Vide si `retenu=false` ou sur une ligne "aucune occurrence trouvée". |
| `justification` | Texte libre | Le raisonnement du modèle derrière `retenu` et `confiance_extrait` — nécessaire pour comprendre *pourquoi* le modèle a tranché comme il l'a fait sur un cas litigieux (ex. renvoi simple vs règle autonome). Toujours renseigné, y compris quand `retenu=false`. Vide sur une ligne "aucune occurrence trouvée". |
| `nature_occurrence` | `prescription` / `recommandation` / *(vide)* | Renvoyé par le modèle en phase 4. Vide uniquement sur les lignes `statut_verification = "aucune occurrence trouvée"`. |
| `nature_juridique_piece` | `opposable en conformité` / `opposable en compatibilité` / `non opposable` | Déduit mécaniquement de `type_piece_source` par `synthese.py` (phase 5) : règlement (PLU/PLUi/POS/CC comme PSMV) → conformité ; OAP → compatibilité ; PADD → non opposable. |
| `nature_sonore_zone` | `lutte_bruit_existant` / `preservation_zone_calme` / `autre` / *(vide)* | Renvoyé par le modèle en phase 4. Vide dans les mêmes conditions que `nature_occurrence`. |
| `portee_geometrique` | `administrative` / `zone_specifique` / *(vide)* | **(ajouté le 17/08/2026)** Renvoyé par le modèle en phase 4. Vide dans les mêmes conditions que `nature_occurrence`. Exploité directement par `preparer_geometries.py` à l'étape 4 pour orienter la ligne vers la géométrie automatique ou vers le tracé manuel — voir `etape-4-conception-technique.md`. |
| `statut_verification` | `validé` / `à vérifier (renvoi CSV-PEB potentiel)` / `aucune occurrence trouvée` | `synthese.py` (phase 5) : `à vérifier...` quand le passage porte le tag d'exclusion lexicale (phase 3) malgré un `retenu=true` en phase 4 ; `aucune occurrence trouvée` quand une pièce extraite avec succès n'a produit aucune occurrence retenue. |
| `ocr_utilise` | `True` / `False` | `extraction_texte.py` (phase 2). |
| `ocr_confiance` | `élevée` / `moyenne` / `faible` / *(vide)* | Idem, vide si `ocr_utilise` est `False`. |

## Dépendances retenues (en plus de celles de l'étape 1)

- `pdfplumber` — extraction de texte PDF page par page.
- `pytesseract` + `pdf2image` — OCR de secours pour les PDF scannés. Nécessitent chacun un binaire externe installé hors pip (Tesseract OCR, Poppler) — voir "Extraction de texte (Phase 2)" pour les sources et l'installation.
- `anthropic` — SDK officiel, appel de classification en phase 4 avec structured outputs.
- `python-dotenv` — chargement de `ANTHROPIC_API_KEY` depuis un fichier `.env` local non versionné.
- `tenacity` — tentatives avec délai progressif, réutilisée à l'identique.

## Prochaine étape

Délimitation géométrique des zones et rédaction des messages (étapes 3, 4 et 5 du plan global), à partir des occurrences produites par `etape2_{dept}.csv`.
