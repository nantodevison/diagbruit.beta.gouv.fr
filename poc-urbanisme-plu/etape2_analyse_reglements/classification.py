"""Phase 4 de l'étape 2 : classification des passages retenus via l'API Anthropic.

Un appel à `client.messages.create(...)` par passage retenu en phase 3,
plutôt qu'un traitement par lot : un échec ne fait perdre qu'une ligne,
jamais un document entier, et chaque ligne du CSV de sortie reste reliée à
un appel identifiable individuellement.

Mise à jour du 13/08/2026 par rapport au document de cadrage initial (voir
`docs/etape-2-conception-technique.md`) : le SDK officiel `anthropic` est
utilisé plutôt que `requests` brut, avec la fonctionnalité **structured
outputs** (`output_config.format`, schéma JSON) plutôt qu'un prompt
demandant "réponds en JSON". La réponse est ainsi garantie conforme au
schéma par construction — le cas "réponse JSON mal formée" que le document
de cadrage envisageait comme erreur à gérer devient marginal (il ne
subsiste qu'en cas de refus de sécurité du modèle ou de troncature
`max_tokens`, tous deux gérés explicitement ci-dessous).

Le modèle retenu est `claude-sonnet-5` : bon équilibre qualité/coût pour une
tâche de classification de texte juridique français, sachant qu'une
vérification humaine est prévue en aval (étape 5 du plan global).

Mise à jour du 13/08/2026 ("option 4", retour utilisateur après relecture
d'un premier lot de résultats) : le découpage mécanique en blocs de
`filtrage_lexical.py` (taille fixe, aveugle au sens) produisait des citations
tronquées en plein milieu d'une phrase utile, ou mélangeant deux sujets sans
rapport dans un même bloc — trois options de correction ont été comparées
(exposer tel quel `contexte_avant`/`contexte_apres` ; découper sur des
phrases plutôt que des caractères ; laisser le modèle choisir lui-même sa
citation) et la dernière a été retenue : le même appel de classification
renvoie désormais aussi `extrait_significatif`, une **citation verbatim**
choisie par le modèle dans le passage et son contexte immédiat (déjà transmis
dans le prompt, donc sans appel API supplémentaire). Elle remplace l'ancien
`extrait_occurrence` calculé mécaniquement, qui ne sert plus que de repli
(`extrait_repli`, voir `filtrage_lexical.py`) si la citation renvoyée par le
modèle ne peut pas être vérifiée comme un extrait réellement présent dans le
texte fourni (voir `_extraire_citation_verifiee` ci-dessous) — le filtre lexical de la
phase 3 reste, lui, inchangé : c'est lui qui garantit qu'aucune occurrence
contenant un mot-clé n'est manquée, l'IA n'intervenant qu'ensuite pour
choisir la meilleure citation parmi ce que le filtre a déjà repéré.

Mise à jour du 13/08/2026 (retour utilisateur, notion de "règle autonome"
précisée) : le prompt définissait jusqu'ici la notion de "règle autonome liée
au bruit" de façon vague ("hors classement sonore/PEB, déjà traités
ailleurs"), avec un indice **conditionnel** — le modèle n'était incité à
vérifier un renvoi au classement sonore/PEB que si le filtre lexical de la
phase 3 avait posé le tag `tag_exclusion`. Un cas réel (département 067,
PADD, orientation sur le bruit de l'aéroport d'Entzheim et des axes routiers)
a montré la limite : le passage évoquait bien le sujet du classement
sonore/PEB sans jamais nommer ces dispositifs, donc sans déclencher le tag —
le modèle n'a alors pas eu l'occasion de se poser la question.

Le prompt est donc désormais **systématique** sur ce point (plus de
dépendance à `tag_exclusion` pour le déclencher — le champ continue
d'exister et d'alimenter `statut_verification` en phase 5, il n'est
simplement plus injecté comme indice dans le prompt) et précise deux notions
supplémentaires, définies avec l'utilisateur :
- **Périmètre diagBruit** : une règle qui ne concerne QUE un projet
  d'infrastructure de transport (pas des bâtiments ni l'aménagement à
  proximité) reste retenue mais avec `confiance_extrait = "faible"`.
- **Renvoi simple vs règle autonome (classement sonore/PEB)** : le test
  n'est plus "le passage cite-t-il ces dispositifs ?" mais "le passage
  se limite-t-il à rappeler l'isolement acoustique standard qu'ils imposent,
  ou bien le secteur qu'ils délimitent sert-il de simple repère géographique
  à une règle différente ?" — seul le second cas est une règle autonome.

Choix assumé pour `confiance_extrait` : ce champ mesurait jusqu'ici seulement
la clarté de la citation (`extrait_significatif`) ; il sert désormais aussi à
signaler une règle hors périmètre bâtiment/aménagement, deux raisons
différentes de valoir "faible". Plutôt que d'ajouter une colonne dédiée, la
consigne exige que `justification` précise laquelle des deux s'applique —
voir `etape-2-ameliorations-possibles.md` pour la piste d'un champ séparé si
ce choix s'avère gênant à l'usage.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import anthropic
from anthropic import Anthropic
from dotenv import load_dotenv
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .filtrage_lexical import PassageRetenu
from .resolution_pieces import ErreurTraitement

load_dotenv()


class CleApiManquante(Exception):
    """ANTHROPIC_API_KEY absente de l'environnement ou du fichier .env."""


