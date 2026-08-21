"""Étape 6 — phase unique : génération de l'export pour la saisie Strapi/Notion
(`generer_export.py`), voir `docs/etape-6-conception-technique.md`.

Lit `etape5_{dept}.gpkg` (couche `messages`), `etape5_{dept}_documents_par_synthese.csv`
et `etape4_{dept}.gpkg` (couche `geometries` — relu uniquement pour la colonne
`communes`, absente de `etape5_{dept}.gpkg` en pratique ; voir la note du
21/08/2026 dans `etape-6-conception-technique.md`, "Architecture des
dossiers"). Pour chaque géométrie finale : assemble le message Strapi
(`assembler_message.py`), propose un territoire (`resolution_territoire.py`),
écrit sa géométrie en GeoJSON individuel, et une ligne dans
`etape6_{dept}_export.csv`.

Usage :
    python -m etape6_mise_en_forme.generer_export --dept 033

Entrée (dans `output/`, voir `--output-dir`) :
    etape4_{dept}.gpkg
    etape5_{dept}.gpkg
    etape5_{dept}_documents_par_synthese.csv

Sortie (dans le même dossier) :
    etape6_{dept}_export.csv    — voir "Contrat de données" dans etape-6-conception-technique.md
    etape6_{dept}_geometries/   — un {id_geometrie}.geojson par géométrie finale
    etape6_{dept}_erreurs.csv   — échecs isolés de résolution de territoire, si non vide
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .assembler_message import assembler_message
from .resolution_territoire import SEPARATEUR_COMMUNES, ResolveurTerritoire

COLONNES_EXPORT = [
    "id_geometrie",
    "territoire_propose",
    "description_slug",
    "alert_slug_propose",
    "message_strapi",
    "nom_fichier_geometrie",
    "communes",
]

COLONNES_ERREURS = ["identifiant", "source", "message", "date_traitement"]


class Etape5GpkgIntrouvable(Exception):
    pass


class Etape4GpkgIntrouvable(Exception):
    pass


class DocumentsCsvIntrouvable(Exception):
    pass


class DesynchronisationEntrees(Exception):
    """`etape5_{dept}.gpkg`, `etape5_{dept}_documents_par_synthese.csv` et
    `etape4_{dept}.gpkg` ne proviennent pas du même run — voir "Gestion des
    erreurs" dans `etape-6-conception-technique.md`."""


def _texte(valeur) -> str:
    """Même normalisation NaN-safe que le reste du pipeline — voir
    `etape4_geometries/synthese_geometries.py`, `_texte()`. Réimplémentée ici
    plutôt qu'importée (voir `etape-1-conception-technique.md`, "Décision 2" :
    chaque étape reste indépendante du code des autres)."""
    if valeur is None:
        return ""
    if isinstance(valeur, float) and pd.isna(valeur):
        return ""
    return str(valeur).strip()


def _slugifier_territoire(territoire: str) -> str:
    """Retire espaces et accents, casse d'origine conservée — voir
    `docs/etape-6-mise-en-forme-diagbruit.md`, "Format de l'alert_slug"."""
    sans_accents = unicodedata.normalize("NFKD", territoire)
    sans_accents = "".join(c for c in sans_accents if not unicodedata.combining(c))
    return re.sub(r"\s+", "", sans_accents)


def _lire_documents_par_synthese(chemin: Path) -> dict[str, list[dict]]:
    documents: dict[str, list[dict]] = defaultdict(list)
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        for ligne in csv.DictReader(fichier):
            id_synthese = _texte(ligne.get("id_geometrie_synthese"))
            if id_synthese:
                documents[id_synthese].append(ligne)
    return documents


def _communes_par_geometrie(chemin: Path) -> dict[str, str]:
    """`communes` (texte brut, non découpé) par `id_geometrie`, reprise de
    `etape4_{dept}.gpkg` — voir la docstring du module pour pourquoi ce
    fichier est relu ici en plus de `etape5_{dept}.gpkg`."""
    gdf = gpd.read_file(chemin, layer="geometries")
    return {_texte(ligne.get("id_geometrie")): _texte(ligne.get("communes")) for _, ligne in gdf.iterrows()}


