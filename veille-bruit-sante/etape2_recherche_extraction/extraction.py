"""Phase 2 (etape 2) — extraction structurée, un appel API par étude candidate.

Voir etape-2-conception-technique.md, Décision 4. Utilise `client.messages.parse` (sorties
structurées via Pydantic) : la réponse est garantie conforme au schéma par construction,
sans prompt "réponds en JSON" ni parsing défensif.
"""
from typing import List, Literal, Optional

from anthropic import Anthropic
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from etape1_base_notion.creer_base_notion import OPTIONS_DOMAINE_SANTE, OPTIONS_SOURCE_BRUIT

MODELE = "claude-sonnet-5"

DomaineSante = Literal[OPTIONS_DOMAINE_SANTE]  # type: ignore[valid-type]
SourceBruit = Literal[OPTIONS_SOURCE_BRUIT]  # type: ignore[valid-type]


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


def _construire_prompt(source: dict) -> str:
    contenu = source.get("resume_brut") or source.get("contexte_synthese") or ""
    return (
        "Voici les informations disponibles sur une publication candidate a une veille "
        "bruit et sante :\n\n"
        f"Titre (tel que trouve) : {source.get('titre', '')}\n"
        f"DOI/URL (tel que trouve) : {source.get('doi_url', '')}\n"
        f"Auteurs (tel que trouve) : {source.get('auteurs', '')}\n"
        f"Annee (telle que trouvee) : {source.get('annee', '')}\n"
        f"Revue (telle que trouvee) : {source.get('revue', '')}\n"
        f"Contenu disponible : {contenu}\n\n"
        "Mets hors_perimetre a true si cette etude ne porte pas sur l'Europe ou des "
        "populations europeennes, ou si elle n'a pas de lien direct entre bruit et sante "
        "(dans ce cas les autres champs peuvent rester vides). Sinon, complete tous les "
        "champs demandes a partir du contenu disponible. domaine_sante et source_bruit "
        "doivent etre choisis uniquement parmi les valeurs autorisees du schema (ne rien "
        "inventer), en retenant celles qui s'appliquent meme partiellement. Le resume "
        "(2-3 phrases) et le resultat_cle doivent etre rediges par toi, jamais recopies "
        "tels quels d'une source."
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def extraire(source: dict) -> EtudeExtraite:
    client = Anthropic()
    reponse = client.messages.parse(
        model=MODELE,
        max_tokens=1500,
        messages=[{"role": "user", "content": _construire_prompt(source)}],
        output_format=EtudeExtraite,
    )
    if reponse.parsed_output is None:
        raise ValueError(f"parsed_output vide (stop_reason={reponse.stop_reason})")
    return reponse.parsed_output


def executer(sources: list[dict]) -> list[dict]:
    """Extraction structurée pour chaque source candidate (des deux canaux confondus).
    Un échec isolé écarte seulement cette source, jamais tout le lot — voir
    etape-2-conception-technique.md, Décision 6."""
    etudes: list[dict] = []

    for source in sources:
        try:
            extraite = extraire(source)
        except Exception as erreur:
            print(f"[etape2][extraction] echec pour '{source.get('titre', '?')}' : {erreur}")
            continue

        if extraite.hors_perimetre:
            continue

        etude = extraite.model_dump(exclude={"hors_perimetre"})
        etude["canal"] = source.get("canal", "")
        # Garde le DOI/URL d'origine si l'extraction n'en a pas trouve de plus precis.
        etude["doi_url"] = etude["doi_url"] or source.get("doi_url", "")
        etudes.append(etude)

    return etudes
