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
5. **Export de la géométrie** : écrit `etape6_{dept}_geometries/{id_geometrie}.geojson` (une géométrie, en EPSG:4326, comme `etape5_{dept}.gpkg`). Seule propriété portée par le GeoJSON : `id_geometrie` — **délibérément pas `alert_slug`**, voir `etape-7-conception-technique.md`, "Correctif du 20/10/2026" : à ce stade de l'étape 6, `alert_slug_propose` n'est le plus souvent qu'une proposition mécanique incomplète (voir "Reprise à la régénération" ci-dessous), la valeur finale n'étant connue qu'après la complétion manuelle en Phase 2 — la propriété `alert_slug` est ajoutée au fichier local juste avant son dépôt sur Box, à l'étape 7, pas ici.
6. **Écriture de la ligne** dans `etape6_{dept}_export.csv` (voir "Contrat de données") — avec reprise de `alert_slug_propose`/`description_slug` depuis un export précédent s'il existe (voir "Reprise à la régénération" ci-dessous).

## Pourquoi la déduplication est correcte

**Lire avant de retirer ce mécanisme.** `strapi_source` et `strapi_reference` sont dédupliqués (`dedupliquer_en_conservant_ordre`, dans `assembler_message.py`) avant jointure. Ce n'est pas un nettoyage arbitraire de la donnée : c'est la conséquence directe d'une décision humaine déjà prise et validée à l'étape 5. `notion_description` (calculé par citations, lui aussi dédupliqué autrefois) n'existe plus — remplacé par `titre_propose`, le raisonnement ci-dessous ne s'applique donc plus qu'à `strapi_source`/`strapi_reference`.

Le raisonnement, en trois temps :

1. Un groupe fusionné peut compter plusieurs occurrences distinctes, chacune avec son propre `extrait_significatif`/`message_occurrence`/`reference_precise` — vérifié en réel sur `067-plui-strasbourg` (`id_geometrie_synthese=2`) : 4 occurrences bien distinctes (remplacement de menuiserie, pose d'une double vitrage intérieur, modification d'un ouvrage en surplomb, remplacement de profils/verres), toutes citant "Article 4" faute d'un `reference_precise` assez granulaire pour descendre à l'alinéa. Ces occurrences **ne sont pas des doublons entre elles**, et `etape5_{dept}_occurrences.csv`/`etape5_{dept}_documents_par_synthese.csv` les gardent toutes, une ligne chacune — jamais dédupliqués, jamais touchés à l'étape 6.
2. Mais la **fusion elle-même** de ces occurrences en une seule géométrie de synthèse est une décision déjà validée par l'opérateur (garde-fou `controle_similarite.py`, fusion explicite à l'étape 4, relecture du `message_synthese` résultant dans `outil_validation.html` à l'étape 5). Une fois validée, le groupe produit **un seul message cohérent** : les occurrences ne sont plus, du point de vue du lecteur final, des informations séparées, mais une règle déjà reformulée en une seule fois.
3. `strapi_source`/`strapi_reference` ne sont pas des fichiers de traçabilité (ce rôle reste tenu par `etape5_{dept}_documents_par_synthese.csv`/`etape5_{dept}_occurrences.csv`) — ce sont des champs de synthèse pour le lecteur final, répondant à "quels documents/références soutiennent cette règle ?". Une fois la fusion validée, citer 4 fois "Article 4" n'apporte rien de plus que le citer une fois : la granularité des occurrences a déjà été absorbée dans `message_synthese`.

Il serait tentant de retirer cette déduplication au motif que "des valeurs identiques ne veulent pas dire des occurrences identiques" (vrai, mais incomplet) : cet argument s'arrête à l'étape 1 ci-dessus, sans aller jusqu'aux étapes 2-3 (la fusion déjà validée rend cette distinction non pertinente pour un champ de synthèse). Sans déduplication, `strapi_reference` afficherait `"Article 4 / Article 4 / Article 4 / Article 4"` — jamais produit par une saisie manuelle réelle (vérifié sur une capture d'écran Strapi).