if not os.environ.get("ANTHROPIC_API_KEY"):
    raise CleApiManquante(
        "ANTHROPIC_API_KEY n'est pas définie. Copier .env.example vers .env "
        "à la racine de poc-urbanisme-plu/ et y renseigner une clé créée sur "
        "la Console Anthropic (console.anthropic.com)."
    )

client = Anthropic()

MODELE_CLASSIFICATION = "claude-sonnet-5"

SCHEMA_CLASSIFICATION = {
    "type": "object",
    "properties": {
        "retenu": {"type": "boolean"},
        # Un enum nullable doit s'exprimer via anyOf (une branche string+enum,
        # une branche null) — "type": ["string", "null"] combiné à "enum" est
        # rejeté par le validateur de schéma de l'API (testé en réel : 400
        # "Enum value ... does not match declared type").
        "nature_occurrence": {
            "anyOf": [
                {"type": "string", "enum": ["prescription", "recommandation"]},
                {"type": "null"},
            ]
        },
        "nature_sonore_zone": {
            "anyOf": [
                {"type": "string", "enum": ["lutte_bruit_existant", "preservation_zone_calme", "autre"]},
                {"type": "null"},
            ]
        },
        "zone_reglementaire_mentionnee": {"type": ["string", "null"]},
        "justification": {"type": "string"},
        # Ajouté le 13/08/2026 ("option 4", retour utilisateur) : citation
        # verbatim choisie par le modèle dans le passage et son contexte
        # immédiat, qui remplace le découpage mécanique en tant qu'extrait
        # affiché — voir le docstring du module et `_extraire_citation_verifiee`.
        "extrait_significatif": {"type": ["string", "null"]},
        # Le découpage automatique en paragraphes (voir `filtrage_lexical.py`)
        # produit parfois un extrait qui mélange plusieurs sujets ou coupe une
        # phrase — un score de confiance sur la lisibilité/autonomie de
        # l'extrait aide le relecteur humain à prioriser sa vérification.
        "confiance_extrait": {
            "anyOf": [
                {"type": "string", "enum": ["faible", "moyenne", "forte", "totale"]},
                {"type": "null"},
            ]
        },
    },
    "required": [
        "retenu",
        "nature_occurrence",
        "nature_sonore_zone",
        "zone_reglementaire_mentionnee",
        "justification",
        "extrait_significatif",
        "confiance_extrait",
    ],
    "additionalProperties": False,
}


@dataclass
class OccurrenceClassifiee:
    passage: PassageRetenu
    retenu: bool
    nature_occurrence: str | None
    nature_sonore_zone: str | None
    zone_reglementaire_mentionnee: str | None
    justification: str
    extrait_significatif: str | None
    confiance_extrait: str | None


class _ErreurClassification(Exception):
    """Échec de l'appel de classification pour un passage donné."""


