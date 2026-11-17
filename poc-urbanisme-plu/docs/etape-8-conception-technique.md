# Étape 8 — Conception technique : publication des alertes en préprod

*Document de conception technique, faisant suite à `etape-8-publication-diagbruit.md` et à `etape-7-conception-technique.md`.*

## Posture

Même POC, même posture que les étapes 1 à 7 (voir `etape-1-conception-technique.md`). Comme l'étape 7, cette étape **écrit dans un système partagé** (Strapi préprod) et, en plus, rend son contenu **visible sur le front** : `--publier` explicite requis pour toute écriture réelle, dry-run par défaut.

## Requête de publication — vérifiée le 17/11/2026 (Strapi 5.13.0)

```
PUT {url_preprod}/api/noisezone-alerts/{documentId}?status=published
{"data": {}}
```

**Constat du 17/11/2026, en préprod** : cette requête publie le brouillon existant **à l'identique**. Testée sur deux alertes du 067, l'une après l'autre (`--ids 375`, puis `--ids 316`) :
- Strapi accepte le corps vide `{"data": {}}` ;
- la version publiée porte les mêmes `alert_slug`, `title`, `content`, `source`, `reference`, `label` que le brouillon (contrôle automatique, et contre-vérification manuelle par relecture des deux versions : seuls l'`id` interne et `publishedAt` diffèrent) — aucun champ vidé ;
- l'audit (`inserer --audit`) reste sain : 0 doublon, 0 publié sans brouillon ;
- vérification à l'œil par l'opérateur : statut « published » dans l'admin Strapi, alerte 316 (Hœrdt, marges de recul le long de l'A35) affichée conforme sur le front de préprod. La 375 (Scheibenhard) n'a pas pu être vue sur le front : ses parcelles n'ont pas de score de bruit, et le front n'affiche alors pas le PLU (limite connue du produit, suivie par l'équipe de développement) — d'où le choix d'une zone le long d'une grande route pour le test.

Pourquoi c'était une hypothèse : on savait seulement qu'un `POST`/`PUT` **sans** `status=draft` publie l'entrée (observé le 24/08/2026 sur une **création**, voir `etape-7-conception-technique.md`, "Piège : publication automatique"). `client_strapi._put` passe toujours `status=draft` pour cette raison ; la publication passe par une fonction distincte (`_put_publication`), pour qu'aucun appel existant ne puisse publier par erreur.

**Garde-fous conservés dans le code** :
1. **Comparaison automatique** après chaque publication : `client_strapi.lire_entree` relit le brouillon **avant** l'appel et la version publiée **après**, et compare les six champs ci-dessus. Une différence, ou une version publiée introuvable, **arrête le run immédiatement** (une erreur de ce type a toutes les chances d'être systématique).
2. **`--ids`** pour limiter la publication à quelques `id_geometrie`.

**À refaire si la version de Strapi change** (voir `cms/package.json`) : dry-run, puis `--ids <un id> --publier` sur une alerte visible sur le front (zone avec score de bruit), vérification à l'œil, puis le reste.

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