**Cas `rnu`/`document_non_significatif`/`document_non_exploitable`/`trou_de_couverture`** : ces quatre cas suivent le même traitement — ils ont eux aussi une géométrie et un message dans `etape5_{dept}.gpkg` (Phase A de l'étape 4), donc une ligne d'export comme les autres. Seule différence : `etape5_{dept}_documents_par_synthese.csv` n'a pas d'entrée pour ces `id_geometrie` (pas de document source).

**Source et référence de ces quatre cas (décision du 20/10/2026)** : elles étaient laissées vides jusque-là. Or `source` et `reference` sont **obligatoires** dans le schéma Strapi, et Strapi 5.13.0 ne le vérifie qu'à la publication, pas pour un brouillon (`required: !isDraft && attr.required`) : vides, les alertes auraient été créées puis impossibles à publier (253 lignes sur 400 pour le 067 hors Eurométropole, détecté au dry-run de l'étape 7). Valeurs fixes désormais calculées par `source_reference_sans_document` (`generer_export.py`), selon `nature_zone` :

| `nature_zone` | `strapi_source` | `strapi_reference` |
|---|---|---|
| `rnu` | `Code de l'urbanisme` | `Règlement national d'urbanisme (art. L111-1 à L111-35 et R111-1 à R111-64)` |
| `trou_de_couverture` | `Géoportail de l'Urbanisme` | `Aucun document d'urbanisme référencé à date du {JJ/MM/AAAA}` — date de **consultation** du Géoportail à l'étape 1 (plus récente `date_traitement` de `etape1_{dept}.csv`), plus exacte qu'une date de création : c'est ce jour-là que l'absence a été constatée |
| `document_non_significatif` | nom complet du document (`nom_document`, `etape4_{dept}.gpkg`), ex. `Plan Local d'Urbanisme (PLU) de la commune de ALTORF` | `Aucune disposition relative au bruit identifiée` |
| `document_non_exploitable` | nom complet du document | `Document non exploitable automatiquement` |

RNU : pas de lien Legifrance dans `reference` — `source` et `reference` sont du texte simple, affiché tel quel par le front (`DiagnosticRegulationBox.tsx`), une URL n'y serait pas cliquable. L'affichage d'un lien (partie législative `LEGISCTA000031719324`, partie réglementaire `LEGISCTA000031721322`) est une question posée à l'équipe de développement (20/10/2026). `message_strapi` est assemblé avec ces mêmes valeurs (`assembler_message_valeurs`).

Vérifié sur un export réel (`etape4_067-plui-strasbourg.gpkg`, colonne `communes`) : le séparateur est `", "` (virgule-espace), pas `" / "` comme envisagé initialement. `resolution_territoire.py` s'appuie sur ce séparateur constaté.

`etape5_{dept}.gpkg` (couche `messages`) ne porte en réalité pas de colonne `communes` — son contrat de données réel (voir `etape-5-conception-technique.md`, "Contrat de données") se limite à `id_geometrie`, `id_gpu`, `id_occurrence` et aux colonnes de message. La colonne existe en revanche dans `etape4_{dept}.gpkg` (couche `geometries`), sous le même `id_geometrie` pour les géométries `occurrence_locale` conservées jusqu'à l'étape 5 (le `id_geometrie` du meneur d'un groupe fusionné, vérifié identique entre les deux fichiers sur l'export réel). `generer_export.py` relit donc aussi `etape4_{dept}.gpkg` — en plus de `etape5_{dept}.gpkg` et `etape5_{dept}_documents_par_synthese.csv` — uniquement pour cette colonne, avec le même garde-fou de désynchronisation que pour les deux autres fichiers d'entrée (voir "Gestion des erreurs" ci-dessous).

## Écart avec le schéma Strapi réel

`message_strapi` (le bloc `Message : ... / Docs sources : ... / références : ...`) a été conçu pour une saisie manuelle dans un unique champ. Le schéma réel (`cms/src/api/noisezone-alert/content-types/noisezone-alert/schema.json`) a en fait des champs distincts, requis : `content` (HTML), `source` (texte), `reference` (texte), et `label` (enum `ZONE SOUMISE AU BRUIT` / `ZONE CALME`) — voir `etape-7-stockage-diagbruit.md`, "Schéma Strapi", pour le détail. `generer_export.py` calcule donc, en plus de `message_strapi` (conservé pour une lecture rapide en tableur), les colonnes séparées `message_content`, `strapi_source`, `strapi_reference` et `label_propose`, correspondant chacune à un champ Strapi réel — voir "Contrat de données" ci-dessous.

`title` (schéma Strapi) et `Description` (base Notion) sont couverts par ce contrat, tous deux alimentés par `titre_propose` (voir ci-dessus) — auparavant, `title` n'était pas renseigné (saisi manuellement à la relecture du brouillon Strapi) et `Description` était calculée par citations.

