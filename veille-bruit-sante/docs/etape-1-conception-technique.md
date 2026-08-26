# Étape 1 — Conception technique : projet et base Notion "Études"

*Document de cadrage technique, faisant suite à `plan-veille-bruit-sante-diagbruit.md` et `etape-1-base-notion-diagbruit.md`. Pose l'architecture générale du projet (valable pour toutes les étapes suivantes), pas seulement la création de la base.*

## Posture

Projet autonome, sur le même modèle que `poc-urbanisme-plu` : une preuve de concept qui automatise une veille, pas un composant produit à intégrer tout de suite. On privilégie la simplicité et l'absence de risque pour l'existant (`fastapi/`, `dagster/`, `frontend/`, `cms/`) à l'alignement complet sur les standards du produit. La gestion des erreurs reprend explicitement la politique retenue sur `poc-urbanisme-plu` (échec isolé jamais bloquant), comme déjà noté dans `etape-3-integration-notion-diagbruit.md`.

## Décision 1 — Un dossier autonome à la racine du dépôt

Le code vit dans **`veille-bruit-sante/`**, à la racine du dépôt, au même niveau que `poc-urbanisme-plu/`, `fastapi/`, `dagster/`.

**Pourquoi :** aucune dépendance avec l'environnement Dagster/dbt ni avec l'API produit — ce projet lit et écrit dans Notion, pas dans PostGIS. Un dossier isolé, avec son propre environnement Python et ses propres dépendances, ne risque jamais de casser l'existant et peut être déplacé ou supprimé librement.

## Décision 2 — Architecture des dossiers : un module par étape, un point d'entrée unique

Contrairement à `poc-urbanisme-plu` (pipeline à vérification humaine entre chaque étape, donc fichiers CSV intermédiaires), ce projet tourne **sans supervision, une fois par semaine** : les étapes 2 et 3 s'enchaînent dans le même run, sans point d'arrêt pour relecture. Le découpage en modules reste néanmoins un dossier `etapeN_xxx/` par étape du plan (même convention de nommage que `poc-urbanisme-plu`), y compris pour l'étape 1 bien qu'elle soit ponctuelle et jamais appelée par `main.py` (voir Décision 4) — mais le point d'entrée de production reste un seul script qui enchaîne les étapes 2 et 3.

```
veille-bruit-sante/
├── README.md
├── requirements.txt
├── .env.example
│
├── config/
│   └── domains_whitelist.yaml     # liste des domaines autorisés pour web_search (étape 2)
│
├── etape2_recherche_extraction/
│   ├── __init__.py
│   ├── recherche_apis.py          # Phase 1a — OpenAlex + Europe PMC
│   ├── recherche_web.py           # Phase 1b — web_search (API Anthropic), restreint via domains_whitelist.yaml
│   ├── extraction.py              # Phase 2 — extraction structurée par étude (appel API Anthropic)
│   └── dedoublonnage.py           # Phase 3 — dédoublonnage interne au run (DOI puis titre)
│
├── etape3_integration_notion/
│   ├── __init__.py
│   ├── etat_existant.py           # Phase 1 — récupération doi_url/titre déjà présents dans la base
│   ├── dedoublonnage_existant.py  # Phase 2 — dédoublonnage contre l'existant (même logique que ci-dessus)
│   └── ecriture.py                # Phase 3 — création des nouvelles fiches Notion
│
├── main.py                        # point d'entrée unique : enchaîne étape 2 puis étape 3
│
└── etape1_base_notion/
    └── creer_base_notion.py       # création ponctuelle de la base "Études" (voir Décision 4)
```

**Pourquoi un seul point d'entrée (`main.py`) plutôt qu'un script par étape appelé séparément par le workflow GitHub Actions :** la date de la dernière recherche (voir Décision 3) n'est calculée qu'une fois, en tout début de run, à partir de l'état de la base Notion — la partager entre deux scripts lancés séparément demanderait de la sérialiser quelque part, ce que le principe "aucune mémoire locale entre deux runs" (voir `etape-4-automatisation-diagbruit.md`) exclut justement. `main.py` importe et enchaîne les fonctions des deux modules dans le même process.

## Décision 3 — Date de la dernière recherche : calculée, jamais stockée

`main.py` calcule la date de départ de la recherche hebdomadaire (voir `etape-2-recherche-extraction-diagbruit.md`) par un appel à l'API Notion en tout début de run : la date `date_ajout` la plus récente parmi les fiches existantes de la base "Études". Base vide (premier run) → date de départ = aujourd'hui moins 10 ans.

