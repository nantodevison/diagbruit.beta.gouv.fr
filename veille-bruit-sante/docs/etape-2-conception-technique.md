# Étape 2 — Conception technique : recherche hebdomadaire et extraction structurée

*Document de cadrage technique, faisant suite à `etape-2-recherche-extraction-diagbruit.md` et à `etape-1-conception-technique.md`.*

## Point d'entrée du module

```python
# etape2_recherche_extraction/main.py (appelé par main.py à la racine)
def executer(date_depuis: date) -> list[dict]:
    """Retourne la liste des études trouvées et dédoublonnées, prêtes pour l'étape 3."""
```

`date_depuis` est calculée par `main.py` (Décision 3 de `etape-1-conception-technique.md`), jamais recalculée ici : ce module reste agnostique de la façon dont la date a été obtenue.

## Décision 1 — Deux fonctions de recherche indépendantes, résultats fusionnés ensuite

`recherche_apis.py` (canal API scientifiques) et `recherche_web.py` (canal `web_search`) sont deux fonctions sans dépendance l'une envers l'autre, chacune retournant une liste d'études au même format brut (avant extraction structurée). Le dédoublonnage interne (Décision 4) intervient seulement après, sur la liste fusionnée.

**Pourquoi les garder séparées plutôt qu'une seule fonction "recherche" qui déciderait en interne quel canal utiliser :** les deux canaux ont des modes d'échec complètement différents (une API REST classique contre un appel à l'API Anthropic avec outil serveur) — les mélanger dans une seule fonction rendrait la gestion d'erreur (Décision 5) illisible. Un canal en échec total ne doit jamais empêcher l'autre de produire des résultats.

## Décision 2 — Canal API scientifiques : OpenAlex en principal, Europe PMC en complément

Les deux API sont interrogées, sans clé requise pour aucune des deux :

| API | Endpoint | Requête |
|---|---|---|
| OpenAlex | `https://api.openalex.org/works` | `search=bruit+noise+health OR bruit+santé`, `filter=from_publication_date:{date_depuis},to_publication_date:{aujourd'hui}` |
| Europe PMC | `https://www.ebi.ac.uk/europepmc/webservices/rest/search` | `query=(noise OR bruit) AND (health OR santé) AND FIRST_PDATE:[{date_depuis} TO {aujourd'hui}]`, `format=json` |

**Pourquoi les deux plutôt qu'une seule :** OpenAlex a une couverture plus large (toutes disciplines, tous éditeurs indexés) mais un plein texte moins systématiquement disponible ; Europe PMC est spécialisé biomédical, avec accès au résumé structuré plus fiable pour cette thématique précise. Les deux remontent en partie les mêmes articles (normal, traité au dédoublonnage) mais chacun trouve aussi des articles absents de l'autre.

**Filtrage géographique — Europe :** aucune des deux API n'offre de filtre fiable "études portant sur une population européenne" (l'affiliation institutionnelle des auteurs n'indique pas la population étudiée). Le filtrage se fait donc **après coup, à l'extraction structurée** (Décision 3) : le prompt d'extraction demande explicitement au modèle de vérifier ce critère à partir du résumé, et une étude hors périmètre est écartée à ce stade plutôt qu'en amont. Point de vigilance retenu, à réévaluer si le volume d'études hors-périmètre s'avère trop élevé en usage réel.

Chaque appel utilise `requests` avec un en-tête `User-Agent` identifiant le projet (bonne pratique attendue par ces deux API, notamment pour l'accès à la "pool polie" d'OpenAlex, plus rapide) — pas de clé API à gérer pour ce canal.

## Décision 3 — Canal `web_search` : un seul appel, prompt daté explicitement

```python
from anthropic import Anthropic

client = Anthropic()
message = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=4096,
    tools=[{
        "type": "web_search_20250305",
        "name": "web_search",
        "allowed_domains": domaines,  # liste à plat, chargée depuis config/domains_whitelist.yaml
    }],
    messages=[{
        "role": "user",
        "content": (
            f"Recherche les publications et rapports institutionnels sur le lien entre "
            f"bruit et santé, publiés entre le {date_depuis.isoformat()} et le "
            f"{date.today().isoformat()}, portant sur l'Europe ou des populations "
            f"européennes. Pour chaque source trouvée, indique son URL exacte."
        ),
    }],
)
```

`allowed_domains` est chargé une seule fois par run depuis `config/domains_whitelist.yaml` (aplati : toutes les catégories du fichier fusionnées en une seule liste de domaines, les catégories n'existant que pour la lisibilité humaine du fichier — voir son en-tête). La date est toujours injectée en toutes lettres dans le prompt (jamais "depuis la dernière fois"), conformément au point de vigilance retenu dans `plan-veille-bruit-sante-diagbruit.md`.

**Pourquoi un seul appel plutôt qu'un appel par domaine ou par catégorie :** `web_search` gère lui-même plusieurs recherches et itérations dans un seul appel (le modèle peut relancer l'outil plusieurs fois dans la même réponse) — le découper artificiellement en plusieurs appels multiplierait le coût sans gain de couverture, `allowed_domains` s'appliquant déjà à l'ensemble de la liste en une fois.

**Extraction du résultat :** la réponse de `web_search` mélange texte de synthèse et citations de sources (blocs `web_search_tool_result` dans `message.content`). Plutôt que de parser ce texte libre pour en extraire une liste structurée, ce premier appel sert uniquement à **identifier des URLs de sources pertinentes** ; l'extraction structurée proprement dite (titre, auteurs, résumé...) est déléguée à la Décision 4, un appel dédié par étude trouvée — voir "Pourquoi deux appels" ci-dessous.

## Décision 4 — Extraction structurée : un appel par étude, sorties structurées

Pour chaque étude retenue (des deux canaux confondus, avant dédoublonnage), un appel à l'API Anthropic avec **structured outputs** (`output_config.format`), sur le même principe que la classification de `poc-urbanisme-plu/etape2_analyse_reglements` (voir `poc-urbanisme-plu/docs/etape-2-conception-technique.md`, section "Appel de classification") : réponse garantie conforme au schéma par construction, sans prompt "réponds en JSON" ni parsing défensif.

Schéma de sortie — reprend exactement les colonnes de `etape-1-base-notion-diagbruit.md` :

```python
schema = {
    "type": "object",
    "properties": {
        "hors_perimetre": {"type": "boolean"},  # true si hors Europe ou hors thématique bruit/santé
        "titre": {"type": "string"},
        "auteurs": {"type": "string"},
        "annee": {"type": "integer"},
        "revue": {"type": "string"},
        "organisme": {"type": "string"},
        "doi_url": {"type": "string"},
        "domaine_sante": {"type": "array", "items": {"type": "string"}},
        "source_bruit": {"type": "array", "items": {"type": "string"}},
        "resume": {"type": "string"},
        "resultat_cle": {"type": "string"},
    },
    "required": ["hors_perimetre", "titre", "doi_url"],
}
```

`hors_perimetre` porte le filtrage géographique/thématique évoqué en Décision 2 : une étude marquée `true` est écartée avant même d'atteindre le dédoublonnage — ses autres champs ne sont alors pas exploités. Le prompt transmet à l'API le contenu disponible pour l'étude (résumé OpenAlex/Europe PMC pour le canal API, ou l'URL + le contexte trouvé par `web_search` pour le canal web) et demande la rédaction du `resume` (2-3 phrases) et du `resultat_cle` à partir de ce contenu — jamais recopiés tels quels, conformément à `etape-2-recherche-extraction-diagbruit.md`.