def _normaliser_espaces(texte: str) -> str:
    return re.sub(r"\s+", " ", texte).strip()


def _extraire_citation_verifiee(donnees: dict, passage: PassageRetenu) -> str | None:
    """Retourne la citation du modèle si elle est bien un extrait verbatim du
    texte fourni (contexte avant + passage + contexte après), sinon retombe
    sur `extrait_repli` (repli mécanique, voir `filtrage_lexical.py`). Un
    modèle qui reformule malgré la consigne ne doit jamais faire perdre
    l'occurrence — seulement dégrader la citation affichée."""
    if not donnees["retenu"]:
        return None

    citation = donnees["extrait_significatif"]
    if not citation:
        return passage.extrait_repli

    texte_source = _normaliser_espaces(
        f"{passage.contexte_avant} {passage.passage_texte} {passage.contexte_apres}"
    )
    if _normaliser_espaces(citation) in texte_source:
        return citation.strip()

    return passage.extrait_repli


def _construire_prompt(passage: PassageRetenu) -> str:
    return f"""Tu analyses un extrait d'un document d'urbanisme français ({passage.piece.type_piece_source})
pour repérer des règles autonomes liées au bruit, dans le périmètre de
diagBruit : les projets de construction de bâtiments et les projets
d'aménagement urbain. Une règle qui ne concerne QUE la réalisation d'une
infrastructure de transport elle-même (voirie, voie ferrée...), sans rapport
avec des bâtiments ou l'urbanisation à proximité, reste à signaler
(retenu=true) mais avec une confiance faible (voir plus bas) — précise-le
explicitement dans justification.

Le classement sonore des voies et le plan d'exposition au bruit (PEB) d'un
aéroport sont déjà traités ailleurs par diagBruit : la mention d'un secteur
affecté par le bruit de ces infrastructures classées n'est donc PAS
automatiquement une règle autonome. Distingue deux cas :
- Simple renvoi (retenu=false) : le passage se contente de rappeler que
  l'isolement acoustique standard prévu par l'arrêté préfectoral (classement
  sonore) ou par le PEB s'applique dans ce secteur — aucune règle propre au
  document d'urbanisme n'est ajoutée.
- Règle autonome (retenu=true) : le secteur défini par le classement sonore
  ou le PEB sert de simple repère géographique pour une règle DIFFÉRENTE de
  l'isolement acoustique standard, ou une exigence d'isolement qui va
  au-delà de celle prévue par l'arrêté/le PEB.

Contexte avant : {passage.contexte_avant}
PASSAGE À ANALYSER : {passage.passage_texte}
Contexte après : {passage.contexte_apres}

Le passage a été extrait automatiquement d'un PDF et son découpage en blocs
n'est pas toujours fiable : il peut mélanger plusieurs sujets, être coupé en
milieu de phrase, ou juxtaposer une énumération peu claire. Le "Contexte
avant" et le "Contexte après" ci-dessus sont les blocs qui précèdent et
suivent immédiatement le passage dans le document — utilise-les si la règle
liée au bruit y déborde (phrase commencée dans le contexte avant, terminée
dans le contexte après, etc.), et pour juger si le passage relève ou non du
périmètre diagBruit et du cas "simple renvoi" ci-dessus.

Si retenu=true, remplis extrait_significatif : une **citation verbatim**,
copiée exactement (aucune reformulation, aucun résumé) depuis le contexte
avant, le passage, et/ou le contexte après ci-dessus, qui isole le plus
précisément possible la prescription ou recommandation liée au bruit — aussi
courte que possible tout en restant compréhensible seule, sans mélanger un
autre sujet sans rapport. Si retenu=false, mets extrait_significatif à null.

Indique aussi dans confiance_extrait à quel point l'extrait que tu as choisi
exprime de façon claire et autonome (sans qu'il faille deviner ou
reconstituer du contexte manquant) la prescription ou recommandation liée au
bruit :
- "faible" : soit un fragment peu clair, coupé, ou mélangeant plusieurs
  sujets sans qu'on distingue clairement la règle ; soit une règle qui ne
  concerne que l'infrastructure de transport elle-même, pas des bâtiments ni
  l'aménagement (les deux raisons sont à distinguer dans justification) ;
- "moyenne" : la règle est devinable mais l'extrait manque de netteté ou de
  contexte pour être cité tel quel ;
- "forte" : la règle est claire, avec une formulation encore un peu
  incomplète ou approximative ;
- "totale" : formulation complète, autonome et non ambiguë, citable telle
  quelle.
Si retenu=false, mets confiance_extrait à null."""


