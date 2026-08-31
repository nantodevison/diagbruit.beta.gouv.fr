"""Phase 2 (etape 2) — extraction structurée, un appel API par étude candidate.

Voir etape-2-conception-technique.md, Décision 4. Utilise `client.messages.parse` (sorties
structurées via Pydantic) : la réponse est garantie conforme au schéma par construction,
sans prompt "réponds en JSON" ni parsing défensif.
"""
from typing import List, Literal, Optional

from anthropic import Anthropic
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from etape1_base_notion.creer_base_notion import (
    OPTIONS_DOMAINE_SANTE, OPTIONS_SOURCE_BRUIT, OPTIONS_URL_SOURCE,
)

MODELE = "claude-sonnet-5"

DomaineSante = Literal[OPTIONS_DOMAINE_SANTE]  # type: ignore[valid-type]
SourceBruit = Literal[OPTIONS_SOURCE_BRUIT]  # type: ignore[valid-type]

_API_METIER, _CLAUDE_WEB_SEARCH, _CLAUDE_LLM = OPTIONS_URL_SOURCE


class EtudeExtraite(BaseModel):
    hors_perimetre: bool
    titre: str
    auteurs: str = ""
    annee: Optional[int] = None
    revue: str = ""
    organisme: str = ""
    doi_url: str = ""
    domaine_sante: List[DomaineSante] = []
    source_bruit: List[SourceBruit] = []
    resume: str = ""
    resultat_cle: str = ""


