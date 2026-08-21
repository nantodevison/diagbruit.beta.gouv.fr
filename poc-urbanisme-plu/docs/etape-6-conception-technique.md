# Étape 6 — Conception technique : mise en forme pour transmission à la partie développement

*Document de cadrage technique, faisant suite à `etape-6-mise-en-forme-diagbruit.md` et à `etape-5-conception-technique.md`. Version issue des échanges du 21/08/2026.*

## Posture

Même sous-dossier du même POC que les étapes 1 à 5 (voir `etape-1-conception-technique.md`) : code écrit par un non-développeur, isolé du reste du produit, preuve de concept plutôt que composant prêt à intégrer.

**Révisé le 21/08/2026** : à l'usage, la complétion de l'`alert_slug` (terme métier + vérification du territoire, voir "Format de l'alert_slug" dans `etape-6-mise-en-forme-diagbruit.md`) sur des dizaines de lignes s'est révélée pénible dans un tableur brut — un `outil_validation.html` a finalement été ajouté, plus léger que celui de l'étape 5 (pas de checkbox natif/corrigé, aucun contenu à valider n'étant généré par LLM ici : juste un champ à compléter, avec le message final déjà validé à l'étape 5 affiché en regard pour contexte). Voir "Outil de validation" ci-dessous.

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
    ├── etape4_{dept}.gpkg                     # relu uniquement pour `communes`, absente de etape5_{dept}.gpkg (voir plus bas)
    ├── etape5_{dept}.gpkg
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

Lit `etape5_{dept}.gpkg` (couche `messages`), `etape5_{dept}_documents_par_synthese.csv` et `etape4_{dept}.gpkg` (couche `geometries`, pour `communes` — voir écart constaté plus bas). Pour chaque géométrie finale :

1. **Assemblage du message** (`assembler_message.py`) : concatène `message_synthese`, la liste des `nature` (Docs sources) et `reference_precise` (références) issues de `etape5_{dept}_documents_par_synthese.csv` filtrée sur `id_geometrie_synthese == id_geometrie`, selon le formalisme défini dans `etape-6-mise-en-forme-diagbruit.md`, "Assemblage du message pour Strapi".
2. **Résolution du territoire** (`resolution_territoire.py`) : découpe `communes`, résout chaque commune vers son code INSEE puis son EPCI via `geo.api.gouv.fr`, propose `territoire_propose` selon la logique décrite dans le document de cadrage. Résultat mis en cache par nom de commune + département pour la durée du run, pour ne pas répéter un appel API déjà fait — plusieurs géométries peuvent partager les mêmes communes.
3. **Export de la géométrie** : écrit `etape6_{dept}_geometries/{id_geometrie}.geojson` (une géométrie, en EPSG:4326, comme `etape5_{dept}.gpkg`).
4. **Écriture de la ligne** dans `etape6_{dept}_export.csv` (voir "Contrat de données").

