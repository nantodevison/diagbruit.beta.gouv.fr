"""Phase 1 de l'étape 2 : résolution des pièces d'un document d'urbanisme.

Lit `etape1_{dept}.csv` (produit par l'étape 1), ne garde que les lignes dont
le `statut` vaut `document trouvé` ou `PSMV additionnel` (seules à porter un
`id_gpu` exploitable — voir `etape-2-analyse-documents-urbanisme-diagbruit.md`),
et résout chaque `id_gpu` en une liste de pièces téléchargeables via
`document-details` du GPU.

Un même `id_gpu` (typiquement un PLUi intercommunal) apparaît sur autant de
lignes du CSV d'entrée que de communes couvertes. Il est donc dédoublonné ici
avant tout appel réseau — écart pragmatique par rapport au document de
cadrage, dans le même esprit que le dédoublonnage des EPCI à l'étape 1
(décision 2.1) : sans cela, un même document serait interrogé et téléchargé
des centaines de fois pour un seul département.

Écart documenté avec `etape-2-analyse-documents-urbanisme-diagbruit.md` (phase 1) :
l'API `document/{id}/details` du GPU ne renvoie pas une liste de « pièces »
typées avec leurs URLs, mais deux structures parallèles observées en
interrogeant l'API réelle (testé sur un PLUi de plusieurs centaines de
fichiers) :
- `files` : la liste brute des noms de fichiers du document ;
- `writingMaterials` : un dictionnaire `{nom_fichier: url_de_téléchargement}`
  couvrant les mêmes fichiers.

Le nom de chaque fichier encode son rôle par un segment fixe (ex.
`{siren}_reglement_{date}.pdf`, `{siren}_padd_{date}.pdf`,
`{siren}_orientations_amenagement_{date}.pdf`, `{siren}_reglement_graphique_N_{date}.pdf`,
`{siren}_prescription_surf_..._{date}.pdf`, `{siren}_rapport_N_{date}.pdf`...).
La colonne `type_piece_source` du CSV de sortie de l'étape 2 n'admet que
quatre valeurs (`règlement écrit`, `OAP`, `PADD`, `PSMV`) : seuls les
fichiers dont le nom correspond sans ambiguïté à l'une d'elles sont retenus
comme « pièce » ici (règlement textuel hors plans graphiques, orientations
d'aménagement, PADD). Le reste (rapport de présentation, plans graphiques,
couches de prescriptions structurées — déjà écartées de l'analyse par
`etape-2-analyse-documents-urbanisme-diagbruit.md` — procédure, servitudes...)
est délibérément hors périmètre de cette première version : rien n'empêche
d'élargir cette liste plus tard si l'analyse s'avère trop restrictive.

Piège observé en testant sur un vrai PLUi (Eurométropole de Strasbourg) : le
nom d'une annexe de prescription structurée peut lui-même contenir le mot
"reglement" (ex. `..._prescription_surf_99_00_01_PPRi_Bruche_reglement_..._.pdf`,
le règlement d'un PPRi annexé comme servitude) — un simple `"reglement" in
nom_fichier` la classerait à tort comme le règlement écrit du PLU/PLUi. Les
motifs d'exclusion (`prescription_surf`/`prescription_lin`, `info_surf`/`info_lin`)
sont donc testés avant le motif générique de règlement.

Pour un document dont la `nature_document` (colonne de l'étape 1) vaut
`PSMV`, la pièce de règlement est typée `PSMV` plutôt que `règlement écrit`
(nature juridique différente, voir la colonne `nature_juridique_piece` de
`synthese.py`).

Contrairement à `etape1_identification/communes.py`, un `etape1_{dept}.csv`
introuvable est une erreur irrécupérable pour l'étape 2 entière (rien
d'exploitable en aval) ; en revanche l'échec de résolution d'un `id_gpu`
individuel est isolé et n'interrompt jamais le traitement des autres
documents du département (décision 4 de l'étape 1, reconduite).

Repli sur `archiveUrl` (ajouté le 26/08/2026, ~31% d'échecs constatés sur le
067 hors Eurométropole) : pour une partie des documents, le GPU renvoie un
`writingMaterials` vide alors que les pièces existent bel et bien — elles ne
sont accessibles que dans l'archive ZIP complète du document (`archiveUrl`).
Dans ce cas, le ZIP est téléchargé une fois, et seuls les fichiers du dossier
`Pieces_ecrites/` correspondant à un `type_piece_source` retenu (même logique
de motifs que pour `writingMaterials`) sont extraits sur disque, sous
`{dossier_telechargement}/{id_gpu}/{nom_fichier}` (le reste de l'archive —
géodata, rapport de présentation — n'est jamais persisté : hors périmètre,
et une archive fait ~200 Mo pour une seule commune).

`Piece.lien_web_document` porte alors une URI locale (`file://...`) au lieu
de l'URL GPU habituelle : `extraction_texte.py` sait lire directement ce
fichier plutôt que le retélécharger, et les outils de relecture manuelle
(`outil_validation.html`) ouvrent nativement un lien `file://` dans un
nouvel onglet — aucun changement necessaire côté outils en aval. Limite
assumée pour ce POC : ce lien n'est valable que sur la machine qui a produit
`download/` (dossier gitignoré, jamais commité). Comme pour les pièces
`writingMaterials`, aucun cache : une relance retélécharge et écrase.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

GPU_DOCUMENT_SEARCH_URL = "https://www.geoportail-urbanisme.gouv.fr/api/document"

STATUT_DOCUMENT_TROUVE = "document trouvé"
STATUT_PSMV_ADDITIONNEL = "PSMV additionnel"
STATUTS_AVEC_ID_GPU = {STATUT_DOCUMENT_TROUVE, STATUT_PSMV_ADDITIONNEL}

DOSSIER_TELECHARGEMENT_DEFAUT = "download"

# Seuls les fichiers de ce dossier de l'archive portent les pièces écrites
# exploitables (voir docstring du module) ; le reste (Donnees_geographiques,
# rapport de présentation...) est ignoré à l'extraction.
DOSSIER_ARCHIVE_PIECES_ECRITES = "Pieces_ecrites/"

TYPE_REGLEMENT = "règlement écrit"
TYPE_OAP = "OAP"
TYPE_PADD = "PADD"
TYPE_PSMV = "PSMV"

# Ordre important : les motifs d'exclusion doivent être testés avant les
# motifs génériques qu'ils pourraient sinon capturer par accident. Exemple
# réel observé (PLUi Eurométropole de Strasbourg) :
# "..._prescription_surf_99_00_01_PPRi_Bruche_reglement_20190923_....pdf" —
# une annexe de prescription structurée (PPRi, servitude) dont le nom
# contient "reglement" sans être le règlement écrit du PLU/PLUi lui-même.
_MOTIFS_PIECES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"reglement_graphique", re.IGNORECASE), ""),  # exclu explicitement
    (re.compile(r"prescription_(surf|lin)", re.IGNORECASE), ""),  # couches structurées, hors périmètre
    (re.compile(r"info_(surf|lin)", re.IGNORECASE), ""),  # couches d'information, hors périmètre
    (re.compile(r"orientations_amenagement", re.IGNORECASE), TYPE_OAP),
    (re.compile(r"padd", re.IGNORECASE), TYPE_PADD),
    (re.compile(r"reglement", re.IGNORECASE), TYPE_REGLEMENT),
]


@dataclass
class Piece:
    id_gpu: str
    lien_web_document: str
    type_piece_source: str  # TYPE_REGLEMENT, TYPE_OAP, TYPE_PADD ou TYPE_PSMV
    nom_fichier: str


@dataclass
class ErreurTraitement:
    id_gpu: str
    lien_web_document: str
    phase: str
    type_erreur: str
    message: str
    contenu_brut: str = ""


class Etape1CsvIntrouvable(Exception):
    """Le CSV de sortie de l'étape 1 est introuvable ou illisible."""


