# Étape 6 — Conception technique : mise en forme pour transmission à la partie développement

*Document de cadrage technique, faisant suite à `etape-6-mise-en-forme-diagbruit.md` et à `etape-5-conception-technique.md`.*

## Posture

Même sous-dossier du même POC que les étapes 1 à 5 (voir `etape-1-conception-technique.md`) : code écrit par un non-développeur, isolé du reste du produit, preuve de concept plutôt que composant prêt à intégrer.

À l'usage, la complétion de l'`alert_slug` (terme métier + vérification du territoire, voir "Format de l'alert_slug" dans `etape-6-mise-en-forme-diagbruit.md`) sur des dizaines de lignes s'est révélée pénible dans un tableur brut — un `outil_validation.html` a été ajouté à cette étape, plus léger que celui de l'étape 5 (pas de checkbox natif/corrigé, aucun contenu à valider n'étant généré par LLM ici : juste un champ à compléter, avec le message final déjà validé à l'étape 5 affiché en regard pour contexte). Voir "Outil de validation" ci-dessous.

## Architecture des dossiers

```
poc-urbanisme-plu/
├── etape5_redaction_messages/             # existant
├── etape6_mise_en_forme/
│   ├── __init__.py                        # vide, comme les modules précédents
│   ├── resolution_territoire.py           # aide partagée : résolution commune → EPCI via geo.api.gouv.fr
│   ├── assembler_message.py               # aide partagée : assemblage déterministe du message Strapi
│   ├── generer_export.py                  # Phase 1 — écrit etape6_{dept}_export.csv + etape6_{dept}_geometries/
│   └── outil_validation.html              # Phase 2 — manuel : complétion de l'alert_slug
└── output/
    ├── etape4_{dept}.gpkg                     # relu pour `communes` et `nature_sonore_zone`, absentes de etape5_{dept}.gpkg (voir plus bas)
    ├── etape5_{dept}.gpkg                     # dont `titre_propose` (voir plus bas)
    ├── etape5_{dept}_documents_par_synthese.csv
    ├── etape6_{dept}_export.csv               # contrat pour la saisie manuelle Strapi + Notion
    ├── etape6_{dept}_geometries/               # un .geojson par géométrie finale, nommé {id_geometrie}.geojson
    └── etape6_{dept}_erreurs.csv               # échecs isolés de résolution de territoire, si non vide
```

Deux phases : génération automatique, puis relecture manuelle dans `outil_validation.html` (voir section dédiée ci-dessous) — sur le modèle des étapes 3 et 5, mais sans script de synthèse a posteriori : l'export de l'outil est directement le fichier final (voir "Outil de validation"). Usage, depuis `poc-urbanisme-plu/` :

```
python -m etape6_mise_en_forme.generer_export --dept 033
# ouvrir outil_validation.html, charger etape6_033_export.csv, compléter
# alert_slug pour chaque ligne, exporter (renommer le dernier export en
# etape6_033_export.csv, ou l'utiliser tel quel)
# pour chaque ligne : saisir Strapi (alert_slug + message_strapi)
# et Notion (Territoire, Description, alert_slug, geojson correspondant dans etape6_033_geometries/)
```

## Phase 1 — Génération de l'export (`generer_export.py`)

Lit `etape5_{dept}.gpkg` (couche `messages`), `etape5_{dept}_documents_par_synthese.csv` et `etape4_{dept}.gpkg` (couche `geometries`, pour `communes` et `nature_sonore_zone` — voir écart constaté plus bas). `etape5_{dept}_occurrences.csv` n'est pas relu ici : il reste un fichier de traçabilité de l'étape 5, jamais une entrée de l'étape 6 (voir "Pourquoi la déduplication est correcte" ci-dessous). Pour chaque géométrie finale :

