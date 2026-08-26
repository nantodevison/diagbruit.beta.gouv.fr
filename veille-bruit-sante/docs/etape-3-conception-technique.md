# Étape 3 — Conception technique : intégration Notion

*Document de cadrage technique, faisant suite à `etape-3-integration-notion-diagbruit.md` et à `etape-2-conception-technique.md`.*

## Point d'entrée du module

```python
# etape3_integration_notion/main.py (appelé par main.py à la racine)
def executer(etudes: list[dict]) -> None:
    """Reçoit la liste dédoublonnée en interne (sortie de l'étape 2), écrit les nouvelles fiches."""
```

## Décision 1 — Un seul appel de lecture, dédoublonnage en mémoire

```python
from notion_client import Client

notion = Client(auth=os.environ["NOTION_API_KEY"])

def recuperer_etat_existant(database_id: str) -> tuple[set[str], list[str]]:
    """Retourne (doi_normalises_existants, titres_normalises_existants)."""
    doi_existants, titres_existants = set(), []
    curseur = None
    while True:
        reponse = notion.databases.query(
            database_id=database_id,
            start_cursor=curseur,
            page_size=100,
        )
        for page in reponse["results"]:
            proprietes = page["properties"]
            doi = proprietes["doi_url"]["url"]
            if doi:
                doi_existants.add(normaliser_doi(doi))
            titres_existants.append(normaliser_titre(
                proprietes["titre"]["title"][0]["plain_text"] if proprietes["titre"]["title"] else ""
            ))
        if not reponse["has_more"]:
            break
        curseur = reponse["next_cursor"]
    return doi_existants, titres_existants
```

`normaliser_doi` et `normaliser_titre` sont les mêmes fonctions que celles de l'étape 2 (Décision 5 de `etape-2-conception-technique.md`) — importées depuis `etape2_recherche_extraction/dedoublonnage.py`, pas dupliquées, pour garantir que la même étude produit toujours la même clé de comparaison des deux côtés.

**Pourquoi un seul appel paginé plutôt qu'une requête `databases.query` filtrée par étude :** conforme à `etape-3-integration-notion-diagbruit.md` ("évite de multiplier les appels réseau"). L'API Notion pagine par 100 résultats maximum (`page_size`) — la boucle `while` gère cette pagination une fois pour toutes, avant tout traitement des études du run. Le volume attendu de la base (quelques dizaines à quelques centaines de fiches après plusieurs mois) reste largement compatible avec un chargement intégral en mémoire.

## Décision 2 — Dédoublonnage contre l'existant : même logique, portée élargie

```python
def est_deja_present(etude: dict, doi_existants: set[str], titres_existants: list[str]) -> bool:
    doi = normaliser_doi(etude["doi_url"]) if etude["doi_url"] else None
    if doi and doi in doi_existants:
        return True
    titre = normaliser_titre(etude["titre"])
    return any(rapidfuzz.fuzz.ratio(titre, t) >= 90 for t in titres_existants)
```

Appliqué à chaque étude de la liste reçue de l'étape 2, avant écriture. Une étude reconnue présente est retirée silencieusement de la suite (pas une erreur — comportement normal d'un run hebdomadaire, conformément à `etape-3-integration-notion-diagbruit.md`).

## Décision 3 — Écriture d'une fiche : mapping direct, propriétés typées Notion

```python
def creer_fiche(database_id: str, etude: dict) -> None:
    notion.pages.create(
        parent={"database_id": database_id},
        properties={
            "titre": {"title": [{"text": {"content": etude["titre"]}}]},
            "auteurs": {"rich_text": [{"text": {"content": etude["auteurs"]}}]},
            "annee": {"number": etude["annee"]},
            "revue": {"select": {"name": etude["revue"]}},
            "organisme": {"rich_text": [{"text": {"content": etude["organisme"]}}]},
            "doi_url": {"url": etude["doi_url"] or None},
            "domaine_sante": {"multi_select": [{"name": d} for d in etude["domaine_sante"]]},
            "source_bruit": {"multi_select": [{"name": s} for s in etude["source_bruit"]]},
            "resume": {"rich_text": [{"text": {"content": etude["resume"]}}]},
            "resultat_cle": {"rich_text": [{"text": {"content": etude["resultat_cle"]}}]},
            "statut": {"select": {"name": "🆕 Nouveau"}},
            "favori": {"checkbox": False},
        },
    )
```

`date_ajout` n'apparaît pas dans ce mapping : c'est une propriété `created_time`, calculée automatiquement par Notion à la création de la page (voir Décision 4 de `etape-1-conception-technique.md`) — la transmettre explicitement serait rejeté par l'API. Chaque type de propriété Notion (`title`, `rich_text`, `number`, `select`, `multi_select`, `url`, `checkbox`) attend une structure JSON précise et différente ; ce mapping traduit terme à terme le contrat de données de `etape-1-base-notion-diagbruit.md`, sans transformation de valeur (conforme à la Phase 3 de `etape-3-integration-notion-diagbruit.md`).

**Point d'attention — `select` sur `revue` :** contrairement à `multi_select`, une valeur `select` non déjà déclarée dans les options de la colonne est créée à la volée par l'API Notion lors de l'écriture (comportement par défaut, pas une erreur) — cohérent avec le fait que la liste des revues scientifiques rencontrées n'est pas figée à l'avance, à la différence de `domaine_sante`/`source_bruit`/`statut` dont les options sont closes (voir Décision 4 de `etape-1-conception-technique.md`).

## Décision 4 — Gestion des erreurs

`creer_fiche` est décorée `tenacity` (3 tentatives, délai exponentiel), comme les appels réseau de l'étape 2. Si elle échoue malgré tout, `executer()` journalise l'échec (`print` vers stderr, avec le titre de l'étude pour permettre un rattrapage manuel) et passe à l'étude suivante — jamais d'interruption du run pour un échec isolé, conformément à la politique retenue dans `etape-3-integration-notion-diagbruit.md`. Pas de fichier `*_erreurs.csv` dédié (spécificité déjà actée dans ce même document) : les journaux d'exécution de GitHub Actions (étape 4) suffisent au faible volume attendu.

## Dépendances retenues

- `notion-client` — lecture et écriture dans la base "Études".
- `rapidfuzz` — réutilisé de l'étape 2 pour le dédoublonnage par titre.
- `tenacity` — tentatives avec délai progressif sur l'écriture.

## Prochaine étape

Étape 4 — automatisation : planification hebdomadaire du run complet (`main.py`, étapes 2 et 3 enchaînées) via GitHub Actions.