## Reprise à la régénération

`generer_export.py` peut être relancé après une première complétion manuelle de `alert_slug_propose`/`description_slug` (dans `outil_validation.html`) sans perdre cette saisie : si `etape6_{dept}_export.csv` existe déjà dans le dossier de sortie, ces deux colonnes y sont relues par `id_geometrie`. **Seuls les slugs au statut `manuel` sont repris** (revu le 13/10/2026, statuts définis dans `etape-6-mise-en-forme-diagbruit.md`, "Format de l'alert_slug") : un slug `vide`, `initialisé` ou `automatisé` est recalculé, pour qu'une évolution des règles (slugification, règle automatique) se propage. Une valeur qui n'entre dans aucun statut (`non_conforme`, ex. moins de deux `-`) est aussi conservée, pour ne jamais effacer une saisie ; elle sera rejetée à l'étape 7. Le décompte par statut est affiché en fin de run. Limite connue : si la règle automatique change, un ancien slug automatisé ne lui correspond plus et est vu comme `manuel`, donc conservé — le décompte permet de le repérer. Toutes les autres colonnes (territoire, message, géométrie...) sont, elles, toujours recalculées fraîchement — déterministe, donc sans perte si rien n'a changé en amont depuis le run précédent.

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
| `alert_slug_propose` | `alert-{territoire_propose réduit à A-Z a-z 0-9}-` à la génération, ou slug complet `alert-{Territoire}-{Commune}{Suffixe}` pour les cas sans contenu métier mono-commune (règle automatique, voir `etape-6-mise-en-forme-diagbruit.md`, "Format de l'alert_slug") (incomplet, `description_slug` non pris en compte puisque vide) ; complété en valeur finale par l'opérateur dans `outil_validation.html` (voir Phase 2), pas par un second passage du script. |
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

## Évolution prévue — proposition automatique des termes métier (non implémentée)

*Décidée le 19/10/2026, à reprendre avant le prochain territoire. Rien n'est codé à ce stade.*

### Constat sur le 067 hors Eurométropole

Après la règle automatique du 13/10 (cas sans contenu métier, voir `etape-6-mise-en-forme-diagbruit.md`, "Format de l'alert_slug"), il restait 149 termes métier saisis à la main, en une demi-journée environ. Analyse de ces 149 termes (export `etape6_export_alert_slugs_20261019_115431.csv`, avant correction des doublons) :
- **77 (52 %) reprennent simplement la zone réglementaire** mentionnée dans `zone_reglementaire_mentionnee` (`etape4_{dept}.gpkg`) : `ZoneUa`, `SecteurUep`, `Zone1Aux3`, `Zone1Au`, `PADD`… Ils sont déductibles **sans LLM** ;
- **72 sont des termes libres** : `TraitementPaysager`, `EspacesTransition`, `ExtensionAgricole`, `NuisancesActivitesMixte`, `Tampon`…
- **10 slugs étaient en double** (21 lignes), presque tous parce qu'un même code de zone (`ZoneUa`) revenait dans deux communes d'un même EPCI. Corrigé le 19/10 en mettant la commune devant le terme (`LupsteinZoneUa` / `PrintzheimZoneUa`). Aucun contrôle ne l'avait signalé pendant la saisie.

### Convention retenue (19/10/2026)

**CamelCase pour le terme métier, sans tiret** : le tiret est réservé au séparateur des champs du slug (`alert-{Territoire}-{Terme}`). Les termes historiques de l'Eurométropole (`autorisation-spr`, `habillage-pac`, en minuscules avec tirets) ne suivent pas cette convention : ils doivent être convertis (`AutorisationSpr`) avant d'être utilisés comme exemples (niveau 2 ci-dessous).

### Les trois niveaux de l'évolution