**Cas `rnu`/`document_non_significatif`/`trou_de_couverture`** : ces trois cas suivent le même traitement — ils ont eux aussi une géométrie et un message dans `etape5_{dept}.gpkg` (Phase A de l'étape 4), donc une ligne d'export comme les autres. Seule différence : `etape5_{dept}_documents_par_synthese.csv` n'a pas d'entrée pour ces `id_geometrie` (pas de document source), donc "Docs sources"/"références" restent vides dans le message assemblé — cohérent avec les messages fixes déjà rédigés à l'étape 5, qui ne citent pas de document.

**Point tranché le 21/08/2026, à l'implémentation** : vérifié sur un export réel (`etape4_067-plui-strasbourg.gpkg`, colonne `communes`) — le séparateur est `", "` (virgule-espace), pas `" / "` comme envisagé initialement. `resolution_territoire.py` s'appuie sur ce séparateur constaté.

**Écart constaté avec ce document, le 21/08/2026** : `etape5_{dept}.gpkg` (couche `messages`) ne porte en réalité pas de colonne `communes` — son contrat de données réel (voir `etape-5-conception-technique.md`, "Contrat de données") se limite à `id_geometrie`, `id_gpu`, `id_occurrence` et aux colonnes de message. La colonne existe en revanche dans `etape4_{dept}.gpkg` (couche `geometries`), sous le même `id_geometrie` pour les géométries `occurrence_locale` conservées jusqu'à l'étape 5 (le `id_geometrie` du meneur d'un groupe fusionné, vérifié identique entre les deux fichiers sur l'export réel). `generer_export.py` relit donc aussi `etape4_{dept}.gpkg` — en plus de `etape5_{dept}.gpkg` et `etape5_{dept}_documents_par_synthese.csv` — uniquement pour cette colonne, avec le même garde-fou de désynchronisation que pour les deux autres fichiers d'entrée (voir "Gestion des erreurs" ci-dessous). Non anticipé dans la version précédente de ce document, qui décrivait `etape5_{dept}.gpkg` comme seule entrée géométrique.

## Phase 2 — Outil de validation (`outil_validation.html`)

*Ajouté le 21/08/2026, en réponse à un besoin exprimé après un premier usage réel : compléter l'`alert_slug` sur des dizaines de lignes directement dans un tableur s'est révélé pénible sans le message final sous les yeux.*

Page HTML autonome, sur le modèle des outils des étapes 3 et 5 (parseur/constructeur CSV maison, aucune dépendance externe, aucun stockage navigateur, export manuel + export automatique tous les 10 champs modifiés, horodatage du nom de fichier). Un seul jeu de données (pas de distinction occurrence/synthèse comme à l'étape 5) : charge `etape6_{dept}_export.csv` (ou un export précédent de l'outil, pour reprendre une session), affiche par ligne :
- `territoire_propose`, `nom_fichier_geometrie` et `communes` en lecture seule, pour contexte ;
- `message_strapi` en lecture seule — le message déjà validé à l'étape 5, qu'il soit natif ou corrigé manuellement, sans distinction ici : cette question est déjà tranchée en amont, l'outil n'a pas à la rejouer ;
- un unique champ éditable, préempli avec `alert_slug_propose` (proposition mécanique incomplète, ex. `alert-EurometropoledeStrasbourg-`), à compléter directement avec le terme métier ou à corriger entièrement si `territoire_propose` est faux. Pas de case "corrigé" ni de conservation d'une valeur native séparée (contrairement à l'étape 5) : `alert_slug_propose` n'est qu'une proposition mécanique jetable, pas un contenu généré à comparer à sa version corrigée — un badge "modifié", recalculé pour la session en cours par comparaison à la valeur chargée, aide seulement à suivre la progression sans ajouter de colonne au contrat de données.

