# Étape 8 — Conception technique : publication des alertes en préprod

*Document de conception technique, faisant suite à `etape-8-publication-diagbruit.md` et à `etape-7-conception-technique.md`.*

## Posture

Même POC, même posture que les étapes 1 à 7 (voir `etape-1-conception-technique.md`). Comme l'étape 7, cette étape **écrit dans un système partagé** (Strapi préprod) et, en plus, rend son contenu **visible sur le front** : `--publier` explicite requis pour toute écriture réelle, dry-run par défaut.

## ⚠️ Hypothèse à vérifier en réel avant tout envoi complet

**Requête de publication retenue, jamais testée au 13/11/2026** :

```
PUT {url_preprod}/api/noisezone-alerts/{documentId}?status=published
{"data": {}}
```

Ce que l'on sait (Strapi 5.13.0) :
- un `POST`/`PUT` **sans** `status=draft` publie l'entrée — observé en réel le 24/08/2026 sur une **création** (voir `etape-7-conception-technique.md`, "Piège : publication automatique") ;
- `client_strapi._put` passe toujours `status=draft` pour cette raison ; la publication passe donc par une fonction distincte (`_put_publication`), pour qu'aucun appel existant ne puisse publier par erreur.

Ce que l'on **ne sait pas** :
- si un `PUT` avec `status=published` publie bien le brouillon **existant** (et pas seulement les champs envoyés) ;
- si Strapi accepte un corps `{"data": {}}` (il peut le refuser : erreur 400, sans dégât) ;
- si une mise à jour vide peut vider des champs de la version publiée (cas le plus grave, à écarter absolument).

**Garde-fous dans le code** :
1. **Comparaison automatique** après chaque publication : `client_strapi.lire_entree` relit le brouillon **avant** l'appel et la version publiée **après**, et compare `alert_slug`, `title`, `content`, `source`, `reference`, `label`. Une différence, ou une version publiée introuvable, **arrête le run immédiatement** (une erreur de ce type a toutes les chances d'être systématique : inutile de la répéter 397 fois).
2. **`--ids`** pour limiter la publication à quelques `id_geometrie`.

**Procédure obligatoire au premier usage**, et à refaire si la version de Strapi change :
1. `python -m etape8_publication.publier --dept 067 --output-dir output/067_horsEurometropole` (dry-run) ;
2. `... --ids <un id> --publier` ;
3. vérification **à l'œil** dans l'admin Strapi et sur le front de préprod ;
4. `... --publier` pour le reste (les alertes déjà publiées sont sautées).

**Repli si Strapi refuse le corps vide** : renvoyer dans `data` les champs lus dans le brouillon juste avant (`lire_entree`), sans passer par l'export. À n'implémenter que si le test le rend nécessaire, et à documenter ici.

Une fois l'hypothèse confirmée (ou corrigée), remplacer cette section par le constat daté.

## Pourquoi réutiliser `etape7_stockage/client_strapi.py`

Exception assumée à la règle « chaque étape reste indépendante du code des autres » (`etape-1-conception-technique.md`, Décision 2) : la connaissance de Strapi accumulée à l'étape 7 (paramètre `status`, recherche en deux temps brouillon/publié, détection des doublons, deux environnements) est précisément ce dont l'étape 8 a besoin. La recopier dupliquerait des pièges déjà corrigés. Les fonctions de publication (`_put_publication`, `lire_entree`, `publier`) sont donc ajoutées à `client_strapi.py`, et `etape8_publication/publier.py` l'importe.

## Architecture des dossiers

```
poc-urbanisme-plu/
├── etape7_stockage/
│   └── client_strapi.py               # + lire_entree, publier (13/11/2026)
├── etape8_publication/
│   ├── __init__.py                    # vide
│   └── publier.py                     # phase unique
└── output/
    ├── etape6_{dept}_export.csv           # entrée : liste des alert_slug du département
    ├── etape8_{dept}_publications.csv     # journal des publications, jamais relu
    └── etape8_{dept}_erreurs.csv          # erreurs, absent si rien à signaler
```

## Phase unique — Publication (`publier.py`)

Usage, depuis `poc-urbanisme-plu/` :

```
python -m etape8_publication.publier --dept 067 --output-dir output/067_horsEurometropole
# → dry-run : liste ce qui serait publié, sans rien écrire

python -m etape8_publication.publier --dept 067 --output-dir output/067_horsEurometropole --ids 1 --publier
# → publie une seule alerte (id_geometrie 1)

python -m etape8_publication.publier --dept 067 --output-dir output/067_horsEurometropole --publier
# → publie toutes les alertes du département encore en brouillon seul
```

`--environnement` existe pour la cohérence avec l'étape 7 mais **seul `preprod` est accepté** : `prod` est refusé avant tout appel réseau (décision du 13/11/2026, voir la doc métier).

Déroulé :
1. Lecture de `etape6_{dept}_export.csv` ; avec `--ids`, filtrage sur `id_geometrie` — un identifiant inconnu arrête tout avant le moindre appel réseau.
2. Vérification de la configuration Strapi de l'environnement.
3. Pour chaque ligne, recherche de l'état réel dans Strapi (`client_strapi.etat_entree`, brouillons **et** publiés, doublons détectés) :
   - **absente** → erreur (`absent`) : l'étape 7 n'a pas été faite pour cette ligne ;
   - **plusieurs documents** → erreur (`doublon`), aucune écriture ;
   - **déjà publiée** → sautée, comptée (`deja_publiee`) — jamais republiée ;
   - **brouillon seul** → publiée (avec `--publier`), ou annoncée (dry-run).
4. Pour une publication réelle : lecture du brouillon, `client_strapi.publier`, lecture de la version publiée, comparaison champ à champ (voir l'hypothèse ci-dessus) ; arrêt immédiat à la première différence.
5. Journal écrit et vidé sur disque ligne par ligne (même raison qu'à l'étape 7 : une interruption laisse une trace exacte de ce qui a été publié).

## Contrat de données

`etape8_{dept}_publications.csv` (avec `--publier` seulement, ajouté en fin de fichier, jamais relu par le script) :

| Colonne | Détail |
|---|---|
| `id_geometrie` | reprise de l'export de l'étape 6. |
| `alert_slug` | slug de l'alerte publiée. |
| `environnement` | toujours `preprod` à ce jour. |
| `strapi_document_id` | `documentId` publié — c'est lui qu'il faut cibler pour un éventuel retour arrière dans l'admin. |
| `date_traitement` | date de la publication. |

`etape8_{dept}_erreurs.csv` : colonnes habituelles (`identifiant`, `source`, `message`, `date_traitement`) ; `source` vaut `absent`, `doublon`, `strapi` (appel refusé) ou `verification` (version publiée différente du brouillon). Écrit seulement avec `--publier`, supprimé s'il n'y a rien à signaler.

## Vérification finale

`python -m etape7_stockage.inserer --dept 067 --output-dir output/067_horsEurometropole --audit` : après publication complète, le résumé doit indiquer toutes les alertes du département publiées, 0 en brouillon seul, 0 `publie_sans_brouillon` (état qui casse l'admin, voir `etape-7-conception-technique.md`, "Draft and publish").

## Dépendances

Aucune nouvelle : `requests`, `tenacity`, `python-dotenv`, via `client_strapi`.