**Niveau 1 — Règle déterministe pour les règles de zone** (dans `generer_export.py`, à côté de `_slug_automatise`) :
- condition : `nature_zone == "occurrence_locale"`, une seule commune, et `zone_reglementaire_mentionnee` reconnue comme un code de zone court (ex. `UA`, `1AUx3`, `Uep` ; à exclure : les descriptions longues comme « zone d'activité limitrophe de l'habitat » ou « secteur formé par l'îlot des rues… ») ;
- terme : `{Commune}{Zone|Secteur}{Code}`, ex. `alert-CCduPaysdeSaverne-LupsteinZoneUa`. La commune est mise **d'office**, pour éviter les doublons entre communes d'un même EPCI (cause des 10 doublons du 067). Le choix `Zone`/`Secteur` peut reprendre le mot présent dans `zone_reglementaire_mentionnee` ou dans `titre_propose` ; `Zone` par défaut ;
- casse du code : à normaliser (le 067 mélange `ZoneUa` et `ZoneUA`) — proposition : première lettre en majuscule, le reste tel que dans le règlement (`ZoneUA`, `Zone1AUx3`), à trancher au moment de coder ;
- statut : `automatise` (même mécanique que la règle du 13/10 : recalculé à chaque relance, jamais une saisie manuelle écrasée). `MOTIF_AUTOMATISE` dans `outil_validation.html` devra être élargi en conséquence, sinon ces slugs y apparaîtront comme `manuel`.

**Niveau 2 — Suggestion par LLM pour les termes libres** :
- ⚠️ **contredit une décision documentée** (`etape-6-mise-en-forme-diagbruit.md`, "Format de l'alert_slug" : « une génération automatique risquerait de proposer un terme plausible mais faux »). Garde-fou retenu : la suggestion ne remplace **jamais** le slug. Elle va dans une **nouvelle colonne `alert_slug_suggere`**, et `alert_slug_propose` reste `initialise` tant que l'opérateur ne l'a pas acceptée ;
- exemples donnés au LLM (few-shot) : les couples `titre_propose` → terme validés du 067 hors Eurométropole (`etape6_067_export.csv`, lignes au statut `manuel`, environ 70 hors termes de zone) et de l'Eurométropole (`output/EurometropoleDeStrasbourg/etape6_export_alert_slugs_20260821_234826.csv`, 28 lignes, convertis en CamelCase). Prévoir un fichier de référence versionné (ex. `etape6_mise_en_forme/exemples_termes_metier.csv`) alimenté à chaque nouveau territoire, plutôt que de relire les exports de chaque département ;
- entrée par ligne : `titre_propose` et `message_content` (le titre seul est souvent trop court) ;
- implémentation : reprendre le schéma de `etape5_redaction_messages/preparer_messages.py` (`_appeler_claude`, sortie structurée, prompt caching du bloc d'exemples dans `system`, cache disque `etape6_{dept}_cache_llm.jsonl` pour qu'une relance ne coûte rien) ;
- consignes du prompt : un vocable du domaine urbanisme/acoustique, **pas un résumé** du message ; CamelCase ; 1 à 3 mots ; ne pas répéter le territoire ni la commune (ajoutée par le script si nécessaire à l'unicité) ;
- évaluation avant adoption : sur le 067, proposer un terme pour chaque ligne en retirant ses propres exemples (validation croisée simple), et mesurer la part de termes identiques ou jugés acceptables. Seuil d'adoption à décider avec l'opérateur.

**Niveau 3 — Contrôles d'unicité et de format, dès l'étape 6** :
- `generer_export.py` : signaler (sans bloquer) les slugs en double et les slugs hors `A-Z a-z 0-9 - _ . ~` à la fin du run, à côté du décompte des statuts ;
- `outil_validation.html` : badge « doublon » et badge « format » recalculés à la frappe, et filtre correspondant — les doublons du 067 auraient été vus pendant la saisie ;
- l'étape 7 garde son propre contrôle bloquant (voir `etape-7-conception-technique.md`) : l'étape 6 aide l'opérateur, l'étape 7 protège Strapi/Notion.

### Côté outil de validation (`outil_validation.html`)

Pour le niveau 2 : afficher `alert_slug_suggere` sous le champ de saisie, avec un bouton « Accepter » qui recopie la suggestion dans le champ (statut → `manuel`, puisque validé par l'opérateur). Ajouter `alert_slug_suggere` à `COLONNES_EXPORT` (JS) **et** à `COLONNES_EXPORT` (`generer_export.py`), sinon un réexport la perdrait (voir "Phase 2 — Outil de validation").

### Ordre de mise en œuvre conseillé

Niveau 3 (simple, utile tout de suite), puis niveau 1 (déterministe, environ la moitié des termes métier), puis niveau 2 (LLM, à évaluer avant adoption).

## Prochaine étape

Voir `etape-6-mise-en-forme-diagbruit.md`, "Prochaine étape" — étape 7, qui automatise l'insertion dans Strapi et Notion à partir de `etape6_{dept}_export.csv` et `etape6_{dept}_geometries/` (voir `etape-7-conception-technique.md`).
