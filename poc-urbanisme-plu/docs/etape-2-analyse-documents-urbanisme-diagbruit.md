# Étape 2 — Analyse des documents d'urbanisme pour repérer les règles liées au bruit

*Document de cadrage détaillé de l'étape 2 du plan d'automatisation des règles PLU de diagBruit (voir `plan-automatisation-regles-plu-diagbruit.md`). Suite de `etape-1-identification-documents-urbanisme-diagbruit.md`.*

**Entrée** : le CSV `etape1_{dept}.csv` produit par l'étape 1. Seules les lignes dont le `statut` vaut **`document trouvé`** ou **`PSMV additionnel`** sont traitées ici — elles seules portent un `id_gpu` exploitable.

Les lignes `RNU confirmé` et `trou de couverture` ne passent pas par les phases d'analyse de cette étape : il n'y a pas de document PDF à lire (pas de règlement pour une commune au RNU, pas de document trouvé du tout pour un trou de couverture).

Cela ne signifie pas que ces lignes restent en dehors du pipeline jusqu'à l'étape 6 : c'est l'étape 3 (`synthese_finale.py`) qui les réintègre directement dans `etape3_{dept}.csv`, sous forme de lignes de synthèse construites depuis `etape1_{dept}.csv` — au même titre que les documents non significatifs — pour qu'elles bénéficient d'une géométrie dès l'étape 4 (voir `etape-3-validation-manuelle.md`, section "RNU et trou de couverture : réintégration dans le pipeline"). Le RNU en particulier porte une règle de fond bien réelle, ce n'est pas une absence de donnée : l'article R.111-2 du code de l'urbanisme permet à l'autorité compétente de refuser un permis de construire, ou de le conditionner à des prescriptions spéciales, si le projet porte atteinte à la salubrité ou à la sécurité publique — la jurisprudence y range explicitement les nuisances sonores. Une commune au RNU n'est donc pas "sans règle" : elle est sous un régime déjà écrit une fois pour toutes au niveau national, plutôt que dans un document local à aller lire.

Un quatrième cas, distinct de ces deux-là, apparaît en Phase 1 (ajouté le 26/08/2026) : un `id_gpu` au statut `document trouvé` mais dont la résolution en pièces exploitables échoue totalement (voir "Phase 1" ci-dessous) — le document existe et est identifié, mais rien n'a pu en être lu. Il est lui aussi réintégré à l'étape 3, sous `nature_zone = "document_non_exploitable"`, distinct de `document_non_significatif` (document lu mais ne mentionnant rien sur le bruit) — voir `etape-3-validation-manuelle.md`, section "Document non exploitable : réintégration dans le pipeline".

## Sources écartées de l'analyse

La couche structurée "prescriptions" du GPU (`prescription-surf/lin/pct`) a été envisagée en complément de la lecture des règlements (amélioration A du plan global). Les tables de codes du Géoportail de l'urbanisme (nomenclatures `PrescriptionSUrbaType` et `PrescriptionLUrbaType`, standards `cnig_PLU_2025`, `cnig_PLUi_2025`, `cnig_PSMV_2025`) ne comportent aucune catégorie liée au bruit, au son ou à l'acoustique, pour aucune des familles de document (PLU, PLUi, PSMV). Cette source est donc **écartée du pipeline d'analyse** — chaque document d'urbanisme, quel que soit son type (règlement écrit, OAP, PADD, PSMV), s'analyse uniquement à partir de son texte.

## Phase 1 — Résolution des pièces du document

À partir de l'`id_gpu`, l'API `document-details` du Géoportail de l'urbanisme (GPU) est interrogée pour obtenir la liste des pièces qui composent le document et l'URL de chaque pièce. Un même document (par exemple un PLUi intercommunal) n'est résolu qu'une seule fois, quel que soit le nombre de communes qu'il couvre dans `etape1_{dept}.csv`.

Seules les pièces à vocation réglementaire sont retenues pour l'analyse — règlement écrit, orientations d'aménagement et de programmation (OAP), projet d'aménagement et de développement durables (PADD), et le règlement d'un PSMV le cas échéant. Les autres pièces d'un document (rapport de présentation, plans graphiques, annexes de servitudes, pièces de procédure) sont hors périmètre de cette analyse.

Constaté sur le 067 (ajouté le 26/08/2026) : pour environ 30% des documents, `document-details` renvoie un `writingMaterials` vide alors que le document a bien un règlement/PADD/OAP — ces fichiers ne sont accessibles que dans l'archive ZIP complète du document (`archiveUrl`), sans indexation fichier par fichier côté GPU. Dans ce cas, l'archive est téléchargée une fois et seules les pièces exploitables qu'elle contient sont extraites sur disque (voir `etape-2-conception-technique.md`, "Repli sur l'archive complète"). Quand même ce repli ne produit aucune pièce exploitable (ex. une carte communale qui n'a qu'un règlement graphique, hors périmètre), le document part en erreur documentée plutôt que de disparaître silencieusement — voir "Gestion des erreurs" plus bas.

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