@retry(
    retry=retry_if_exception_type(
        (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError)
    ),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _appeler_claude(prompt: str) -> anthropic.types.Message:
    return client.messages.create(
        model=MODELE_CLASSIFICATION,
        # Relevé à 800 le 13/08/2026 (500 jusque-là) : le prompt précisant la
        # notion de "règle autonome" (périmètre diagBruit, distinction
        # renvoi simple/règle autonome) demande au modèle une justification
        # plus détaillée, ce qui a fait apparaître des réponses tronquées
        # (stop_reason=max_tokens) sur quelques passages en test réel.
        max_tokens=800,
        # claude-sonnet-5 réfléchit par défaut (adaptive thinking) dès lors
        # que `thinking` n'est pas précisé, et ce raisonnement est décompté
        # de `max_tokens` même s'il n'est pas affiché — constaté en réel
        # (13/08/2026) : deux passages sur les premiers testés se sont
        # terminés en `stop_reason=max_tokens` avant même de produire la
        # réponse JSON. La tâche de classification ne nécessite pas de
        # raisonnement approfondi ; le désactiver laisse tout le budget de
        # tokens à la réponse et réduit coût et latence.
        thinking={"type": "disabled"},
        output_config={"format": {"type": "json_schema", "schema": SCHEMA_CLASSIFICATION}},
        messages=[{"role": "user", "content": prompt}],
    )


def classifier_passage(passage: PassageRetenu) -> OccurrenceClassifiee:
    """Classifie un passage retenu. Lève `_ErreurClassification` en cas
    d'échec (appel API, refus de sécurité, sortie tronquée)."""
    prompt = _construire_prompt(passage)

    try:
        response = _appeler_claude(prompt)
    except anthropic.APIError as exc:
        raise _ErreurClassification(f"appel API échoué : {exc}") from exc

    if response.stop_reason == "refusal":
        raise _ErreurClassification("le modèle a refusé de répondre (stop_reason=refusal)")
    if response.stop_reason == "max_tokens":
        raise _ErreurClassification("réponse tronquée (stop_reason=max_tokens)")

    try:
        texte_reponse = next(bloc.text for bloc in response.content if bloc.type == "text")
        donnees = json.loads(texte_reponse)
    except (StopIteration, json.JSONDecodeError) as exc:
        raise _ErreurClassification(f"réponse inexploitable : {exc}") from exc

    return OccurrenceClassifiee(
        passage=passage,
        retenu=donnees["retenu"],
        nature_occurrence=donnees["nature_occurrence"],
        nature_sonore_zone=donnees["nature_sonore_zone"],
        zone_reglementaire_mentionnee=donnees["zone_reglementaire_mentionnee"],
        justification=donnees["justification"],
        extrait_significatif=_extraire_citation_verifiee(donnees, passage),
        confiance_extrait=donnees["confiance_extrait"],
    )


def classifier_departement(
    passages: list[PassageRetenu],
) -> tuple[list[OccurrenceClassifiee], list[ErreurTraitement]]:
    """Classifie chaque passage retenu (phase 4 complète).

    Ne lève jamais d'exception : tout échec de classification est isolé et
    empilé dans la liste d'erreurs retournée, le reste du département
    continue d'être traité.
    """
    occurrences: list[OccurrenceClassifiee] = []
    erreurs: list[ErreurTraitement] = []

    for passage in passages:
        try:
            occurrences.append(classifier_passage(passage))
        except _ErreurClassification as exc:
            erreurs.append(
                ErreurTraitement(
                    passage.piece.id_gpu,
                    passage.piece.lien_web_document,
                    "4-classification",
                    "appel_claude",
                    str(exc),
                    contenu_brut=passage.extrait_repli,
                )
            )

    return occurrences, erreurs