1. **Assemblage des champs Strapi** (`assembler_message.py`) : à partir de `message_synthese` et de la liste des `nature`/`reference_precise` issues de `etape5_{dept}_documents_par_synthese.csv` filtrée sur `id_geometrie_synthese == id_geometrie` — le bloc `message_strapi` complet (formalisme de `etape-6-mise-en-forme-diagbruit.md`, "Assemblage du message pour Strapi"), **et** les mêmes valeurs exposées séparément (`message_content`, `strapi_source`, `strapi_reference` — voir "Écart avec le schéma Strapi réel" ci-dessous). **Avec déduplication** (voir "Pourquoi la déduplication est correcte" ci-dessous) : `nature`/`reference_precise` sont dédupliqués avant jointure.
2. **Résolution du territoire** (`resolution_territoire.py`) : découpe `communes`, résout chaque commune vers son code INSEE puis son EPCI via `geo.api.gouv.fr`, propose `territoire_propose` selon la logique décrite dans le document de cadrage. Résultat mis en cache par nom de commune + département pour la durée du run, pour ne pas répéter un appel API déjà fait — plusieurs géométries peuvent partager les mêmes communes.
3. **Proposition de `label_propose`** (voir "Écart avec le schéma Strapi réel") : `ZONE CALME` si `nature_sonore_zone == "preservation_zone_calme"`, `ZONE SOUMISE AU BRUIT` sinon (y compris vide, pour `rnu`/`document_non_significatif`/`document_non_exploitable`/`trou_de_couverture`).
4. **Reprise de `titre_propose`** — repris tel quel de `etape5_{dept}.gpkg` (généré par LLM et validé à l'étape 5, voir `etape-5-conception-technique.md`, "Phase 2"), sans transformation. Remplace le calcul précédent de `notion_description` par citations — voir `etape-7-stockage-diagbruit.md`, "Colonne Description".
5. **Export de la géométrie** : écrit `etape6_{dept}_geometries/{id_geometrie}.geojson` (une géométrie, en EPSG:4326, comme `etape5_{dept}.gpkg`).
6. **Écriture de la ligne** dans `etape6_{dept}_export.csv` (voir "Contrat de données") — avec reprise de `alert_slug_propose`/`description_slug` depuis un export précédent s'il existe (voir "Reprise à la régénération" ci-dessous).

## Pourquoi la déduplication est correcte

**Lire avant de retirer ce mécanisme.** `strapi_source` et `strapi_reference` sont dédupliqués (`dedupliquer_en_conservant_ordre`, dans `assembler_message.py`) avant jointure. Ce n'est pas un nettoyage arbitraire de la donnée : c'est la conséquence directe d'une décision humaine déjà prise et validée à l'étape 5. `notion_description` (calculé par citations, lui aussi dédupliqué autrefois) n'existe plus — remplacé par `titre_propose`, le raisonnement ci-dessous ne s'applique donc plus qu'à `strapi_source`/`strapi_reference`.

Le raisonnement, en trois temps :

1. Un groupe fusionné peut compter plusieurs occurrences distinctes, chacune avec son propre `extrait_significatif`/`message_occurrence`/`reference_precise` — vérifié en réel sur `067-plui-strasbourg` (`id_geometrie_synthese=2`) : 4 occurrences bien distinctes (remplacement de menuiserie, pose d'une double vitrage intérieur, modification d'un ouvrage en surplomb, remplacement de profils/verres), toutes citant "Article 4" faute d'un `reference_precise` assez granulaire pour descendre à l'alinéa. Ces occurrences **ne sont pas des doublons entre elles**, et `etape5_{dept}_occurrences.csv`/`etape5_{dept}_documents_par_synthese.csv` les gardent toutes, une ligne chacune — jamais dédupliqués, jamais touchés à l'étape 6.
2. Mais la **fusion elle-même** de ces occurrences en une seule géométrie de synthèse est une décision déjà validée par l'opérateur (garde-fou `controle_similarite.py`, fusion explicite à l'étape 4, relecture du `message_synthese` résultant dans `outil_validation.html` à l'étape 5). Une fois validée, le groupe produit **un seul message cohérent** : les occurrences ne sont plus, du point de vue du lecteur final, des informations séparées, mais une règle déjà reformulée en une seule fois.
3. `strapi_source`/`strapi_reference` ne sont pas des fichiers de traçabilité (ce rôle reste tenu par `etape5_{dept}_documents_par_synthese.csv`/`etape5_{dept}_occurrences.csv`) — ce sont des champs de synthèse pour le lecteur final, répondant à "quels documents/références soutiennent cette règle ?". Une fois la fusion validée, citer 4 fois "Article 4" n'apporte rien de plus que le citer une fois : la granularité des occurrences a déjà été absorbée dans `message_synthese`.

Il serait tentant de retirer cette déduplication au motif que "des valeurs identiques ne veulent pas dire des occurrences identiques" (vrai, mais incomplet) : cet argument s'arrête à l'étape 1 ci-dessus, sans aller jusqu'aux étapes 2-3 (la fusion déjà validée rend cette distinction non pertinente pour un champ de synthèse). Sans déduplication, `strapi_reference` afficherait `"Article 4 / Article 4 / Article 4 / Article 4"` — jamais produit par une saisie manuelle réelle (vérifié sur une capture d'écran Strapi).