def generer(code_departement: str, dossier_sortie: str | Path = "output") -> Path:
    dossier = Path(dossier_sortie)
    chemin_etape5 = dossier / f"etape5_{code_departement}.gpkg"
    chemin_documents = dossier / f"etape5_{code_departement}_documents_par_synthese.csv"
    chemin_etape4 = dossier / f"etape4_{code_departement}.gpkg"

    if not chemin_etape5.exists():
        raise Etape5GpkgIntrouvable(str(chemin_etape5))
    if not chemin_documents.exists():
        raise DocumentsCsvIntrouvable(str(chemin_documents))
    if not chemin_etape4.exists():
        raise Etape4GpkgIntrouvable(str(chemin_etape4))

    gdf = gpd.read_file(chemin_etape5, layer="messages")
    documents_par_synthese = _lire_documents_par_synthese(chemin_documents)
    communes_par_geometrie = _communes_par_geometrie(chemin_etape4)

    # --- Vérification de cohérence entre les fichiers d'entrée ---
    # Un désynchronisme ici signale des fichiers issus de runs différents,
    # jamais supposé sans conséquence : le traitement s'arrête plutôt que de
    # produire un export partiellement incohérent (même logique que
    # synthese_messages.py à l'étape 5).
    ids_messages = {_texte(ligne.get("id_geometrie")) for _, ligne in gdf.iterrows()}

    ids_documents_orphelins = set(documents_par_synthese) - ids_messages
    if ids_documents_orphelins:
        raise DesynchronisationEntrees(
            f"{len(ids_documents_orphelins)} id_geometrie_synthese de {chemin_documents.name} "
            f"absent(s) de {chemin_etape5.name} : {', '.join(sorted(ids_documents_orphelins))}."
        )

    ids_occurrence_sans_document = {
        _texte(ligne.get("id_geometrie"))
        for _, ligne in gdf.iterrows()
        if _texte(ligne.get("id_occurrence")) and _texte(ligne.get("id_geometrie")) not in documents_par_synthese
    }
    if ids_occurrence_sans_document:
        raise DesynchronisationEntrees(
            f"{len(ids_occurrence_sans_document)} géométrie(s) occurrence_locale de {chemin_etape5.name} "
            f"sans aucune ligne dans {chemin_documents.name} : "
            f"{', '.join(sorted(ids_occurrence_sans_document))}."
        )

    ids_manquantes_etape4 = ids_messages - set(communes_par_geometrie)
    if ids_manquantes_etape4:
        raise DesynchronisationEntrees(
            f"{len(ids_manquantes_etape4)} id_geometrie de {chemin_etape5.name} absent(s) de "
            f"{chemin_etape4.name} (fichiers issus de runs différents ?) : "
            f"{', '.join(sorted(ids_manquantes_etape4))}."
        )

    dossier_geometries = dossier / f"etape6_{code_departement}_geometries"
    dossier_geometries.mkdir(exist_ok=True)

    resolveur = ResolveurTerritoire(code_departement)
    date_traitement = date.today().isoformat()

    lignes_export: list[dict] = []
    erreurs: list[dict] = []

    for _, ligne in gdf.iterrows():
        id_geometrie = _texte(ligne.get("id_geometrie"))
        communes_brutes = communes_par_geometrie.get(id_geometrie, "")
        communes = [c.strip() for c in communes_brutes.split(SEPARATEUR_COMMUNES) if c.strip()]

        territoire_propose, echec = resolveur.proposer_territoire(communes)
        if echec:
            erreurs.append(
                {
                    "identifiant": id_geometrie,
                    "source": "resolution_territoire",
                    "message": f"résolution du territoire échouée pour : {communes_brutes or '(vide)'}",
                    "date_traitement": date_traitement,
                }
            )

        alert_slug_propose = f"alert-{_slugifier_territoire(territoire_propose)}-" if territoire_propose else ""

        documents = documents_par_synthese.get(id_geometrie, [])
        message_strapi = assembler_message(_texte(ligne.get("message_synthese")), documents)

        nom_fichier_geometrie = f"{id_geometrie}.geojson"
        geodf_ligne = gpd.GeoDataFrame([{"id_geometrie": id_geometrie}], geometry=[ligne.geometry], crs=gdf.crs)
        geodf_ligne.to_file(dossier_geometries / nom_fichier_geometrie, driver="GeoJSON")

        lignes_export.append(
            {
                "id_geometrie": id_geometrie,
                "territoire_propose": territoire_propose,
                "description_slug": "",
                "alert_slug_propose": alert_slug_propose,
                "message_strapi": message_strapi,
                "nom_fichier_geometrie": nom_fichier_geometrie,
                "communes": communes_brutes,
            }
        )

    chemin_export = dossier / f"etape6_{code_departement}_export.csv"
    with chemin_export.open("w", newline="", encoding="utf-8-sig") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=COLONNES_EXPORT)
        writer.writeheader()
        writer.writerows(lignes_export)

    chemin_erreurs = dossier / f"etape6_{code_departement}_erreurs.csv"
    if erreurs:
        with chemin_erreurs.open("w", newline="", encoding="utf-8-sig") as fichier:
            writer = csv.DictWriter(fichier, fieldnames=COLONNES_ERREURS)
            writer.writeheader()
            writer.writerows(erreurs)
        print(f"{len(erreurs)} échec(s) de résolution de territoire, listé(s) dans {chemin_erreurs}.")
    elif chemin_erreurs.exists():
        chemin_erreurs.unlink()

    print(f"{len(lignes_export)} ligne(s) écrite(s) dans {chemin_export}, géométries dans {dossier_geometries}.")
    return chemin_export


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Étape 6 — génère l'export CSV et les géométries pour la saisie manuelle Strapi/Notion."
    )
    parser.add_argument(
        "--dept",
        required=True,
        help="Code département diagBruit (ex. 033, 971) — doit correspondre à un etape5_{dept}.gpkg existant.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Dossier de lecture/écriture des fichiers (défaut : output/).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    print(f"Étape 6 — département {args.dept}")
    try:
        generer(args.dept, dossier_sortie=args.output_dir)
    except Etape5GpkgIntrouvable as exc:
        print(f"Arrêt : etape5_{args.dept}.gpkg introuvable ({exc}).", file=sys.stderr)
        return 1
    except Etape4GpkgIntrouvable as exc:
        print(f"Arrêt : etape4_{args.dept}.gpkg introuvable ({exc}).", file=sys.stderr)
        return 1
    except DocumentsCsvIntrouvable as exc:
        print(f"Arrêt : etape5_{args.dept}_documents_par_synthese.csv introuvable ({exc}).", file=sys.stderr)
        return 1
    except DesynchronisationEntrees as exc:
        print(f"Arrêt : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
