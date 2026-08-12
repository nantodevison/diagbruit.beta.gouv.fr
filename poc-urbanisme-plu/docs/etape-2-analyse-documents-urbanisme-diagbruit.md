# Étape 2 — Analyse des documents d'urbanisme pour repérer les règles liées au bruit
 
*Document de cadrage détaillé de l'étape 2 du plan d'automatisation des règles PLU de diagBruit (voir `plan-automatisation-regles-plu-diagbruit.md`). Suite de `etape-1-identification-documents-urbanisme-diagbruit.md`. Version issue des échanges du 11-12/08/2026.*
 
**Entrée** : le CSV `etape1_{dept}.csv` produit par l'étape 1. Seules les lignes dont le `statut` vaut **`document trouvé`** ou **`PSMV additionnel`** sont traitées ici — elles seules portent un `id_gpu` exploitable.
 
Les lignes `RNU confirmé` et `trou de couverture` ne passent pas par cette étape : l'information nécessaire à leur message final existe déjà entièrement dans leur `statut` de l'étape 1. Elles seront traitées directement à l'étape 6 (mise en forme), avec deux gabarits de message distincts — RNU (situation normale attendue, régime national qui s'applique) et trou de couverture (anomalie de données à signaler différemment). La rédaction de ces gabarits reste à faire.
 
## Sources écartées de l'analyse
 
La couche structurée "prescriptions" du GPU (`prescription-surf/lin/pct`) a été envisagée en complément de la lecture des règlements (amélioration A du plan global), puis vérifiée directement sur les tables de codes du Géoportail de l'urbanisme (nomenclatures `PrescriptionSUrbaType` et `PrescriptionLUrbaType`) pour les familles **PLU, PLUi et PSMV** (standards `cnig_PLU_2025`, `cnig_PLUi_2025`, `cnig_PSMV_2025`) : aucune catégorie liée au bruit, au son ou à l'acoustique parmi la totalité des libellés, quelle que soit la famille de document. Cette source est donc **écartée du pipeline d'analyse** — chaque document d'urbanisme, quel que soit son type (règlement écrit, OAP, PADD, PSMV), s'analyse uniquement à partir de son texte.
 
## Phase 1 — Résolution des pièces du document
 
À partir de l'`id_gpu`, appel à `document-details` de l'API du GPU pour obtenir la liste des pièces qui composent le document (règlement écrit, OAP, PADD, PSMV le cas échéant) et l'URL de chaque pièce.
 
## Phase 2 — Extraction du texte
 
Chaque PDF est extrait **page par page**. Une numérotation d'article ou d'alinéa est recherchée dans le texte extrait ; si elle est identifiable, elle sert de référence, sinon la référence retombe sur le numéro de page — les documents d'urbanisme n'ayant pas de structure normalisée d'une commune à l'autre, ce repère à deux niveaux évite d'afficher une précision qu'on ne peut pas garantir partout.
 
Quand un PDF s'avère être un scan (texte natif quasi vide), un passage par OCR prend le relais. Le niveau de confiance de cet OCR est conservé et traduit en trois niveaux (élevée / moyenne / faible), pour permettre de prioriser la vérification humaine sur les scans les moins fiables.
 
## Phase 3 — Repérage des occurrences
 
Un premier passage lexical repère, dans le texte extrait, les passages contenant l'un des termes suivants :
 
**Mots-clés d'inclusion** : `bruit`, `nuisances sonores`, `isolation acoustique`, `acoustique`, `sonore`, `calme`, `zone calme`
 
Un second passage tague, parmi les passages retenus, ceux qui contiennent également un terme évoquant le classement sonore des voies ou le plan d'exposition au bruit — pour lesquels diagBruit dispose déjà d'un traitement dédié et qu'on ne veut pas dupliquer :
 
**Mots-clés d'exclusion (tag, pas de suppression)** : `classement sonore`, `plan d'exposition au bruit`, `CSV` *(Classement Sonore des Voies)*, `PEB`, `L.571-10`
 
Ce tag ne supprime pas le passage : un règlement peut renvoyer au classement sonore *et*, dans le même paragraphe, ajouter une prescription autonome (ex. une exigence d'isolation renforcée). L'arbitrage final est laissé à la phase suivante, qui dispose du contexte nécessaire pour trancher.
 
## Phase 4 — Classification
 
Chaque passage retenu en phase 3 est analysé pour déterminer :
- s'il constitue une règle autonome liée au bruit, ou seulement un renvoi au classement sonore/PEB (auquel cas il est écarté malgré sa présence en phase 3) ;
- sa **nature** : prescription ou recommandation ;
- sa **nature sonore** : lutte contre une nuisance existante, ou préservation d'une zone calme ;
- la **zone réglementaire** concernée, quand le texte la précise (nécessaire pour l'étape 3 du plan global, qui délimitera géométriquement les zones à cette granularité plutôt qu'à celle de la commune).
## Phase 5 — Synthèse CSV
 
| Colonne | Détail |
|---|---|
| `id_gpu` | clé de jointure avec `etape1_{dept}.csv` |
| `id_occurrence` | identifiant unique de la ligne |
| `type_piece_source` | règlement écrit / OAP / PADD / PSMV |
| `lien_web_document` | URL du PDF source |
| `reference_type` | `alinea` ou `page` |
| `reference_precise` | ex. "Article 11, alinéa 3" ou "page 24" |
| `zone_reglementaire_mentionnee` | ex. "UA", "ensemble du zonage", "non précisé" |
| `extrait_occurrence` | courte citation/paraphrase du passage repéré |
| `nature_occurrence` | prescription / recommandation |
| `nature_juridique_piece` | opposable en conformité / en compatibilité / non opposable — déduit du `type_piece_source` |
| `nature_sonore_zone` | lutte contre bruit existant / préservation zone calme / autre |
| `statut_verification` | validé / à vérifier (renvoi CSV-PEB potentiel) / aucune occurrence trouvée |
| `ocr_utilise` | booléen |
| `ocr_confiance` | élevée / moyenne / faible — vide si `ocr_utilise` est faux |
| `date_traitement` | date d'exécution du run |
 
Quand une pièce n'a produit aucune occurrence, une ligne est tout de même écrite pour elle (`id_gpu`, `lien_web_document` renseignés, colonnes d'analyse vides, `statut_verification = "aucune occurrence trouvée"`) — pour que le CSV reste la source de vérité unique et traçable, sans message caché ailleurs dans le processus.
 
## Gestion des erreurs
 
Comme à l'étape 1, aucun échec isolé (résolution d'une pièce, extraction d'un PDF, appel de classification) n'interrompt le traitement du reste du département. Chaque erreur est empilée dans `etape2_{dept}_erreurs.csv`, avec la phase concernée et le type d'erreur, après quelques tentatives avec délai progressif.
 
## Prochaine étape
 
Conception technique de la mise en œuvre (architecture du code, bibliothèques, format exact des appels et des fichiers).