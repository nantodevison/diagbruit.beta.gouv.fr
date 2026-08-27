"""Phase 2 de l'étape 2 : extraction du texte des pièces résolues en phase 1.

Chaque PDF est extrait page par page avec `pdfplumber`. Un score de confiance
simple sur le texte natif extrait (part des pages contenant un minimum de
caractères reconnus) détermine s'il s'agit d'un scan : si moins de la moitié
des pages ont du texte natif exploitable, le document est considéré comme
scanné et l'OCR (`pytesseract` + `pdf2image`) prend le relais pour
l'ensemble du document — la confiance moyenne renvoyée par Tesseract est
alors traduite en trois niveaux (`élevée` / `moyenne` / `faible`).

`pytesseract` et `pdf2image` sont de simples wrappers Python autour de
binaires externes (Tesseract OCR, Poppler) qui doivent être installés
séparément sur la machine (voir `docs/etape-2-conception-technique.md`).
Leur absence — ou tout autre échec d'OCR — ne bloque jamais le traitement du
département : la pièce concernée part en erreur documentée, conformément à
la décision 4 de l'étape 1 (jamais bloquant), reconduite telle quelle ici.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import pdf2image
import pdfplumber
import pytesseract
import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .resolution_pieces import ErreurTraitement, Piece

# Une page est considérée comme ayant du texte natif exploitable si elle
# contient au moins ce nombre de caractères après extraction directe.
MIN_CARACTERES_PAGE_TEXTE = 20

DPI_OCR = 200
LANGUE_OCR = "fra"

SEUIL_CONFIANCE_ELEVEE = 80
SEUIL_CONFIANCE_MOYENNE = 50


@dataclass
class PageExtraite:
    numero_page: int
    texte: str


@dataclass
class ExtractionPiece:
    piece: Piece
    pages: list[PageExtraite]
    ocr_utilise: bool
    ocr_confiance: str | None  # élevée / moyenne / faible, None si ocr_utilise est False


class _ErreurExtraction(Exception):
    """Échec de téléchargement, de lecture PDF ou d'OCR pour une pièce."""


def _lire_fichier_local(url: str) -> bytes:
    # Pièces de repli résolues via archiveUrl (voir `resolution_pieces.py`) :
    # déjà extraites sur disque, `lien_web_document` porte une URI `file://`
    # plutôt qu'une URL GPU à retélécharger.
    chemin = Path(url2pathname(urlparse(url).path))
    try:
        return chemin.read_bytes()
    except OSError as exc:
        raise _ErreurExtraction(f"lecture du fichier local impossible ({chemin}) : {exc}") from exc


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _telecharger(url: str) -> bytes:
    if url.startswith("file://"):
        return _lire_fichier_local(url)
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def _extraire_texte_natif(contenu_pdf: bytes) -> list[PageExtraite]:
    try:
        with pdfplumber.open(io.BytesIO(contenu_pdf)) as pdf:
            return [
                PageExtraite(numero_page=i + 1, texte=page.extract_text() or "")
                for i, page in enumerate(pdf.pages)
            ]
    except Exception as exc:  # pdfplumber/pdfminer peuvent lever des erreurs variées selon le PDF
        raise _ErreurExtraction(f"lecture du PDF impossible : {exc}") from exc


def _est_scan(pages: list[PageExtraite]) -> bool:
    if not pages:
        return True
    pages_avec_texte = sum(1 for page in pages if len(page.texte.strip()) >= MIN_CARACTERES_PAGE_TEXTE)
    return pages_avec_texte < len(pages) / 2


def _niveau_confiance(confiance_moyenne: float) -> str:
    if confiance_moyenne >= SEUIL_CONFIANCE_ELEVEE:
        return "élevée"
    if confiance_moyenne >= SEUIL_CONFIANCE_MOYENNE:
        return "moyenne"
    return "faible"


def _extraire_par_ocr(contenu_pdf: bytes) -> tuple[list[PageExtraite], str]:
    try:
        images = pdf2image.convert_from_bytes(contenu_pdf, dpi=DPI_OCR)
    except Exception as exc:
        raise _ErreurExtraction(f"conversion PDF -> image (Poppler) impossible : {exc}") from exc

    pages: list[PageExtraite] = []
    confiances: list[float] = []
    for i, image in enumerate(images):
        try:
            texte = pytesseract.image_to_string(image, lang=LANGUE_OCR)
            donnees = pytesseract.image_to_data(
                image, lang=LANGUE_OCR, output_type=pytesseract.Output.DICT
            )
        except Exception as exc:
            raise _ErreurExtraction(f"OCR (Tesseract) impossible : {exc}") from exc

        pages.append(PageExtraite(numero_page=i + 1, texte=texte))
        confiances.extend(float(c) for c in donnees.get("conf", []) if str(c).lstrip("-").isdigit() and float(c) >= 0)

    confiance_moyenne = sum(confiances) / len(confiances) if confiances else 0.0
    return pages, _niveau_confiance(confiance_moyenne)


def _extraire_piece(piece: Piece) -> ExtractionPiece:
    contenu_pdf = _telecharger(piece.lien_web_document)
    pages = _extraire_texte_natif(contenu_pdf)

    if not _est_scan(pages):
        return ExtractionPiece(piece=piece, pages=pages, ocr_utilise=False, ocr_confiance=None)

    pages_ocr, confiance = _extraire_par_ocr(contenu_pdf)
    return ExtractionPiece(piece=piece, pages=pages_ocr, ocr_utilise=True, ocr_confiance=confiance)


def extraire_textes(pieces: list[Piece]) -> tuple[list[ExtractionPiece], list[ErreurTraitement]]:
    """Extrait le texte de chaque pièce (phase 2 complète).

    Ne lève jamais d'exception : toute pièce dont le téléchargement,
    l'extraction ou l'OCR échoue est isolée et son erreur empilée dans la
    liste retournée, le reste du département continue d'être traité.
    """
    extractions: list[ExtractionPiece] = []
    erreurs: list[ErreurTraitement] = []

    for piece in pieces:
        try:
            extractions.append(_extraire_piece(piece))
        except (_ErreurExtraction, requests.exceptions.RequestException) as exc:
            erreurs.append(
                ErreurTraitement(
                    piece.id_gpu, piece.lien_web_document, "2-extraction", "extraction_pdf", str(exc)
                )
            )

    return extractions, erreurs