class _ErreurAppelGPU(Exception):
    """Erreur réseau/HTTP lors d'un appel API, après épuisement des tentatives."""


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _get(url: str) -> requests.Response:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response


def _details_document(id_gpu: str) -> dict:
    try:
        response = _get(f"{GPU_DOCUMENT_SEARCH_URL}/{id_gpu}/details")
        return response.json()
    except requests.exceptions.RequestException as exc:
        raise _ErreurAppelGPU(f"document-details indisponible pour {id_gpu} : {exc}") from exc


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _telecharger_archive(url: str) -> bytes:
    # Timeout large : une archive complète de PLUi peut peser plusieurs
    # centaines de Mo (voir docstring du module).
    response = requests.get(url, timeout=180)
    response.raise_for_status()
    return response.content


def _extraire_pieces_archive(
    id_gpu: str,
    archive_url: str,
    nature_document: str,
    dossier_telechargement: Path,
) -> list[Piece]:
    """Télécharge `archive_url` et n'extrait sur disque que les pièces
    écrites exploitables (voir docstring du module). Lève `_ErreurAppelGPU`
    si le téléchargement échoue après les tentatives de `_telecharger_archive`.
    """
    contenu_zip = _telecharger_archive(archive_url)

    pieces: list[Piece] = []
    dossier_document = dossier_telechargement / id_gpu
    with zipfile.ZipFile(io.BytesIO(contenu_zip)) as archive:
        for info in archive.infolist():
            if info.is_dir() or DOSSIER_ARCHIVE_PIECES_ECRITES not in info.filename:
                continue
            nom_fichier = Path(info.filename).name
            type_piece = _type_piece(nom_fichier, nature_document)
            if type_piece is None:
                continue

            dossier_document.mkdir(parents=True, exist_ok=True)
            chemin_local = dossier_document / nom_fichier
            chemin_local.write_bytes(archive.read(info))
            pieces.append(Piece(id_gpu, chemin_local.resolve().as_uri(), type_piece, nom_fichier))

    return pieces


