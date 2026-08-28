"""Phase 3 de l'étape 2 : filtrage lexical du texte extrait.

Sur le texte de chaque pièce (phase 2), deux recherches textuelles simples,
paragraphe par paragraphe, dans l'ordre du document :
- la liste de mots-clés d'inclusion retient un passage ;
- la liste de mots-clés d'exclusion pose un tag sur les passages retenus qui
  évoquent en plus le classement sonore des voies ou le PEB (déjà traités
  ailleurs par diagBruit). Ce tag ne supprime rien — l'arbitrage revient à la
  phase 4 (classification).

Écart pragmatique par rapport au document de cadrage sur deux points non
précisés par celui-ci :

1. **Découpage en paragraphes** : le texte extrait par `pdfplumber` (ou par
   l'OCR) ne porte pas de marquage fiable de paragraphe. On découpe d'abord
   sur les lignes vides ; si une page ne produit qu'un seul bloc (PDF sans
   ligne vide entre paragraphes, cas fréquent), on retombe sur un découpage
   ligne à ligne.
2. **Repérage de la référence (article/alinéa)** : la numérotation est
   recherchée en tête de chaque paragraphe et mémorisée au fil de la lecture
   de la pièce (un "Article N" rencontré reste la référence courante jusqu'au
   suivant ; un "alinéa N" s'y ajoute). Si aucune numérotation n'a encore été
   rencontrée au moment d'un passage retenu, la référence retombe sur le
   numéro de page de ce passage (voir `etape-2-analyse-documents-urbanisme-diagbruit.md`,
   phase 2).

   Bug corrigé le 13/08/2026 (retour utilisateur, département 067) : une
   première version cherchait "article" n'importe où dans le paragraphe, ce
   qui capturait à tort des renvois au code de l'urbanisme cités en milieu de
   phrase (ex. "...en application de l'article L.302-1 du code de
   l'urbanisme...") comme s'il s'agissait d'un article du document
   lui-même. Deux garde-fous désormais en place : la recherche ne porte que
   sur le **début** du paragraphe (un article du document apparaît comme son
   propre paragraphe/titre, jamais noyé en milieu de phrase — cohérent avec
   le découpage en blocs de `_decouper_en_paragraphes`), et toute capture de
   la forme "L.302-1", "R. 111-2"... (lettre de code + point + chiffres,
   caractéristique d'une référence légale) est explicitement écartée.

Ce module ne fait aucun appel réseau ni traitement d'image ; il ne lève et ne
retourne donc normalement aucune erreur, mais garde la même signature à deux
listes que les autres phases pour rester cohérent avec elles dans `main.py`.

Mise à jour du 13/08/2026 (retour utilisateur, option 4 retenue pour la
citation — voir `classification.py`) : `contexte_avant` est désormais tronqué
en conservant sa **fin** plutôt que son début. La phase 4 demande au modèle
une citation verbatim qui peut piocher dans le contexte immédiat ; ce qui
compte, pour `contexte_avant`, c'est la partie la plus proche du passage (la
fin du bloc précédent), pas son tout début. `contexte_apres` reste tronqué en
conservant son début (la partie la plus proche du passage), sans changement.
`extrait_occurrence` (renommé `extrait_repli`) reste calculé mécaniquement :
il ne sert plus de citation affichée dans le CSV, seulement de repli si la
citation du modèle ne peut pas être vérifiée comme un extrait verbatim du
texte fourni (voir `classification.py`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .extraction_texte import ExtractionPiece
from .resolution_pieces import ErreurTraitement, Piece

MOTS_CLES_INCLUSION = [
    "bruit",
    "nuisances sonores",
    "isolation acoustique",
    "acoustique",
    "sonore",
    "calme",
    "zone calme",
]

MOTS_CLES_EXCLUSION = [
    "classement sonore",
    "plan d'exposition au bruit",
    "csv",  # Classement Sonore des Voies (acronyme, cf. document de cadrage)
    "peb",
    "l.571-10",
]

_ARTICLE_RE = re.compile(r"article\s+([\w.\-]+)", re.IGNORECASE)
_ALINEA_RE = re.compile(r"alin[ée]a\s+(\d+)", re.IGNORECASE)
# Renvoi au code de l'urbanisme (ou à un autre code) plutôt qu'à un article du
# document lui-même : "L.302-1", "R. 111-2", "L 571-10"... — lettre, point ou
# espace optionnel, puis un chiffre.
_CITATION_CODE_RE = re.compile(r"^[a-z]\.?\s?\d", re.IGNORECASE)

# Longueur maximale du repli mécanique `extrait_repli` (voir docstring du
# module) — le passage complet, plus long, sert au prompt de la phase 4
# (`passage_texte`).
LONGUEUR_MAX_EXTRAIT = 500
LONGUEUR_MAX_CONTEXTE = 300

# Taille cible (en caractères) d'un bloc regroupé quand le PDF ne sépare pas
# ses paragraphes par une ligne vide (repli ligne à ligne, voir
# `_decouper_en_paragraphes`) : évite un passage par ligne physique, ce qui
# fragmenterait inutilement le texte et multiplierait le nombre d'appels de
# classification (phase 4, facturée à l'appel).
TAILLE_CIBLE_BLOC_REPLI = 400


@dataclass
class PassageRetenu:
    piece: Piece
    reference_type: str  # "alinea" ou "page"
    reference_precise: str
    numero_page: int
    passage_texte: str
    extrait_repli: str  # citation mécanique de repli, voir docstring du module
    contexte_avant: str
    contexte_apres: str
    tag_exclusion: bool
    ocr_utilise: bool
    ocr_confiance: str | None


@dataclass
class _ParagrapheRepere:
    numero_page: int
    texte: str
    reference_type: str
    reference_precise: str


def _decouper_en_paragraphes(texte: str) -> list[str]:
    blocs = [b.strip() for b in re.split(r"\n\s*\n", texte) if b.strip()]
    if len(blocs) > 1:
        return blocs

    # Repli : pas de ligne vide entre paragraphes dans ce PDF (fréquent avec
    # l'extraction pdfplumber de règlements d'urbanisme). On regroupe les
    # lignes consécutives en blocs d'une taille raisonnable — plutôt qu'un
    # paragraphe par ligne physique — en coupant aussi au début d'un nouvel
    # "Article" pour ne pas mélanger deux articles dans un même bloc.
    lignes = [ligne.strip() for ligne in texte.splitlines() if ligne.strip()]
    paragraphes: list[str] = []
    bloc_courant: list[str] = []
    for ligne in lignes:
        debut_nouvel_article = bool(_ARTICLE_RE.match(ligne)) and bloc_courant
        taille_bloc = sum(len(l) for l in bloc_courant)
        if bloc_courant and (debut_nouvel_article or taille_bloc >= TAILLE_CIBLE_BLOC_REPLI):
            paragraphes.append(" ".join(bloc_courant))
            bloc_courant = []
        bloc_courant.append(ligne)
    if bloc_courant:
        paragraphes.append(" ".join(bloc_courant))
    return paragraphes


def _paragraphes_avec_repere(pages: list) -> list[_ParagrapheRepere]:
    """Aplati les pages d'une pièce en paragraphes, dans l'ordre de lecture,
    en mémorisant la dernière référence (article/alinéa) rencontrée."""
    resultat: list[_ParagrapheRepere] = []
    dernier_article: str | None = None
    dernier_alinea: str | None = None

    for page in pages:
        for paragraphe in _decouper_en_paragraphes(page.texte):
            match_article = _ARTICLE_RE.match(paragraphe)
            if match_article and _CITATION_CODE_RE.match(match_article.group(1)):
                match_article = None  # renvoi au code (ex. "article L.302-1"), pas un article du document
            match_alinea = _ALINEA_RE.search(paragraphe)

            if match_article:
                dernier_article = f"Article {match_article.group(1)}"
                dernier_alinea = f"alinéa {match_alinea.group(1)}" if match_alinea else None
            elif match_alinea:
                dernier_alinea = f"alinéa {match_alinea.group(1)}"

            if dernier_article:
                reference_type = "alinea"
                reference_precise = (
                    f"{dernier_article}, {dernier_alinea}" if dernier_alinea else dernier_article
                )
            elif dernier_alinea:
                reference_type = "alinea"
                reference_precise = dernier_alinea
            else:
                reference_type = "page"
                reference_precise = f"page {page.numero_page}"

            resultat.append(
                _ParagrapheRepere(
                    numero_page=page.numero_page,
                    texte=paragraphe,
                    reference_type=reference_type,
                    reference_precise=reference_precise,
                )
            )

    return resultat


def _tronquer(texte: str, longueur_max: int) -> str:
    """Conserve le début du texte (utilisé pour `contexte_apres` et le repli
    mécanique `extrait_repli` : la partie la plus proche du passage, ou
    l'entrée en matière, est en tête)."""
    if len(texte) <= longueur_max:
        return texte
    return texte[:longueur_max].rstrip() + "…"


def _tronquer_debut(texte: str, longueur_max: int) -> str:
    """Conserve la fin du texte (utilisé pour `contexte_avant` : la partie la
    plus proche du passage — donc la plus utile pour une citation qui
    déborderait dessus — est en fin de bloc précédent)."""
    if len(texte) <= longueur_max:
        return texte
    return "…" + texte[-longueur_max:].lstrip()


def _contient_un_mot_cle(texte: str, mots_cles: list[str]) -> bool:
    texte_normalise = texte.lower()
    return any(mot in texte_normalise for mot in mots_cles)


def _filtrer_piece(extraction: ExtractionPiece) -> list[PassageRetenu]:
    paragraphes = _paragraphes_avec_repere(extraction.pages)
    passages: list[PassageRetenu] = []

    for i, paragraphe in enumerate(paragraphes):
        if not _contient_un_mot_cle(paragraphe.texte, MOTS_CLES_INCLUSION):
            continue

        contexte_avant = paragraphes[i - 1].texte if i > 0 else ""
        contexte_apres = paragraphes[i + 1].texte if i + 1 < len(paragraphes) else ""

        passages.append(
            PassageRetenu(
                piece=extraction.piece,
                reference_type=paragraphe.reference_type,
                reference_precise=paragraphe.reference_precise,
                numero_page=paragraphe.numero_page,
                passage_texte=paragraphe.texte,
                extrait_repli=_tronquer(paragraphe.texte, LONGUEUR_MAX_EXTRAIT),
                contexte_avant=_tronquer_debut(contexte_avant, LONGUEUR_MAX_CONTEXTE),
                contexte_apres=_tronquer(contexte_apres, LONGUEUR_MAX_CONTEXTE),
                tag_exclusion=_contient_un_mot_cle(paragraphe.texte, MOTS_CLES_EXCLUSION),
                ocr_utilise=extraction.ocr_utilise,
                ocr_confiance=extraction.ocr_confiance,
            )
        )

    return passages


def filtrer_departement(
    extractions: list[ExtractionPiece],
) -> tuple[list[PassageRetenu], list[ErreurTraitement]]:
    """Filtre lexicalement le texte de chaque pièce extraite (phase 3
    complète). Ne fait aucun appel réseau : la liste d'erreurs retournée est
    toujours vide, conservée pour la cohérence de signature avec les autres
    phases.
    """
    passages: list[PassageRetenu] = []
    for extraction in extractions:
        passages.extend(_filtrer_piece(extraction))
    return passages, []