**Pourquoi ne pas stocker cette date dans un fichier local (`last_run.json` ou équivalent) :** GitHub Actions recrée une machine vierge à chaque exécution (voir `etape-4-automatisation-diagbruit.md`) — un fichier écrit pendant un run n'existe plus au run suivant, sauf à le committer dans le dépôt à chaque run (mécanisme fragile, source de conflits git, hors de propos pour un simple horodatage déjà disponible ailleurs). La base Notion est la seule mémoire persistante du projet ; s'appuyer sur elle évite toute duplication d'état.

## Décision 4 — Création de la base Notion : script ponctuel, pas manuel

`etape1_base_notion/creer_base_notion.py` crée la base "Études" via l'API Notion (`notion-client`, méthode `databases.create`), avec exactement les colonnes et types du contrat de données de `etape-1-base-notion-diagbruit.md`. Exécuté une seule fois, à la main, hors de la boucle hebdomadaire — jamais appelé par `main.py`.

**Pourquoi un script plutôt qu'une création manuelle dans l'interface Notion :** un script rend la création reproductible (base de test, recréation en cas d'erreur de configuration) et documente le contrat de données dans le code plutôt que dans la seule mémoire de la personne qui l'a créée à la main. Le coût de l'écrire est faible : la structure de colonnes est déjà entièrement spécifiée par `etape-1-base-notion-diagbruit.md`, il n'y a pas de logique à concevoir, seulement à traduire en appel API.

**Sur le nommage `etape1_base_notion/` malgré son caractère ponctuel :** gardé par cohérence avec la convention `etapeN_xxx/` de `poc-urbanisme-plu`, même si — contrairement aux dossiers des étapes 2 et 3 — ce module n'est jamais invoqué par `main.py` ni exécuté par le workflow hebdomadaire (voir `etape-4-conception-technique.md`). Le nom seul ne suffit donc pas à distinguer "module du pipeline récurrent" de "outil ponctuel" : c'est ce document qui fait foi sur ce point.

```python
proprietes = {
    "titre": {"title": {}},
    "auteurs": {"rich_text": {}},
    "annee": {"number": {}},
    "revue": {"select": {}},
    "organisme": {"rich_text": {}},
    "doi_url": {"url": {}},
    "domaine_sante": {"multi_select": {"options": [
        {"name": "Cardiovasculaire"}, {"name": "Santé mentale"},
        {"name": "Cognition"}, {"name": "Métabolique"},
        {"name": "Sommeil"}, {"name": "Enfant"},
    ]}},
    "source_bruit": {"multi_select": {"options": [
        {"name": "Routier"}, {"name": "Aérien"},
        {"name": "Ferroviaire"}, {"name": "Industriel"},
    ]}},
    "resume": {"rich_text": {}},
    "resultat_cle": {"rich_text": {}},
    "date_ajout": {"created_time": {}},
    "statut": {"select": {"options": [
        {"name": "🆕 Nouveau"}, {"name": "✅ Lu"},
    ]}},
    "favori": {"checkbox": {}},
}
```

**Point d'attention :** `date_ajout` en `created_time` est une propriété calculée automatiquement par Notion (jamais transmise à la création d'une page, voir `etape-3-conception-technique.md`) — cohérent avec `etape-1-base-notion-diagbruit.md` ("Remplie automatiquement à la création de la fiche"). La base doit ensuite être partagée manuellement avec l'intégration Notion (l'API ne peut pas s'accorder ce droit elle-même) : dans Notion, ouvrir la page parente choisie pour héberger la base, `···` → `Connexions` → sélectionner l'intégration. L'identifiant de la base (`NOTION_DATABASE_ID`), affiché dans l'URL de la base une fois créée, est à reporter dans les secrets (voir `etape-4-conception-technique.md`).

## Dépendances retenues

- `notion-client` — SDK officiel Notion, utilisé aux étapes 1 (setup), 3 (lecture/écriture).
- `anthropic` — SDK officiel Anthropic, pour `web_search` et l'extraction structurée (étape 2).
- `requests` — appels HTTP directs à OpenAlex et Europe PMC (pas de SDK officiel pour ces deux API).
- `python-dotenv` — chargement des secrets depuis `.env` en local (en production, GitHub Actions les injecte directement en variables d'environnement, voir `etape-4-conception-technique.md`).
- `pyyaml` — lecture de `config/domains_whitelist.yaml`.

## Prochaine étape

Étape 2 — recherche hebdomadaire et extraction structurée : détail des deux canaux de recherche, du prompt d'extraction et du dédoublonnage interne au run.