**Cas `rnu`/`document_non_significatif`/`document_non_exploitable`/`trou_de_couverture`** : ces quatre cas suivent le même traitement — ils ont eux aussi une géométrie et un message dans `etape5_{dept}.gpkg` (Phase A de l'étape 4), donc une ligne d'export comme les autres. Seule différence : `etape5_{dept}_documents_par_synthese.csv` n'a pas d'entrée pour ces `id_geometrie` (pas de document source), donc "Docs sources"/"références" restent vides dans le message assemblé — cohérent avec les messages fixes déjà rédigés à l'étape 5, qui ne citent pas de document.

Vérifié sur un export réel (`etape4_067-plui-strasbourg.gpkg`, colonne `communes`) : le séparateur est `", "` (virgule-espace), pas `" / "` comme envisagé initialement. `resolution_territoire.py` s'appuie sur ce séparateur constaté.

`etape5_{dept}.gpkg` (couche `messages`) ne porte en réalité pas de colonne `communes` — son contrat de données réel (voir `etape-5-conception-technique.md`, "Contrat de données") se limite à `id_geometrie`, `id_gpu`, `id_occurrence` et aux colonnes de message. La colonne existe en revanche dans `etape4_{dept}.gpkg` (couche `geometries`), sous le même `id_geometrie` pour les géométries `occurrence_locale` conservées jusqu'à l'étape 5 (le `id_geometrie` du meneur d'un groupe fusionné, vérifié identique entre les deux fichiers sur l'export réel). `generer_export.py` relit donc aussi `etape4_{dept}.gpkg` — en plus de `etape5_{dept}.gpkg` et `etape5_{dept}_documents_par_synthese.csv` — uniquement pour cette colonne, avec le même garde-fou de désynchronisation que pour les deux autres fichiers d'entrée (voir "Gestion des erreurs" ci-dessous).

## Écart avec le schéma Strapi réel

`message_strapi` (le bloc `Message : ... / Docs sources : ... / références : ...`) a été conçu pour une saisie manuelle dans un unique champ. Le schéma réel (`cms/src/api/noisezone-alert/content-types/noisezone-alert/schema.json`) a en fait des champs distincts, requis : `content` (HTML), `source` (texte), `reference` (texte), et `label` (enum `ZONE SOUMISE AU BRUIT` / `ZONE CALME`) — voir `etape-7-stockage-diagbruit.md`, "Schéma Strapi", pour le détail. `generer_export.py` calcule donc, en plus de `message_strapi` (conservé pour une lecture rapide en tableur), les colonnes séparées `message_content`, `strapi_source`, `strapi_reference` et `label_propose`, correspondant chacune à un champ Strapi réel — voir "Contrat de données" ci-dessous.

`title` (schéma Strapi) et `Description` (base Notion) sont couverts par ce contrat, tous deux alimentés par `titre_propose` (voir ci-dessus) — auparavant, `title` n'était pas renseigné (saisi manuellement à la relecture du brouillon Strapi) et `Description` était calculée par citations.

## Reprise à la régénération

`generer_export.py` peut être relancé après une première complétion manuelle de `alert_slug_propose`/`description_slug` (dans `outil_validation.html`) sans perdre cette saisie : si `etape6_{dept}_export.csv` existe déjà dans le dossier de sortie, ces deux colonnes y sont relues et reprises telles quelles par `id_geometrie`, plutôt que recalculées depuis zéro. Toutes les autres colonnes (territoire, message, géométrie...) sont, elles, toujours recalculées fraîchement — déterministe, donc sans perte si rien n'a changé en amont depuis le run précédent.

**Point opérationnel** : la reprise ne lit que `etape6_{dept}_export.csv` lui-même, jamais un export de `outil_validation.html` resté sous son nom horodaté (`etape6_export_alert_slugs_{horodatage}.csv`) — pensez à renommer le dernier export de l'outil en `etape6_{dept}_export.csv` avant de relancer `generer_export.py`, sinon la reprise ne verra pas la dernière saisie.

## Phase 2 — Outil de validation (`outil_validation.html`)

*En réponse à un besoin exprimé après un premier usage réel : compléter l'`alert_slug` sur des dizaines de lignes directement dans un tableur s'est révélé pénible sans le message final sous les yeux.*

Page HTML autonome, sur le modèle des outils des étapes 3 et 5 (parseur/constructeur CSV maison, aucune dépendance externe, aucun stockage navigateur, export manuel + export automatique tous les 10 champs modifiés, horodatage du nom de fichier). Un seul jeu de données (pas de distinction occurrence/synthèse comme à l'étape 5) : charge `etape6_{dept}_export.csv` (ou un export précédent de l'outil, pour reprendre une session), affiche par ligne :
- `territoire_propose`, `label_propose` (en badge à côté du territoire), `nom_fichier_geometrie` et `communes` en lecture seule, pour contexte ;
- `message_strapi` en lecture seule — le message déjà validé à l'étape 5, qu'il soit natif ou corrigé manuellement, sans distinction ici : cette question est déjà tranchée en amont, l'outil n'a pas à la rejouer ;
- un unique champ éditable, préempli avec `alert_slug_propose` (proposition mécanique incomplète, ex. `alert-EurometropoledeStrasbourg-`), à compléter directement avec le terme métier ou à corriger entièrement si `territoire_propose` est faux. Pas de case "corrigé" ni de conservation d'une valeur native séparée (contrairement à l'étape 5) : `alert_slug_propose` n'est qu'une proposition mécanique jetable, pas un contenu généré à comparer à sa version corrigée — un badge "modifié", recalculé pour la session en cours par comparaison à la valeur chargée, aide seulement à suivre la progression sans ajouter de colonne au contrat de données.

