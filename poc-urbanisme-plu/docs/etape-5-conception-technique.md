# Étape 5 — Conception technique : rédaction des messages

*Document de cadrage technique, faisant suite à `etape-5-redaction-messages-diagbruit.md` et à `etape-4-conception-technique.md`. Version issue des échanges du 19/08/2026.*

## Posture

Même sous-dossier du même POC que les étapes 1 à 4 (voir `etape-1-conception-technique.md`) : code écrit par un non-développeur, isolé du reste du produit, preuve de concept plutôt que composant prêt à intégrer.

Écart assumé par rapport aux étapes précédentes : c'est la première étape qui **génère** du contenu nouveau (un message) plutôt que d'extraire, classifier ou géoréférencer du contenu existant. Le risque n'est plus seulement "une donnée mal classée" mais "une affirmation incorrecte présentée à l'utilisateur final de diagBruit" — d'où la validation humaine systématique décrite dans le document de cadrage général, plus stricte qu'un simple contrôle qualité automatique.

## Architecture des dossiers

```
poc-urbanisme-plu/
├── etape4_geometries/                     # existant
├── etape5_redaction_messages/
│   ├── __init__.py                        # vide, comme les modules précédents
│   ├── controle_similarite.py             # Phase 1 — auto : garde-fou de cohérence géométrique
│   ├── ton_de_voix.py                     # aide partagée : texte des 5 piliers, à joindre aux prompts LLM
│   ├── messages_fixes.py                  # aide partagée : les 3 textes fixes (rnu / document_non_significatif / trou_de_couverture)
│   ├── preparer_messages.py               # Phase 2 — auto (LLM) : génère message_occurrence et message_synthese_llm
│   ├── outil_validation.html              # Phase 3 — manuel : relecture/correction, sur le modèle de l'étape 3
│   ├── synthese_messages.py               # Phase 4 — auto : reprend l'export de la Phase 3, écrit etape5_{dept}.gpkg
│   └── verifier_orthographe.py            # auto, après la Phase 4 : enrichit etape5_{dept}.gpkg de _validation_orthographe
└── output/
    ├── etape4_{dept}.gpkg
    ├── etape5_{dept}_avertissements.csv           # Phase 1 — paires géométriques suspectes, si non vide
    ├── etape5_{dept}_a_completer.gpkg             # Phase 2 — synthèses natives du LLM (avec géométrie) ; jamais retouché
    ├── etape5_{dept}_syntheses.csv                # Phase 2 — miroir CSV de la table de synthèse (sans géométrie), pour la Phase 3
    ├── etape5_{dept}_occurrences.csv              # Phase 2 — messages individuels + citations sources, pour la Phase 3
    ├── etape5_{dept}_documents_par_synthese.csv   # Phase 2 — un document par ligne, clé étrangère vers la synthèse
    ├── etape5_{dept}_erreurs.csv                  # Phase 2 — échecs isolés d'appel LLM ou de jointure vers etape3, si non vide
    ├── etape5_export_occurrences_{horodatage}.csv # Phase 3 — export(s) de outil_validation.html, le plus récent fait foi
    ├── etape5_export_syntheses_{horodatage}.csv   # Phase 3 — idem, requis pour la Phase 4
    └── etape5_{dept}.gpkg                         # Phase 4 — contrat pour l'étape 6 (couche unique "messages") ;
                                                    # réécrit en place par verifier_orthographe.py (colonne en plus)
```

Comme les étapes 3 et 4, l'étape 5 n'a pas de `main.py` unique : la relecture humaine (Phase 3) s'intercale entre deux phases automatisées. Usage, depuis `poc-urbanisme-plu/` :

```
python -m etape5_redaction_messages.controle_similarite --dept 033
# consulter etape5_033_avertissements.csv si présent (informatif, ne bloque rien)
python -m etape5_redaction_messages.preparer_messages --dept 033
# ouvrir outil_validation.html dans un navigateur, charger etape5_033_occurrences.csv
# et/ou etape5_033_syntheses.csv, corriger si besoin, exporter (Phase 3)
python -m etape5_redaction_messages.synthese_messages --dept 033
python -m etape5_redaction_messages.verifier_orthographe --dept 033
# ouvrir etape5_033.gpkg dans QGIS, filtrer sur "_validation_orthographe" != ''
```