def _type_piece(nom_fichier: str, nature_document: str) -> str | None:
    """Retourne le `type_piece_source` du fichier, ou None s'il est hors
    périmètre (voir le docstring du module)."""
    for motif, type_piece in _MOTIFS_PIECES:
        if motif.search(nom_fichier):
            if not type_piece:
                return None
            if type_piece == TYPE_REGLEMENT and nature_document == "PSMV":
                return TYPE_PSMV
            return type_piece
    return None


def _lignes_a_traiter(chemin_etape1_csv: Path) -> list[dict]:
    try:
        with chemin_etape1_csv.open("r", newline="", encoding="utf-8-sig") as fichier:
            lignes = list(csv.DictReader(fichier))
    except OSError as exc:
        raise Etape1CsvIntrouvable(f"Impossible de lire {chemin_etape1_csv} : {exc}") from exc

    # Dédoublonnage par id_gpu (voir docstring du module) : on garde la
    # première ligne rencontrée pour chaque id_gpu, seule sa nature_document
    # nous intéresse ici.
    vues: set[str] = set()
    a_traiter = []
    for ligne in lignes:
        id_gpu = ligne.get("id_gpu", "")
        if ligne.get("statut") not in STATUTS_AVEC_ID_GPU or not id_gpu or id_gpu in vues:
            continue
        vues.add(id_gpu)
        a_traiter.append(ligne)
    return a_traiter


def resoudre_pieces_departement(
    chemin_etape1_csv: str | Path,
    dossier_telechargement: str | Path = DOSSIER_TELECHARGEMENT_DEFAUT,
) -> tuple[list[Piece], list[ErreurTraitement]]:
    """Résout, pour chaque document unique du département, la liste de ses
    pièces exploitables (voir docstring du module).

    Lève `Etape1CsvIntrouvable` si le fichier d'entrée est absent ou illisible.
    Toute autre erreur (document-details indisponible pour un `id_gpu`,
    archive de repli indisponible) est isolée et empilée dans la liste
    d'erreurs retournée.
    """
    lignes = _lignes_a_traiter(Path(chemin_etape1_csv))
    dossier_telechargement = Path(dossier_telechargement)

    pieces: list[Piece] = []
    erreurs: list[ErreurTraitement] = []

    for ligne in lignes:
        id_gpu = ligne["id_gpu"]
        nature_document = ligne.get("nature_document", "")
        try:
            details = _details_document(id_gpu)
        except _ErreurAppelGPU as exc:
            erreurs.append(ErreurTraitement(id_gpu, "", "1-resolution", "appel_gpu", str(exc)))
            continue

        materiaux = details.get("writingMaterials") or {}
        if not materiaux:
            archive_url = details.get("archiveUrl") or ""
            if not archive_url:
                erreurs.append(
                    ErreurTraitement(
                        id_gpu, "", "1-resolution", "aucun_fichier",
                        "document-details n'a renvoyé aucune pièce (writingMaterials vide) "
                        "et aucune archiveUrl de repli n'est disponible",
                    )
                )
                continue

            try:
                pieces_archive = _extraire_pieces_archive(
                    id_gpu, archive_url, nature_document, dossier_telechargement
                )
            except _ErreurAppelGPU as exc:
                erreurs.append(ErreurTraitement(id_gpu, archive_url, "1-resolution", "archive_indisponible", str(exc)))
                continue

            if not pieces_archive:
                erreurs.append(
                    ErreurTraitement(
                        id_gpu, archive_url, "1-resolution", "aucun_fichier",
                        "writingMaterials vide et aucune pièce exploitable trouvée dans "
                        f"{DOSSIER_ARCHIVE_PIECES_ECRITES} de l'archive de repli",
                    )
                )
                continue

            pieces.extend(pieces_archive)
            continue

        pieces_avant = len(pieces)
        for nom_fichier, url in materiaux.items():
            type_piece = _type_piece(nom_fichier, nature_document)
            if type_piece is None:
                continue
            pieces.append(Piece(id_gpu, url, type_piece, nom_fichier))

        if len(pieces) == pieces_avant:
            # writingMaterials non vide mais aucun de ses fichiers ne
            # correspond aux motifs attendus (voir _type_piece) : sans cette
            # erreur explicite, l'id_gpu disparaîtrait silencieusement,
            # comme le cas archiveUrl avant son propre traitement d'erreur.
            erreurs.append(
                ErreurTraitement(
                    id_gpu, "", "1-resolution", "aucun_fichier",
                    f"writingMaterials contient {len(materiaux)} fichier(s) mais aucun ne "
                    "correspond à une pièce exploitable (règlement/PADD/OAP/PSMV)",
                )
            )

    return pieces, erreurs
