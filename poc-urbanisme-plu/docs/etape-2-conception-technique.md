# Étape 2 — Conception technique : analyse des documents d'urbanisme pour repérer les règles liées au bruit
 
*Document de cadrage technique — décisions issues des échanges du 11-12/08/2026, faisant suite à `etape-2-analyse-documents-urbanisme-diagbruit.md` et à `etape-1-conception-technique.md`.*
 
## Posture
 
Ce module reste un sous-dossier du même POC que l'étape 1, sous la même posture générale (voir `etape-1-conception-technique.md`) : code écrit par un non-développeur, isolé du reste du produit, préuve de concept plutôt que composant prêt à intégrer.
 
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
 
## Extraction de texte (Phase 2)
 
`pdfplumber` extrait le texte PDF page par page. Un score de confiance sur le texte extrait (densité de caractères reconnus, présence de mots courants) détermine s'il s'agit d'un scan ; le cas échéant, `pytesseract` + `pdf2image` prennent le relais pour l'OCR, et le score de confiance renvoyé par l'OCR est traduit dans le champ `ocr_confiance` (élevée / moyenne / faible).
 
## Filtrage lexical (Phase 3)
 
Deux recherches textuelles simples (pas besoin de bibliothèque dédiée) sur le texte extrait, paragraphe par paragraphe : la liste d'inclusion retient un passage, la liste d'exclusion pose un tag sur les passages retenus qui contiennent en plus un terme évoquant classement sonore/PEB. Aucune suppression n'a lieu à ce stade — l'arbitrage revient à la phase de classification.
 
## Appel de classification (Phase 4)
 
Un appel à l'API Anthropic (`/v1/messages`, modèle `claude-sonnet-4-6`) par passage retenu, plutôt qu'un traitement par lot : un échec ou une réponse mal formée ne fait perdre qu'une ligne, jamais un document entier, et chaque ligne du CSV de sortie reste reliée à un appel identifiable individuellement.
 
Le prompt transmet le passage, son contexte immédiat, le type de pièce source et le tag d'exclusion éventuel ; il demande une réponse strictement JSON :
 
```python
import requests
import json
import os
 
API_KEY = os.environ["ANTHROPIC_API_KEY"]
 
def classifier_passage(passage_texte, contexte_avant, contexte_apres, type_piece, tag_exclusion):
    prompt = f"""Tu analyses un extrait d'un document d'urbanisme français ({type_piece})
pour repérer des règles autonomes liées au bruit (hors classement sonore des voies
et plan d'exposition au bruit, qui sont déjà traités ailleurs).
 
Contexte avant : {contexte_avant}
PASSAGE À ANALYSER : {passage_texte}
Contexte après : {contexte_apres}
 
Indice préalable : ce passage a été taggé "{tag_exclusion}" par un filtre lexical
(présence possible d'un renvoi au classement sonore/PEB). Vérifie si, malgré ce tag,
le passage contient une prescription ou recommandation autonome liée au bruit.
 
Réponds UNIQUEMENT avec un objet JSON, sans aucun texte avant ou après :
{{
  "retenu": true ou false,
  "nature_occurrence": "prescription" ou "recommandation" ou null,
  "nature_sonore_zone": "lutte_bruit_existant" ou "preservation_zone_calme" ou "autre" ou null,
  "zone_reglementaire_mentionnee": "texte libre ou null",
  "justification": "une phrase expliquant la décision"
}}"""
 
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 500,
            "messages": [{"role": "user", "content": prompt}]
        }
    )
    response.raise_for_status()
    texte_reponse = response.json()["content"][0]["text"]
    return json.loads(texte_reponse)
```
 
Une clé API Anthropic (`ANTHROPIC_API_KEY`) est nécessaire, à créer sur la Console Anthropic.
 
## Gestion des erreurs
 
Reprise à l'identique du pattern de l'étape 1 : `tenacity` enveloppe chaque appel externe (résolution de pièce, appel de classification) avec tentatives et délai progressif. Un échec persistant, ou une réponse JSON mal formée en phase 4, ne bloque pas le traitement — la ligne concernée part dans `etape2_{dept}_erreurs.csv` (phase concernée, type d'erreur, contenu brut disponible pour investigation) et le reste du département continue d'être traité.
 
## Dépendances retenues (en plus de celles de l'étape 1)
 
- `pdfplumber` — extraction de texte PDF page par page.
- `pytesseract` + `pdf2image` — OCR de secours pour les PDF scannés.
- `requests` — appel à l'API Anthropic, comme pour les appels GPU de l'étape 1.
- `tenacity` — tentatives avec délai progressif, réutilisée à l'identique.
## Prochaine étape
 
Implémentation de `resolution_pieces.py` et `extraction_texte.py`, qui ne dépendent d'aucune décision encore en suspens — développables et testables avant même d'avoir figé les gabarits de message de l'étape 6. `classification.py` suit une fois qu'un premier lot de passages filtrés est disponible pour ajuster le prompt sur des cas réels.