**À relancer dans cet ordre à chaque nouvelle correction** : `verifier_orthographe.py` réécrit `etape5_{dept}.gpkg` en place pour y ajouter une colonne — si `synthese_messages.py` est relancé ensuite (nouvel export corrigé), il réécrit le fichier en entier sans connaître cette colonne, qui disparaît. Il faut donc systématiquement relancer `verifier_orthographe.py` après toute nouvelle exécution de `synthese_messages.py` — discipline opérationnelle plutôt que verrou technique, même famille de contrainte que l'ordre déjà documenté pour l'étape 4 (`preparer_geometries.py` jamais relancé après le début de la Phase 2).

## Phase 1 — Garde-fou de cohérence géométrique (`controle_similarite.py`)

Lit `etape4_{dept}.gpkg` (couche `geometries`). Filtre aux lignes `nature_zone == "occurrence_locale"`, regroupées par `nature_sonore_zone` (deux occurrences de `nature_sonore_zone` différente ne sont de toute façon jamais éligibles à une fusion — inutile de les comparer). Exclut les paires déjà reliées par `fusionne_avec_id_gpu`/`fusionne_avec_id_occurrence`.

Pour chaque paire restante, filtrée au préalable sur le chevauchement de leurs *bounding box* (évite de calculer une distance de Hausdorff, plus coûteuse, sur des paires manifestement sans rapport) :
- **aire** : reprojection en CRS métrique (Lambert-93/EPSG:2154 pour la métropole ; projection adaptée pour un DROM le cas échéant), puis comparaison des deux aires — signalée si l'écart dépasse 10 % ;
- **forme** : distance de Hausdorff entre les deux contours (dans le même CRS métrique), normalisée par une longueur caractéristique de la géométrie (ex. diagonale de la bounding box, ou racine carrée de l'aire) pour obtenir un score comparable indépendamment de la taille absolue de la zone. Hausdorff plutôt que Fréchet : indépendant de l'ordre/du sens de parcours des points du contour, donc plus robuste pour comparer deux polygones tracés indépendamment dans QGIS. Seuil numérique non encore fixé, à définir empiriquement.

Une paire qui dépasse les deux seuils (aire et forme) est écrite dans `etape5_{dept}_avertissements.csv` — jamais bloquant, jamais une correction automatique : la fusion reste une décision humaine (voir `etape-4-conception-technique.md`, "Mécanisme de fusion"), ce script se contente de signaler les cas qui méritent un second regard.

## Phase 2 — Génération des messages (`preparer_messages.py`)

Lit `etape4_{dept}.gpkg`. Pour chaque géométrie finale (un meneur et ses éventuels membres, ou une occurrence isolée) :

**`nature_zone` différent de `occurrence_locale`** → le message fixe correspondant (`messages_fixes.py`, voir `etape-5-redaction-messages-diagbruit.md`, "Messages fixes"), aucun appel LLM. Écrit directement en `message_synthese_llm` dans `etape5_{dept}_a_completer.gpkg`/`etape5_{dept}_syntheses.csv`, `message_occurrence` non applicable — ces lignes n'ont d'ailleurs pas d'`id_occurrence`, c'est ce qui permet à `outil_validation.html` de les exclure automatiquement du mode "Message fusion" (voir Phase 3 ci-dessous), cohérent avec leur exclusion déjà actée du circuit de validation humaine.

**`nature_zone == "occurrence_locale"`** :
1. Reconstruction du groupe : toutes les lignes de `etape4_{dept}.gpkg` dont `fusionne_avec_id_occurrence` pointe vers le meneur, plus le meneur lui-même (ou l'occurrence seule si elle n'a ni meneur ni membre).
2. Pour chaque occurrence du groupe : jointure vers `etape3_{dept}.csv` sur `id_gpu` + `id_occurrence`, pour récupérer `extrait_significatif`, `contexte_documentaire`, `nature_occurrence`. Un appel LLM produit `message_occurrence` à partir de ces champs, de `justification`, `zone_reglementaire_mentionnee`, `type_piece_source`, `reference_precise`, et du texte du ton de voix (`ton_de_voix.py`). Écrit dans `etape5_{dept}_occurrences.csv` (une ligne par occurrence, y compris pour un groupe d'une seule occurrence).
3. Si le groupe compte plus d'une occurrence : un second appel LLM combine les `message_occurrence` du groupe (jamais une simple concaténation, voir "Ton de voix" dans le document de cadrage général) en un unique `message_synthese`. Si le groupe compte une seule occurrence, `message_synthese` reprend directement `message_occurrence` — pas d'appel LLM redondant.

**Échec isolé au sein d'un groupe** : l'échec d'une occurrence (jointure étape3 introuvable, appel LLM en échec) n'exclut que cette occurrence, jamais le reste du groupe — la synthèse se construit avec les `message_occurrence` restants. Si *toutes* les occurrences d'un groupe échouent, le groupe entier est exclu de `etape5_{dept}_a_completer.gpkg` pour cette exécution (rien d'exploitable à synthétiser), chaque échec individuel restant tracé dans `etape5_{dept}_erreurs.csv`.

**Miroir CSV (ajouté le 20/08/2026)** : en plus de `etape5_{dept}_a_completer.gpkg`, la table de synthèse (sans la colonne géométrie) est aussi écrite dans `etape5_{dept}_syntheses.csv` — un navigateur ne sait pas lire un GeoPackage nativement, alors qu'un CSV se parse sans dépendance en JavaScript (voir "Phase 3 — Validation humaine" ci-dessous). Les deux fichiers portent la même donnée, le gpkg pour la couche `geometries`/le SIG, le CSV pour l'outil HTML de la Phase 3.

**Vérification NaN-safe** : toute comparaison ou jointure sur un champ texte relu depuis un gpkg doit passer par la même normalisation que `synthese_geometries.py`, `_texte()` (voir `etape4_geometries/synthese_geometries.py`) — QGIS convertit couramment une chaîne vide en `NULL`, relu comme `NaN` par `geopandas`, ce qui a déjà causé un bug de résolution de fusion à l'étape 4.

**Documents concernés (tranché le 19/08/2026)** : un groupe fusionné peut porter sur plusieurs `id_gpu` distincts (voir `etape-4-conception-technique.md`, "Mécanisme de fusion" — la cohérence de fusion ne vérifie jamais l'égalité d'`id_gpu`), donc la liste des documents concernés par une synthèse a une cardinalité variable. Plutôt qu'une colonne texte structurée (JSON) dans `etape5_{dept}_a_completer.gpkg` — ce qui aurait introduit le premier champ imbriqué du pipeline, jusqu'ici toujours resté plat — un fichier compagnon dédié, `etape5_{dept}_documents_par_synthese.csv` : un document par ligne (`id_geometrie_synthese`, `id_gpu`, `nature` = `type_piece_source`, `lien_web_document`, `reference_precise`), `id_geometrie_synthese` étant l'`id_geometrie` du meneur du groupe. Cohérent avec le reste du pipeline ("une information, une colonne", déjà tenu partout ailleurs) et directement lisible dans un tableur — au prix d'une jointure de plus pour reconstituer la liste complète d'un groupe, ce qui est un compromis jugé acceptable. Choix qui simplifie aussi, en anticipation, la conception de l'outil de validation (Phase 3) : un CSV plat par groupe se prête mieux à un affichage HTML tabulaire que du JSON à parser.

`etape5_{dept}_a_completer.gpkg` ne porte donc, pour chaque géométrie finale, que `message_synthese_llm` et les identifiants — jamais la liste des documents elle-même.

## Correction humaine : natif + correction, jamais de cascade

*Décidé le 20/08/2026, en réponse à un besoin exprimé après un premier usage réel : conserver la sortie native du LLM même après correction, pour pouvoir s'en servir plus tard comme exemple de recalibrage du prompt (fonctionnalité future, non construite ici — voir "Prochaine étape").*

Chaque message généré (`message_occurrence`, `message_synthese_llm`) est **immuable** une fois écrit par la Phase 2 : jamais réécrit en place. À côté de chacun, trois colonnes, vides à la sortie de la Phase 2, remplies le cas échéant par l'opérateur en Phase 3 :
- `{occurrence,synthese}_corrigee` — booléen (`"True"`/`"False"`), explicite plutôt que déduit (ex. non déduit de "le champ corrigé est-il non vide"). Volontairement un simple booléen, pas les trois états `validé`/`corrigé`/`rejeté` de l'étape 3 : à cette étape du pipeline (géométries déjà validées en étape 4, cohérence déjà vérifiée en début d'étape 5), un "rejet" n'a plus de sens — remettre en cause un message reviendrait à rouvrir les étapes précédentes, pas à statuer ici.
- `message_{occurrence,synthese}_corrige` — la reformulation. Pré-remplie avec une copie du texte natif au moment où l'opérateur coche la case (moins de friction : on retouche, on ne retape pas) ; jamais vidée si la case est décochée par erreur (la case ne pilote que quelle valeur est *active*, pas la présence du texte).
- `validation_message_commentaire` — libre, facultatif, **indépendant** de la case à cocher (un commentaire n'implique pas forcément une correction du texte).

**Pas de cascade entre les deux niveaux** : corriger `message_occurrence` ne régénère jamais `message_synthese_llm`, et les deux corrections (occurrence, synthèse) sont indépendantes — rien n'exige qu'une correction de synthèse s'accompagne d'une correction d'occurrence, ni l'inverse. Techniquement, ceci tient au fait que la synthèse est générée immédiatement après les messages d'occurrence, dans le même passage de `preparer_messages.py` (voir Phase 2 ci-dessus), avant toute intervention humaine possible : faire cascader une correction demanderait de scinder la génération en deux phases avec un palier de validation entre les deux (repoussé, voir "Prochaine étape"). Une synthèse jugée mauvaise à cause d'un message d'occurrence mal formulé se corrige directement au niveau de la synthèse — l'opérateur garde l'entière liberté de réécriture, indépendamment de ce qu'il choisit de signaler au niveau de l'occurrence.

## Phase 3 — Validation humaine (`outil_validation.html`)

Page HTML autonome, sur le modèle de l'étape 3 (`etape3_validation_manuelle/outil_validation.html`) — mêmes choix techniques : aucune dépendance externe (parseur/constructeur CSV maison), aucun stockage navigateur, export manuel + export automatique tous les 10 traitements, l'horodatage du nom de fichier faisant foi pour retrouver le dernier export.

Deux modes indépendants, chacun avec son propre fichier d'entrée et son propre export :
- **Message par occurrence** — charge `etape5_{dept}_occurrences.csv`. Citation source et contexte en lecture seule, citation surlignée au sein du contexte (identique à l'étape 3, `apercuAvecCitationSurlignee`) ; `message_occurrence` natif affiché en lecture seule ; case à cocher + champ de reformulation + commentaire, voir "Correction humaine" ci-dessus.
- **Message fusion** — charge `etape5_{dept}_syntheses.csv`, et éventuellement aussi `etape5_{dept}_occurrences.csv` (facultatif mais recommandé) pour rappeler, en lecture seule, les messages d'occurrence du groupe au-dessus du message de synthèse — permet de suivre le raisonnement du LLM avant de juger la synthèse. **Exclut automatiquement les lignes sans `id_occurrence`** (les trois cas à message fixe), qui ne passent jamais par ce circuit de correction (voir Phase 2 ci-dessus et `etape-5-redaction-messages-diagbruit.md`, "Messages fixes").

Chaque mode exporte séparément : `etape5_export_occurrences_{horodatage}.csv` et `etape5_export_syntheses_{horodatage}.csv` — mêmes colonnes que les fichiers chargés, sans géométrie (jamais chargée par cet outil, qui ne travaille que sur les CSV miroirs).

## Phase 4 — Synthèse finale (`synthese_messages.py`)

Lit `etape5_{dept}_a_completer.gpkg` (géométries + messages natifs, jamais retouché) et le plus récent `etape5_export_syntheses_{horodatage}.csv` (repérage par horodatage encodé dans le nom, même logique que `_dernier_export` à l'étape 3 — voir `etape3_validation_manuelle/synthese_finale.py`) — **requis**, la Phase 4 s'arrête si aucun export n'existe : même discipline qu'à l'étape 3, un passage par l'outil de relecture est attendu même si rien n'est corrigé.

Pour chaque géométrie, résout la valeur finale : `message_synthese_corrige` si `synthese_corrigee`, sinon `message_synthese_llm`. Écrit `etape5_{dept}.gpkg` — couche unique `messages`, contrat pour l'étape 6 — avec `message_synthese` (la valeur résolue) **et** le détail complet (`message_synthese_llm`, `synthese_corrigee`, `message_synthese_corrige`, `validation_message_commentaire`) conservé pour traçabilité, plutôt que seulement la valeur finale.

**`etape5_export_occurrences_{horodatage}.csv` n'est jamais lu ici** — conformément à "Correction humaine : natif + correction, jamais de cascade" ci-dessus, les corrections d'occurrence n'ont pas d'effet sur la synthèse du même run.

**Désynchronisation** : si une géométrie de `etape5_{dept}_a_completer.gpkg` est absente de l'export lu (ex. Phase 2 relancée après l'export), elle est exclue de la sortie finale plutôt qu'assemblée à partir de données possiblement obsolètes — un avertissement liste les identifiants concernés.

## Vérification orthographique (`verifier_orthographe.py`)

*Ajouté le 21/08/2026, en réponse à un besoin exprimé après un premier usage réel : les messages générés par le LLM sont globalement propres, mais une reformulation tapée à la main par l'opérateur en Phase 3 peut introduire des fautes de frappe ou d'accord.*

Lit `etape5_{dept}.gpkg` (déjà produit par la Phase 4). Pour chaque ligne où `synthese_corrigee` est vrai, passe `message_synthese_corrige` à Grammalecte (`pygrammalecte.grammalecte_text`) et concatène les erreurs détectées (orthographe et grammaire, avec suggestion si Grammalecte en propose une) dans une nouvelle colonne `_validation_orthographe`, séparées par `" | "` — vide si rien n'est détecté. **Les messages natifs du LLM (`synthese_corrigee` faux) ne sont jamais vérifiés** : ce n'est pas leur qualité rédactionnelle qui est visée, mais le risque de faute humaine à la frappe.

**Découpage ligne par ligne avant l'appel à Grammalecte** (corrigé le 21/08/2026, suite à un usage réel) : un appel de `grammalecte_text` sur un message entier échoue (`JSONDecodeError` interne à Grammalecte, "Illegal trailing comma before end of array") dès que le texte contient plusieurs lignes dans certaines combinaisons — vérifié en réel sur les 28 messages corrigés du département 067 : 12 échouaient ainsi en appelant Grammalecte sur le texte entier, contre 0 en découpant par ligne au préalable. L'énumération à tirets recommandée par `ton_de_voix.py` ("Phrases courtes, énumérations privilégiées") est justement ce qui déclenche le plus souvent ce bug interne à Grammalecte. Limite acceptée en échange : un accord grammatical qui s'étendrait sur deux lignes ne serait pas détecté — jugé marginal vu le style de phrases courtes déjà en place. Un échec malgré tout (par ligne) est signalé dans `_validation_orthographe` elle-même (`"[erreur de vérification orthographique sur une partie du message]"`) plutôt que silencieux, distinct d'une ligne réellement propre (vide).

Jamais de correction automatique du texte — un signalement à trier par l'opérateur, comme le garde-fou géométrique de la Phase 1. Deux catégories de faux positifs attendues : le vocabulaire du domaine (Grammalecte ne connaît pas "OAP", les noms de rue/secteur, les références d'article) et les conventions typographiques françaises strictes (espace insécable avant `:`/`»`, tiret cadratin recommandé pour une énumération) — une colonne non vide n'est pas une faute certaine.

**Réécrit `etape5_{dept}.gpkg` en place** (même fichier, même couche `messages`) pour y ajouter la colonne, plutôt que produire un fichier séparé — l'objectif explicite étant de pouvoir relire le résultat directement dans QGIS (filtre attributaire sur `"_validation_orthographe" != ''`), sans repasser par un CSV ni par `outil_validation.html` pour cette seule lecture. **Corriger** une faute réelle repérée ainsi passe en revanche toujours par `outil_validation.html` (seul endroit où `message_synthese_corrige` s'édite), suivi d'un nouvel export, d'une nouvelle exécution de `synthese_messages.py`, puis de `verifier_orthographe.py` à nouveau.

