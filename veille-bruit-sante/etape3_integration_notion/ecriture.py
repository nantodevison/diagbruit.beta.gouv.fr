"""Phase 3 (etape 3) — écriture des nouvelles fiches dans la base Notion "Études".

Mapping direct des champs extraits à l'étape 2, sans transformation — voir
etape-3-conception-technique.md, Décision 3. `date_ajout` n'apparaît pas ici : propriété
`created_time`, calculée automatiquement par Notion à la création de la page.
"""
from typing import Optional

from notion_client import Client
from tenacity import retry, stop_after_attempt, wait_exponential


def _texte_riche(valeur: Optional[str]) -> list[dict]:
    return [{"text": {"content": valeur or ""}}]


def _nettoyer_option_select(valeur: Optional[str]) -> Optional[str]:
    """Notion refuse toute virgule dans le nom d'une option select/multi_select. `revue`
    est un vocabulaire libre (créé à la volée, voir etape-3-conception-technique.md,
    Décision 3) : un vrai nom de revue peut légitimement en contenir une (constaté au
    premier run réel), remplacée ici plutôt que rejetée."""
    if not valeur:
        return None
    return valeur.replace(",", " -")


def _proprietes(etude: dict) -> dict:
    return {
        "titre": {"title": _texte_riche(etude.get("titre"))},
        "auteurs": {"rich_text": _texte_riche(etude.get("auteurs"))},
        "annee": {"number": etude.get("annee")},
        "revue": {"select": (
            {"name": nom} if (nom := _nettoyer_option_select(etude.get("revue"))) else None
        )},
        "organisme": {"rich_text": _texte_riche(etude.get("organisme"))},
        "doi_url": {"url": etude.get("doi_url") or None},
        "url_source": {"select": (
            {"name": nom} if (nom := etude.get("url_source")) else None
        )},
        "url_not_real": {"checkbox": bool(etude.get("url_not_real"))},
        "domaine_sante": {"multi_select": [{"name": d} for d in etude.get("domaine_sante") or []]},
        "source_bruit": {"multi_select": [{"name": s} for s in etude.get("source_bruit") or []]},
        "resume": {"rich_text": _texte_riche(etude.get("resume"))},
        "resultat_cle": {"rich_text": _texte_riche(etude.get("resultat_cle"))},
        "statut": {"select": {"name": "🆕 Nouveau"}},
        "favori": {"checkbox": False},
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def creer_fiche(notion: Client, data_source_id: str, etude: dict) -> None:
    notion.pages.create(
        parent={"type": "data_source_id", "data_source_id": data_source_id},
        properties=_proprietes(etude),
    )