# Instructions fixes, identiques a chaque appel du run — isolees du contenu variable de
# chaque source pour beneficier du cache de prompt (etape2_recherche_extraction, echange
# du 2026-08-28 sur le cout des appels Anthropic) : passees en `system` avec
# cache_control, elles ne sont facturees plein tarif qu'une fois par run, puis relues a
# ~10% du prix pour chaque etude suivante. Elles doivent rester au-dessus du seuil minimal
# de mise en cache du modele (1024 tokens pour Sonnet 5) pour que le cache s'active — voir
# le print de diagnostic dans executer(), qui rapporte cache_read_input_tokens a chaque
# run pour verifier que c'est bien le cas plutot que de le supposer.
#
# BROUILLON — l'exemple et le contre-exemple ci-dessous sont a valider avant un run reel
# (echange du 2026-08-28) : ils illustrent le format attendu mais n'ont pas ete relus.
PROMPT_SYSTEME = """Tu extrais les metadonnees structurees d'une etude scientifique ou d'un \
rapport institutionnel candidat a une veille documentaire sur le lien entre bruit et sante.

## Critere hors_perimetre

Mets hors_perimetre a true si au moins une des conditions suivantes est vraie (dans ce cas \
les autres champs peuvent rester vides) :
- la population etudiee n'est pas europeenne et l'etude ne peut pas etre raisonnablement \
generalisee a des populations europeennes (climat, mode de vie, reglementation acoustique \
tres differents) ;
- il n'y a pas de lien direct et mesure entre une exposition au bruit et un effet sur la \
sante physique ou mentale — un article sur la seule mesure acoustique, sans volet \
sanitaire, est hors perimetre ;
- le document est un protocole d'etude ou d'essai clinique sans resultats — par exemple \
une fiche d'enregistrement ClinicalTrials.gov ou un document methodologique (souvent nomme \
"Prot_000.pdf" ou similaire) qui decrit un objectif, une methodologie et des criteres \
d'inclusion prevus, sans aucune donnee ni resultat rapporte : il n'y a alors rien a \
extraire tant que l'essai n'a pas produit de resultats publies ;
- l'exposition etudiee est une exposition professionnelle au bruit (bruit au poste de \
travail, risque auditif professionnel, reglementation de securite au travail, medecine du \
travail) — meme si l'etude traite bien de sante, le bruit professionnel est totalement \
hors du perimetre de cette veille, qui ne porte que sur l'exposition environnementale et \
residentielle des populations ;
- le contenu disponible est trop insuffisant pour juger du perimetre (resume absent ou non \
pertinent).

Cas limites :
- une etude multi-pays incluant au moins un pays europeen reste dans le perimetre, meme si \
la majorite des participants sont hors Europe ;
- une etude nord-americaine ou asiatique sur une population comparable (pays a revenu \
eleve, exposition urbaine au bruit routier/aerien) est acceptee par defaut, sauf mention \
contraire — le doute profite a l'inclusion, la revue humaine tranchera ensuite dans Notion ;
- attention a la distinction avec source_bruit = Industriel : une etude sur le bruit \
industriel percu par les riverains d'un site (exposition environnementale) reste dans le \
perimetre ; une etude sur l'exposition sonore des salaries a l'interieur de ce meme site \
(exposition professionnelle) est hors perimetre ;
- un essai clinique reste dans le perimetre des lors qu'un resultat est rapporte (section \
"Results" renseignee sur ClinicalTrials.gov, publication associee, rapport intermediaire \
avec donnees) — seule l'absence totale de resultat exploitable rend hors_perimetre.

## doi_url

Ne propose une valeur pour doi_url que si elle apparait telle quelle, caractere pour \
caractere, dans le "Contenu disponible" fourni ci-dessous — jamais reconstituee ou devinee \
de memoire, meme si tu penses reconnaitre l'etude. Si aucune URL/DOI exact n'apparait dans \
le contenu disponible, laisse doi_url vide : le DOI/URL trouve lors de la recherche sera \
conserve tel quel plutot que remplace par une valeur non verifiee. La verification que \
cette URL repond reellement est faite ensuite par un controle technique separe, hors de ta \
portee ici — inutile donc d'evaluer ou de commenter sa validite.

## Domaine et source du bruit

domaine_sante et source_bruit doivent etre choisis uniquement parmi les valeurs autorisees \
du schema (ne rien inventer), en retenant celles qui s'appliquent meme partiellement — une \
etude peut cumuler plusieurs valeurs sur les deux champs. Definitions :

domaine_sante :
- Cardiovasculaire : hypertension, maladies coronariennes, AVC, arythmies.
- Sante mentale : anxiete, depression, stress percu, qualite de vie psychologique.
- Cognition : attention, memoire, performances scolaires, fonctions executives.
- Metabolique : diabete, obesite, syndrome metabolique.
- Sommeil : latence d'endormissement, reveils nocturnes, qualite du sommeil rapportee ou \
mesuree.
- Enfant : tout effet specifique etudie chez une population pediatrique (0-17 ans), quel \
que soit le domaine de sante concerne.

source_bruit :
- Routier : trafic automobile, poids lourds, deux-roues.
- Aerien : avions, aeroports, helicopteres.
- Ferroviaire : trains, trams, metros aeriens.
- Industriel : usines, chantiers, activites industrielles ou artisanales.

## Resume et resultat cle

resume (2-3 phrases) et resultat_cle doivent etre rediges par toi, dans un francais neutre \
et factuel, jamais recopies tels quels d'une source.

## Exemple

Entree :
Titre (tel que trouve) : Long-term exposure to road traffic noise and incident \
hypertension: a prospective cohort study in six European countries
DOI/URL (tel que trouve) : https://doi.org/10.1000/exemple.2025.001
Auteurs (tel que trouve) : Dubois M et al.
Annee (telle que trouvee) : 2025
Revue (telle que trouvee) : Environmental Health Perspectives
Contenu disponible : Cohorte de 45 000 participants dans six pays europeens suivis pendant \
10 ans. L'exposition chronique au bruit routier nocturne (Lden > 55 dB) est associee a une \
augmentation de 18% du risque d'hypertension incidente, apres ajustement sur la pollution \
de l'air et le statut socio-economique.

Sortie attendue :
hors_perimetre: false
titre: "Long-term exposure to road traffic noise and incident hypertension: a prospective \
cohort study in six European countries"
auteurs: "Dubois M et al."
annee: 2025
revue: "Environmental Health Perspectives"
organisme: ""
doi_url: "https://doi.org/10.1000/exemple.2025.001"
domaine_sante: ["Cardiovasculaire"]
source_bruit: ["Routier"]
resume: "Cette cohorte prospective menee dans six pays europeens sur 45 000 participants \
montre qu'une exposition chronique au bruit routier nocturne est associee a un risque \
accru d'hypertension. L'association reste significative apres ajustement sur la pollution \
de l'air et le statut socio-economique."
resultat_cle: "Une exposition nocturne au bruit routier (Lden > 55 dB) augmente de 18% le \
risque d'hypertension incidente."

Contre-exemple (hors perimetre) : une etude portant sur des methodes de mesure acoustique \
en usine, sans aucune donnee de sante humaine, meme si elle mentionne le bruit industriel, \
est hors_perimetre = true : il n'y a pas de lien direct avec la sante, seulement une \
caracterisation technique du bruit."""