**Pourquoi un appel par étude plutôt qu'un appel unique qui structurerait toute la liste d'un coup :** un échec isolé (contenu insuffisant pour une étude donnée, timeout) ne fait perdre qu'une étude, jamais tout le lot de la semaine — cohérent avec la politique de gestion des erreurs retenue au projet (Décision 5). Le volume attendu (quelques études par semaine, voir `etape-3-integration-notion-diagbruit.md`) rend ce surcoût d'appels négligeable.

## Décision 5 — Dédoublonnage interne : DOI normalisé, puis titre normalisé

```python
def normaliser_doi(doi_url: str) -> str:
    return doi_url.lower().removeprefix("https://doi.org/").removeprefix("http://doi.org/").strip("/")

def normaliser_titre(titre: str) -> str:
    return re.sub(r"[^\w\s]", "", titre.lower()).strip()
```

Deux études sont considérées identiques si leurs DOI normalisés sont égaux et non vides, sinon si leurs titres normalisés dépassent un seuil de similarité (`rapidfuzz.fuzz.ratio`, seuil retenu : 90). En cas de doublon entre les deux canaux, l'étude issue du canal API scientifiques est conservée en priorité (métadonnées structurées, DOI systématique) ; celle du canal web sert de repli si aucune des deux ne vient de ce canal.

**Pourquoi `rapidfuzz` plutôt qu'une égalité stricte de titre :** deux sources peuvent citer un même titre avec une ponctuation ou une casse légèrement différente (sous-titre tronqué, apostrophe typographique) — une égalité stricte laisserait passer des doublons évidents à l'œil humain.

## Décision 6 — Gestion des erreurs

Reprend la politique du projet (voir `etape-1-conception-technique.md`, posture, et `etape-3-integration-notion-diagbruit.md`) : `tenacity` (3 tentatives, délai exponentiel) sur chaque appel réseau individuel (un appel OpenAlex, un appel Europe PMC, l'appel `web_search`, un appel d'extraction). Un canal de recherche entièrement en échec après ses tentatives ne bloque pas l'autre — `executer()` retourne la liste construite à partir du ou des canaux qui ont fonctionné, avec un `print`/log signalant le canal en échec. Une étude dont l'extraction structurée échoue est écartée du run (journalisée), plutôt que transmise à l'étape 3 avec des champs incomplets.

## Dépendances retenues

- `anthropic` — `web_search` et extraction structurée.
- `requests` — OpenAlex, Europe PMC.
- `rapidfuzz` — comparaison de similarité de titres (dédoublonnage).
- `tenacity` — tentatives avec délai progressif.
- `pyyaml` — lecture de `config/domains_whitelist.yaml`.

## Prochaine étape

Étape 3 — intégration Notion : dédoublonnage contre l'existant et écriture des nouvelles fiches à partir de la liste produite par ce module.