Comme `synthese_messages.py` réécrit `etape5_{dept}.gpkg` en entier sans connaître `_validation_orthographe`, cette colonne disparaît si la Phase 4 est relancée après coup — voir la note dans "Architecture des dossiers" ci-dessus.

## Contrat de données

`etape5_{dept}_occurrences.csv` (une ligne par occurrence, écrite par la Phase 2, complétée par la Phase 3) :

| Colonne | Détail |
|---|---|
| `id_geometrie_synthese` | `id_geometrie` du meneur du groupe (ou de l'occurrence isolée) — clé étrangère vers `etape5_{dept}_a_completer.gpkg`/`etape5_{dept}_syntheses.csv`. |
| `id_gpu`, `id_occurrence` | identifiants de l'occurrence, repris de `etape4_{dept}.gpkg`. |
| `message_occurrence` | rédigé par le LLM en Phase 2 — jamais montré à l'utilisateur final de diagBruit, sert de trace de raisonnement pour la Phase 3. Immuable (voir "Correction humaine" ci-dessus). |
| `occurrence_corrigee` | booléen, coché par l'opérateur en Phase 3. |
| `message_occurrence_corrige` | reformulation de l'opérateur, vide si `occurrence_corrigee` est faux. |
| `validation_message_commentaire` | libre, facultatif, indépendant de `occurrence_corrigee`. |
| `extrait_significatif`, `contexte_documentaire`, `justification` | repris de `etape3_{dept}.csv`/`etape4_{dept}.gpkg` par la jointure de la Phase 2 — jamais modifiés, affichage en lecture seule dans `outil_validation.html`. |
| `lien_web_document`, `reference_precise` | repris de `etape4_{dept}.gpkg`. |
| `nature_sonore_zone` | repris de `etape4_{dept}.gpkg` — ajouté le 21/08/2026, affiché en badge dans `outil_validation.html` (mode "Message par occurrence"), sur le modèle des badges de l'étape 3. |

`etape5_{dept}_syntheses.csv` (une ligne par géométrie finale, miroir CSV sans géométrie de la couche `syntheses` de `etape5_{dept}_a_completer.gpkg`) :

| Colonne | Détail |
|---|---|
| `id_geometrie`, `id_gpu`, `id_occurrence` | identifiants — `id_occurrence` vide pour les trois cas à message fixe (voir Phase 2). |
| `message_synthese_llm` | rédigé par le LLM en Phase 2 (ou message fixe pour `rnu`/`document_non_significatif`/`trou_de_couverture`). Immuable. |
| `synthese_corrigee`, `message_synthese_corrige`, `validation_message_commentaire` | même principe que pour les occurrences ci-dessus. |

`etape5_{dept}.gpkg` (couche `messages`, sortie de la Phase 4 — contrat pour l'étape 6) reprend les colonnes de `etape5_{dept}_syntheses.csv` et ajoute `message_synthese`, la valeur résolue (native ou corrigée) — voir Phase 4 ci-dessus. `verifier_orthographe.py` y ajoute ensuite `_validation_orthographe` (voir section dédiée ci-dessus) — présente uniquement après son exécution, absente si seule la Phase 4 a tourné.

`etape5_{dept}_documents_par_synthese.csv` (un document par ligne) :

| Colonne | Détail |
|---|---|
| `id_geometrie_synthese` | `id_geometrie` du meneur du groupe (ou de l'occurrence isolée) — clé étrangère vers la ligne correspondante de `etape5_{dept}_a_completer.gpkg`/`etape5_{dept}.gpkg`. |
| `id_gpu` | identifiant du document, pour distinguer deux entrées d'un même groupe qui porteraient sur des documents différents. |
| `nature` | reprise de `type_piece_source` (voir `etape-4-conception-technique.md`, "Contrat de données"). Décidé le 20/08/2026 : pas de colonne `nom_document` en plus — `nature` suffit à identifier chaque entrée dans la liste "Docs sources" assemblée à l'étape 6 (voir `etape-6-mise-en-forme-diagbruit.md`). |
| `lien_web_document` | reprise telle quelle de `etape4_{dept}.gpkg`. |
| `reference_precise` | reprise telle quelle de `etape4_{dept}.gpkg`. |

Une géométrie de synthèse peut ainsi être associée à plusieurs lignes de ce fichier (groupe fusionné multi-documents) ; une occurrence isolée n'y a qu'une seule ligne.

## Gestion des erreurs

Même principe que les étapes précédentes pour les échecs isolés (appel LLM en échec, occurrence introuvable dans `etape3_{dept}.csv`) : n'interrompent jamais le traitement du reste du département — consignés dans `etape5_{dept}_erreurs.csv` (Phase 2), supprimé plutôt que laissé tel quel si une exécution n'a plus rien à y signaler, même logique que `etape4_{dept}_erreurs.csv` (voir `etape4_geometries/synthese_geometries.py`). La Phase 1 (garde-fou géométrique) produit, elle, des **avertissements** dans un fichier distinct (`etape5_{dept}_avertissements.csv`) — distinction volontaire de vocabulaire : rien n'y est objectivement invalide, contrairement à un échec de génération.

`preparer_messages.py` s'arrête avec un message explicite si `etape4_{dept}.gpkg` ou `etape3_{dept}.csv` est introuvable — comme aux étapes précédentes, l'absence d'un fichier d'entrée entier ne laisse rien d'exploitable en aval, contrairement à un échec isolé sur une occurrence. `synthese_messages.py` (Phase 4) s'arrête de même si `etape5_{dept}_a_completer.gpkg` ou tout export `etape5_export_syntheses_*.csv` est introuvable, et exclut (avec avertissement, jamais silencieusement) toute géométrie désynchronisée entre les deux — voir Phase 4 ci-dessus.

## Dépendances retenues

- `anthropic` — déjà présent (étape 2), réutilisé pour la génération des messages plutôt que d'introduire un autre moteur de génération de texte. Même modèle (`claude-sonnet-5`), mêmes réglages (`thinking` désactivé, sorties structurées via `output_config.format`), même gestion des tentatives (`tenacity`) que `etape2_analyse_reglements/classification.py` — repris à l'identique plutôt que réinventé.
- `python-dotenv` — déjà présent (étape 2), pour charger `ANTHROPIC_API_KEY` depuis `.env` à la racine de `poc-urbanisme-plu/`. `preparer_messages.py` s'arrête immédiatement si la clé est absente, même garde-fou que `classification.py`.
- `geopandas`/`shapely`/`pyproj` — déjà présents (étape 4) ; `pyproj`, dépendance transitive de `geopandas`, couvre la reprojection nécessaire au calcul de distances métriques en Phase 1.
- **Aucune dépendance nouvelle pour `outil_validation.html`** — même choix qu'à l'étape 3 : parseur/constructeur CSV maison, aucune bibliothèque externe, page utilisable hors ligne.
- `pygrammalecte` — nouvelle dépendance (`verifier_orthographe.py`), retenue plutôt que LanguageTool : correcteur spécifiquement français (accords, typographie française), pas de JVM à installer contrairement à LanguageTool, entièrement hors ligne une fois sa propre dépendance Grammalecte-fr installée (au premier import, automatiquement).

## Prochaine étape

Étape 6 — mise en forme des données selon le format attendu pour ingestion dans la base diagBruit, à partir de `etape5_{dept}.gpkg` (voir `etape-6-mise-en-forme-diagbruit.md`).

**Reporté** (voir "Correction humaine : natif + correction, jamais de cascade" ci-dessus) : si le besoin de faire cascader une correction d'occurrence vers une régénération de la synthèse se confirme à l'usage, la Phase 2 devra être scindée en deux (génération des messages d'occurrence, palier de validation, génération de la synthèse à partir des messages validés) — non fait pour l'instant, la version actuelle traite les deux corrections comme indépendantes.

**Reporté également** : réinjecter les corrections accumulées (`message_*_corrige`) comme exemples de recalibrage dans les prompts de `preparer_messages.py` pour les prochains départements — fonctionnalité future explicitement anticipée par le mécanisme natif+correction ci-dessus, non construite ici.