- s'il constitue une **règle autonome** liée au bruit, dans le périmètre de diagBruit : les projets de construction de bâtiments et les projets d'aménagement urbain.
  - Une règle qui ne concerne que la réalisation d'une infrastructure de transport elle-même (voirie, voie ferrée...), sans rapport avec des bâtiments ou l'urbanisation à proximité, est tout de même retenue, mais signalée avec une confiance réduite sur la citation associée (voir plus bas).
  - Le classement sonore des voies et le plan d'exposition au bruit (PEB) d'un aéroport sont déjà traités ailleurs par diagBruit : la mention d'un secteur affecté par le bruit de ces infrastructures classées n'est donc pas automatiquement une règle autonome. Deux cas sont distingués : un **simple renvoi** (écarté) quand le passage se contente de rappeler que l'isolement acoustique standard prévu par l'arrêté préfectoral (classement sonore) ou par le PEB s'applique dans ce secteur, sans rien ajouter de propre au document d'urbanisme ; et une **règle autonome** (retenue) quand le secteur classé sert seulement de repère géographique à une règle différente de l'isolement standard, ou à une exigence d'isolement qui va au-delà de celle prévue par l'arrêté/le PEB ;
- sa **nature** : prescription ou recommandation ;
- sa **nature sonore** : lutte contre une nuisance existante, ou préservation d'une zone calme ;
- la **zone réglementaire** concernée, quand le texte la précise (texte libre — ex. "UA", "ensemble du zonage", "non précisé") ;
- la **portée géométrique** de la règle : **administrative** (la règle s'applique à l'ensemble du zonage, de la commune ou de l'EPCI couvert par le document — une géométrie de contour administratif suffira à l'étape 4) ou **zone spécifique** (la règle ne concerne qu'une zone réglementaire précise — ex. "UA" — qui nécessitera un tracé manuel dédié, faute de source automatique fiable). Ce champ est distinct de la zone réglementaire mentionnée elle-même : l'un dit *quelle* zone est citée dans le texte (`zone_reglementaire_mentionnee`, texte libre, informatif), l'autre dit *quel processus de géométrie* appliquer (`portee_geometrique`, valeur contrôlée, exploitée directement par le code de l'étape 4) ;
- la **citation la plus pertinente** pour illustrer la règle repérée : le passage retenu est transmis avec son contexte immédiat (le texte qui précède et qui suit dans le document), et c'est le modèle qui choisit lui-même la citation exacte — mot pour mot, sans reformulation — qui isole le mieux la règle, avec un niveau de confiance sur la clarté de cette citation ;
- le **raisonnement** qui justifie ces choix, notamment laquelle des deux situations explique une confiance réduite (citation peu claire et fragmentée, ou règle limitée à l'infrastructure de transport).

## Phase 5 — Synthèse CSV

| Colonne | Détail |
|---|---|
| `id_gpu` | clé de jointure avec `etape1_{dept}.csv` |
| `id_occurrence` | identifiant unique de la ligne, construit à partir du nom du fichier source et d'un compteur qui repart à 1 pour chaque pièce |
| `type_piece_source` | règlement écrit / OAP / PADD / PSMV |
| `lien_web_document` | URL du PDF source |
| `reference_type` | `alinea` ou `page` |
| `reference_precise` | ex. "Article 11, alinéa 3" ou "page 24" |
| `zone_reglementaire_mentionnee` | ex. "UA", "ensemble du zonage", "non précisé" |
| `portee_geometrique` | `administrative` ou `zone_specifique` — détermine à l'étape 4 si une géométrie automatique (contour administratif) suffit, ou si un tracé manuel est nécessaire |
| `extrait_significatif` | citation verbatim choisie par le modèle, sans son contexte — pour un survol rapide |
| `contexte_documentaire` | la même citation, entourée cette fois de son contexte immédiat (juste avant / juste après), concaténés dans l'ordre de lecture du document — pour vérifier en contexte sans ouvrir le PDF source |
| `confiance_extrait` | faible / moyenne / forte / totale — confiance du modèle dans la clarté de la citation retenue ; peut aussi signaler une règle hors périmètre diagBruit (limitée à l'infrastructure de transport) — la raison précise est à lire dans `justification` |
| `justification` | texte libre : le raisonnement du modèle derrière `retenu` et `confiance_extrait` |
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

Les erreurs de phase 1 (`type_erreur` = `aucun_fichier`, `appel_gpu` ou `archive_indisponible`) ne sont pas de simples erreurs à corriger et oublier : l'étape 3 les relit pour réintégrer chaque `id_gpu` concerné dans `etape3_{dept}.csv` sous `nature_zone = "document_non_exploitable"` (voir plus haut et `etape-3-validation-manuelle.md`). `etape2_{dept}_erreurs.csv` est donc, depuis le 26/08/2026, une entrée directe de l'étape 3, pas seulement un fichier d'audit.

## Prochaine étape

Validation manuelle des occurrences (étape 3), qui réintègre également les communes RNU et les trous de couverture, puis délimitation géométrique des zones (étape 4) à partir du CSV produit par l'étape 3.