**Pas de script de synthèse a posteriori** (décision du 21/08/2026, différente de l'étape 5) : l'export de l'outil a exactement la même structure que `etape6_{dept}_export.csv` (mêmes colonnes) et devient directement le fichier à utiliser pour la saisie Strapi/Notion, une fois renommé (ou tel quel). Cohérent avec l'étape 6 "à phase unique" pour la partie automatisée : la relecture manuelle est une étape en plus, pas une refonte de l'architecture en phases automatiques multiples.

## Gestion des erreurs

Un échec isolé de résolution de territoire (commune introuvable, API indisponible) n'empêche jamais l'export de la ligne : `territoire_propose` reste vide, `alert_slug_propose` aussi (rien à assembler sans territoire), mais la ligne entière reste écrite dans `etape6_{dept}_export.csv` avec le message assemblé — l'opérateur peut toujours compléter le territoire à la main. L'échec est tracé dans `etape6_{dept}_erreurs.csv` (supprimé plutôt que laissé vide si rien à signaler, même logique que les étapes précédentes).

Une désynchronisation entre les fichiers d'entrée (un `id_geometrie_synthese` de `etape5_{dept}_documents_par_synthese.csv` absent de `etape5_{dept}.gpkg`, une géométrie `occurrence_locale` sans aucune ligne dans le fichier documents, ou un `id_geometrie` de `etape5_{dept}.gpkg` absent de `etape4_{dept}.gpkg`) est en revanche plus grave — signale une incohérence entre des fichiers censés être issus du même run — et arrête le traitement avec un message explicite plutôt que de produire un export partiellement incohérent, comme le fait déjà `synthese_messages.py` à l'étape 5 pour un cas similaire.

`generer_export.py` s'arrête immédiatement, comme aux étapes précédentes, si `etape5_{dept}.gpkg`, `etape5_{dept}_documents_par_synthese.csv` ou `etape4_{dept}.gpkg` est introuvable — rien d'exploitable en aval sans eux.

**`--dept` et suffixe de document (constaté le 21/08/2026)** : en usage réel de test, `--dept` a porté un suffixe après un tiret (`067-plui-strasbourg`, convention utilisée pour tester les étapes 3 à 6 sur un seul document sans rejouer les étapes 1/2 sur tout le département). Ce suffixe n'est pas un code département exploitable par l'API Découpage administratif — `resolution_territoire.py` ne retient que la partie avant le premier tiret pour ses appels à `geo.api.gouv.fr`, la valeur complète de `--dept` restant utilisée telle quelle pour le nommage des fichiers, comme dans toutes les étapes précédentes.

## Contrat de données

`etape6_{dept}_export.csv` (une ligne par géométrie finale) :

| Colonne | Détail |
|---|---|
| `id_geometrie` | reprise de `etape5_{dept}.gpkg` — sert aussi de nom de fichier dans `etape6_{dept}_geometries/`. |
| `territoire_propose` | calculé par `resolution_territoire.py` — proposition modifiable par l'opérateur avant saisie Notion/construction du slug. |
| `description_slug` | **toujours vide** — colonne conservée pour compatibilité avec le contrat initial, mais non utilisée en pratique : l'opérateur saisit directement le terme métier dans `alert_slug_propose` complet via `outil_validation.html` (voir Phase 2), sans passer par un champ séparé. |
| `alert_slug_propose` | `alert-{territoire_propose sans espaces/accents}-` à la génération (incomplet, `description_slug` non pris en compte puisque vide) ; complété en valeur finale par l'opérateur dans `outil_validation.html` (voir Phase 2), pas par un second passage du script. |
| `message_strapi` | message assemblé, format `Message : ... / Docs sources : ... / références : ...` — prêt à copier dans le champ message de Strapi. |
| `nom_fichier_geometrie` | nom du fichier dans `etape6_{dept}_geometries/` (`{id_geometrie}.geojson`) — à joindre manuellement au champ `data` de Notion. |
| `communes` | reprise telle quelle de `etape4_{dept}.gpkg` (voir écart constaté ci-dessus), pour vérification visuelle rapide si `territoire_propose` semble incorrect. |

## Dépendances retenues

- `requests` — déjà présent (étape 1), réutilisé pour les appels à `geo.api.gouv.fr` (résolution commune → EPCI).
- `geopandas` — déjà présent (étape 4/5), pour lire `etape5_{dept}.gpkg` et écrire chaque géométrie individuelle en GeoJSON.
- Aucune dépendance Python nouvelle : ni appel LLM (la partie du slug qui l'aurait justifié est finalement laissée à la saisie manuelle, voir `etape-6-mise-en-forme-diagbruit.md`, "Format de l'alert_slug"), ni bibliothèque supplémentaire pour `generer_export.py`.
- **`outil_validation.html`** (ajouté le 21/08/2026, voir Phase 2) — aucune dépendance non plus, même choix qu'aux étapes 3 et 5 : parseur/constructeur CSV maison, page utilisable hors ligne.

## Prochaine étape

Voir `etape-6-mise-en-forme-diagbruit.md`, "Prochaine étape" — le circuit se termine, pour cette itération, par la saisie manuelle dans Strapi et Notion à partir de `etape6_{dept}_export.csv` et `etape6_{dept}_geometries/`.