**Pas de script de synthèse a posteriori** (différent de l'étape 5) : l'export de l'outil a exactement la même structure que `etape6_{dept}_export.csv` (mêmes colonnes) et devient directement le fichier à utiliser pour la saisie Strapi/Notion, une fois renommé (ou tel quel). Cohérent avec l'étape 6 "à phase unique" pour la partie automatisée : la relecture manuelle est une étape en plus, pas une refonte de l'architecture en phases automatiques multiples. La liste de colonnes de l'outil (`COLONNES_EXPORT`, dans le JS) doit rester synchronisée avec celle de `generer_export.py` — sinon un réexport depuis l'outil perdrait silencieusement les colonnes ajoutées depuis (`message_content`, `strapi_source`, `strapi_reference`, `label_propose`, `titre_propose`).

## Gestion des erreurs

Un échec isolé de résolution de territoire (commune introuvable, API indisponible) n'empêche jamais l'export de la ligne : `territoire_propose` reste vide, `alert_slug_propose` aussi (rien à assembler sans territoire), mais la ligne entière reste écrite dans `etape6_{dept}_export.csv` avec le message assemblé — l'opérateur peut toujours compléter le territoire à la main. L'échec est tracé dans `etape6_{dept}_erreurs.csv` (supprimé plutôt que laissé vide si rien à signaler, même logique que les étapes précédentes).

Une désynchronisation entre les fichiers d'entrée (un `id_geometrie_synthese` de `etape5_{dept}_documents_par_synthese.csv` absent de `etape5_{dept}.gpkg`, une géométrie `occurrence_locale` sans aucune ligne dans le fichier documents, ou un `id_geometrie` de `etape5_{dept}.gpkg` absent de `etape4_{dept}.gpkg`) est en revanche plus grave — signale une incohérence entre des fichiers censés être issus du même run — et arrête le traitement avec un message explicite plutôt que de produire un export partiellement incohérent, comme le fait déjà `synthese_messages.py` à l'étape 5 pour un cas similaire. **`titre_propose_llm` absent pour une géométrie** (échec isolé de génération à l'étape 5, voir `etape-5-conception-technique.md`) en revanche n'est jamais bloquant ici : `titre_propose` reste simplement vide pour la géométrie concernée.

`generer_export.py` s'arrête immédiatement, comme aux étapes précédentes, si `etape5_{dept}.gpkg`, `etape5_{dept}_documents_par_synthese.csv` ou `etape4_{dept}.gpkg` est introuvable — rien d'exploitable en aval sans eux.

**`--dept` et suffixe de document** : en usage réel de test, `--dept` a porté un suffixe après un tiret (`067-plui-strasbourg`, convention utilisée pour tester les étapes 3 à 6 sur un seul document sans rejouer les étapes 1/2 sur tout le département). Ce suffixe n'est pas un code département exploitable par l'API Découpage administratif — `resolution_territoire.py` ne retient que la partie avant le premier tiret pour ses appels à `geo.api.gouv.fr`, la valeur complète de `--dept` restant utilisée telle quelle pour le nommage des fichiers, comme dans toutes les étapes précédentes.

## Contrat de données

`etape6_{dept}_export.csv` (une ligne par géométrie finale) :

| Colonne | Détail |
|---|---|
| `id_geometrie` | reprise de `etape5_{dept}.gpkg` — sert aussi de nom de fichier dans `etape6_{dept}_geometries/`. |
| `territoire_propose` | calculé par `resolution_territoire.py` — proposition modifiable par l'opérateur avant saisie Notion/construction du slug. |
| `description_slug` | **toujours vide** — colonne conservée pour compatibilité avec le contrat initial, mais non utilisée en pratique : l'opérateur saisit directement le terme métier dans `alert_slug_propose` complet via `outil_validation.html` (voir Phase 2), sans passer par un champ séparé. |
| `alert_slug_propose` | `alert-{territoire_propose sans espaces/accents}-` à la génération (incomplet, `description_slug` non pris en compte puisque vide) ; complété en valeur finale par l'opérateur dans `outil_validation.html` (voir Phase 2), pas par un second passage du script. |
| `message_strapi` | message assemblé, format `Message : ... / Docs sources : ... / références : ...` — pour une lecture rapide en tableur ; pas destiné à être copié tel quel, voir les colonnes séparées ci-dessous. |
| `message_content` | `message_synthese` seul (sans "Docs sources"/"références") — correspond au champ Strapi `content` (à convertir en HTML : un `<p>` par ligne, non fait par ce script — voir `etape-7-stockage-diagbruit.md`). |
| `strapi_source` | liste dédupliquée des `nature` (`etape5_{dept}_documents_par_synthese.csv`, elle-même reprise de `type_piece_source` calculé à l'étape 4, ex. "règlement écrit"), jointe par `" / "` (voir "Pourquoi la déduplication est correcte") — correspond au champ Strapi `source`. |
| `strapi_reference` | liste dédupliquée des `reference_precise`, jointe par `" / "` — correspond au champ Strapi `reference`. |
| `label_propose` | `ZONE CALME` ou `ZONE SOUMISE AU BRUIT`, déduit de `nature_sonore_zone` (`etape4_{dept}.gpkg`) — correspond au champ Strapi `label`. |
| `titre_propose` | titre court généré par LLM et validé à l'étape 5 (`titre_propose` de `etape5_{dept}.gpkg`), repris tel quel — correspond au champ Strapi `title` et à la colonne Notion `Description`. |
| `nom_fichier_geometrie` | nom du fichier dans `etape6_{dept}_geometries/` (`{id_geometrie}.geojson`) — à joindre manuellement au champ `data` de Notion. |
| `communes` | reprise telle quelle de `etape4_{dept}.gpkg` (voir écart constaté ci-dessus), pour vérification visuelle rapide si `territoire_propose` semble incorrect. |

## Dépendances retenues

- `requests` — déjà présent (étape 1), réutilisé pour les appels à `geo.api.gouv.fr` (résolution commune → EPCI).
- `geopandas` — déjà présent (étape 4/5), pour lire `etape5_{dept}.gpkg` et écrire chaque géométrie individuelle en GeoJSON.
- Aucune dépendance Python nouvelle : ni appel LLM (la partie du slug qui l'aurait justifié est finalement laissée à la saisie manuelle, voir `etape-6-mise-en-forme-diagbruit.md`, "Format de l'alert_slug"), ni bibliothèque supplémentaire pour `generer_export.py`.
- **`outil_validation.html`** (voir Phase 2) — aucune dépendance non plus, même choix qu'aux étapes 3 et 5 : parseur/constructeur CSV maison, page utilisable hors ligne.

## Prochaine étape

Voir `etape-6-mise-en-forme-diagbruit.md`, "Prochaine étape" — étape 7, qui automatise l'insertion dans Strapi et Notion à partir de `etape6_{dept}_export.csv` et `etape6_{dept}_geometries/` (voir `etape-7-conception-technique.md`).