def _construire_prompt(source: dict) -> str:
    """Ne contient que les donnees propres a cette source — tout ce qui est identique
    d'un appel a l'autre est dans PROMPT_SYSTEME (voir sa docstring)."""
    contenu = source.get("resume_brut") or source.get("contexte_synthese") or ""
    return (
        "Voici les informations disponibles sur une publication candidate a une veille "
        "bruit et sante :\n\n"
        f"Titre (tel que trouve) : {source.get('titre', '')}\n"
        f"DOI/URL (tel que trouve) : {source.get('doi_url', '')}\n"
        f"Auteurs (tel que trouve) : {source.get('auteurs', '')}\n"
        f"Annee (telle que trouvee) : {source.get('annee', '')}\n"
        f"Revue (telle que trouvee) : {source.get('revue', '')}\n"
        f"Contenu disponible : {contenu}"
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def extraire(source: dict):
    client = Anthropic()
    reponse = client.messages.parse(
        model=MODELE,
        max_tokens=1500,
        system=[{
            "type": "text",
            "text": PROMPT_SYSTEME,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": _construire_prompt(source)}],
        output_format=EtudeExtraite,
    )
    if reponse.parsed_output is None:
        raise ValueError(f"parsed_output vide (stop_reason={reponse.stop_reason})")
    return reponse.parsed_output, reponse.usage


def executer(sources: list[dict]) -> list[dict]:
    """Extraction structurée pour chaque source candidate (des deux canaux confondus).
    Un échec isolé écarte seulement cette source, jamais tout le lot — voir
    etape-2-conception-technique.md, Décision 6."""
    etudes: list[dict] = []
    tokens_caches_lus = 0
    tokens_caches_ecrits = 0

    for source in sources:
        try:
            extraite, usage = extraire(source)
        except Exception as erreur:
            print(f"[etape2][extraction] echec pour '{source.get('titre', '?')}' : {erreur}")
            continue

        tokens_caches_lus += getattr(usage, "cache_read_input_tokens", 0) or 0
        tokens_caches_ecrits += getattr(usage, "cache_creation_input_tokens", 0) or 0

        if extraite.hors_perimetre:
            continue

        etude = extraite.model_dump(exclude={"hors_perimetre"})
        etude["canal"] = source.get("canal", "")

        doi_source = source.get("doi_url", "")
        doi_llm = etude["doi_url"]
        # Garde le DOI/URL d'origine si l'extraction n'en a pas trouve de plus precis.
        etude["doi_url"] = doi_llm or doi_source
        # url_source doit etre determine ici, pas au moment de la recherche : c'est le seul
        # endroit ou l'on sait si le LLM d'extraction a remplace l'URL d'origine par une
        # autre (auquel cas la fiabilite de l'URL finale ne depend plus du canal de
        # recherche d'origine, meme pour une etude venue d'une API scientifique).
        if doi_llm and doi_llm != doi_source:
            etude["url_source"] = _CLAUDE_LLM
        else:
            etude["url_source"] = _API_METIER if source.get("canal") == "api" else _CLAUDE_WEB_SEARCH

        etudes.append(etude)

    if sources:
        # Verification empirique du cache (shared/prompt-caching.md : "Verifier a partir
        # de l'usage, pas de la relecture du code") — si tokens_caches_lus reste a 0 sur
        # plusieurs sources, PROMPT_SYSTEME est soit trop court (< 1024 tokens pour
        # Sonnet 5), soit invalide par un contenu variable qui s'y serait glisse.
        print(
            f"[etape2][extraction] cache prompt : {tokens_caches_lus} tokens lus, "
            f"{tokens_caches_ecrits} tokens ecrits sur {len(sources)} appel(s)."
        )

    return etudes
