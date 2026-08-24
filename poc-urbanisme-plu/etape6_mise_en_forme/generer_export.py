"""Étape 6 — phase unique : génération de l'export pour la saisie Strapi/Notion
(`generer_export.py`), voir `docs/etape-6-conception-technique.md`.

Lit `etape5_{dept}.gpkg` (couche `messages`, dont `titre_propose`, généré par
LLM à l'étape 5 et validé par l'opérateur), `etape5_{dept}_documents_par_synthese.csv` et `etape4_{dept}.gpkg`
(couche `geometries` — relu pour `communes` et `nature_sonore_zone`,
absentes de `etape5_{dept}.gpkg` en pratique ; voir la note du 21/08/2026
dans `etape-6-conception-technique.md`, "Architecture des dossiers"). Pour
chaque géométrie finale : assemble les champs Strapi (`assembler_message.py`),
propose un territoire (`resolution_territoire.py`), écrit sa géométrie en
GeoJSON individuel, et une ligne dans `etape6_{dept}_export.csv`.

**Reprise (ajouté le 24/08/2026)** : si `etape6_{dept}_export.csv` existe
déjà dans le dossier de sortie, `alert_slug_propose` et `description_slug`
y sont relus et conservés par `id_geometrie` plutôt qu'écrasés par la
proposition mécanique fraîche — un second passage ne perd donc jamais une
saisie déjà faite dans `outil_validation.html`. Pensez à renommer le
dernier export de l'outil en `etape6_{dept}_export.csv` avant de relancer
ce script, sinon la reprise ne verra pas vos dernières corrections.

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

from .assembler_message import assembler_message, assembler_source_reference
from .resolution_territoire import SEPARATEUR_COMMUNES, ResolveurTerritoire

# Correspondance vers le champ `label` de Strapi (enum `ZONE SOUMISE AU
# BRUIT` / `ZONE CALME`, voir docs/etape-7-stockage-diagbruit.md) — seule
# `preservation_zone_calme` correspond à une zone calme ; tout le reste,
# y compris vide (rnu/document_non_significatif/trou_de_couverture, qui
# n'ont pas de nature_sonore_zone), retombe sur le défaut du schéma.
LABEL_ZONE_CALME = "ZONE CALME"
LABEL_PAR_DEFAUT = "ZONE SOUMISE AU BRUIT"
NATURE_SONORE_ZONE_CALME = "preservation_zone_calme"

COLONNES_EXPORT = [
    "id_geometrie",
    "territoire_propose",
    "description_slug",
    "alert_slug_propose",
    "message_strapi",
    "message_content",
    "strapi_source",
    "strapi_reference",
    "label_propose",
    "titre_propose",
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
    """`etape5_{dept}.gpkg`, `etape5_{dept}_documents_par_synthese.csv`
    et `etape4_{dept}.gpkg` ne proviennent pas du même run — voir
    "Gestion des erreurs" dans
    `etape-6-conception-technique.md`."""


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


def _label_propose(nature_sonore_zone: str) -> str:
    return LABEL_ZONE_CALME if nature_sonore_zone == NATURE_SONORE_ZONE_CALME else LABEL_PAR_DEFAUT


def _lire_documents_par_synthese(chemin: Path) -> dict[str, list[dict]]:
    documents: dict[str, list[dict]] = defaultdict(list)
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        for ligne in csv.DictReader(fichier):
            id_synthese = _texte(ligne.get("id_geometrie_synthese"))
            if id_synthese:
                documents[id_synthese].append(ligne)
    return documents


def _details_par_geometrie(chemin: Path) -> dict[str, dict[str, str]]:
    """`communes` et `nature_sonore_zone` (texte brut) par `id_geometrie`,
    reprises de `etape4_{dept}.gpkg` — voir la docstring du module pour
    pourquoi ce fichier est relu ici en plus de `etape5_{dept}.gpkg`."""
    gdf = gpd.read_file(chemin, layer="geometries")
    return {
        _texte(ligne.get("id_geometrie")): {
            "communes": _texte(ligne.get("communes")),
            "nature_sonore_zone": _texte(ligne.get("nature_sonore_zone")),
        }
        for _, ligne in gdf.iterrows()
    }


def _lire_export_precedent(chemin: Path) -> dict[str, dict[str, str]]:
    """`alert_slug_propose`/`description_slug` déjà saisis par `id_geometrie`,
    si un export précédent existe — voir "Reprise" dans la docstring du
    module."""
    if not chemin.exists():
        return {}
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        return {
            _texte(ligne.get("id_geometrie")): {
                "alert_slug_propose": _texte(ligne.get("alert_slug_propose")),
                "description_slug": _texte(ligne.get("description_slug")),
            }
            for ligne in csv.DictReader(fichier)
            if _texte(ligne.get("id_geometrie"))
        }


def generer(code_departement: str, dossier_sortie: str | Path = "output") -> Path:
    dossier = Path(dossier_sortie)
    chemin_etape5 = dossier / f"etape5_{code_departement}.gpkg"
    chemin_documents = dossier / f"etape5_{code_departement}_documents_par_synthese.csv"
    chemin_etape4 = dossier / f"etape4_{code_departement}.gpkg"
    chemin_export = dossier / f"etape6_{code_departement}_export.csv"

    if not chemin_etape5.exists():
        raise Etape5GpkgIntrouvable(str(chemin_etape5))
    if not chemin_documents.exists():
        raise DocumentsCsvIntrouvable(str(chemin_documents))
    if not chemin_etape4.exists():
        raise Etape4GpkgIntrouvable(str(chemin_etape4))

    gdf = gpd.read_file(chemin_etape5, layer="messages")
    documents_par_synthese = _lire_documents_par_synthese(chemin_documents)
    details_par_geometrie = _details_par_geometrie(chemin_etape4)
    export_precedent = _lire_export_precedent(chemin_export)

    # --- Vérification de cohérence entre les fichiers d'entrée ---
    # Un désynchronisme ici signale des fichiers issus de runs différents,
    # jamais supposé sans conséquence : le traitement s'arrête plutôt que de
    # produire un export partiellement incohérent (même logique que
    # synthese_messages.py à l'étape 5).
    ids_messages = {_texte(ligne.get("id_geometrie")) for _, ligne in gdf.iterrows()}
    ids_occurrence_locale = {
        _texte(ligne.get("id_geometrie")) for _, ligne in gdf.iterrows() if _texte(ligne.get("id_occurrence"))
    }

    ids_documents_orphelins = set(documents_par_synthese) - ids_messages
    if ids_documents_orphelins:
        raise DesynchronisationEntrees(
            f"{len(ids_documents_orphelins)} id_geometrie_synthese de {chemin_documents.name} "
            f"absent(s) de {chemin_etape5.name} : {', '.join(sorted(ids_documents_orphelins))}."
        )

    ids_occurrence_sans_document = ids_occurrence_locale - set(documents_par_synthese)
    if ids_occurrence_sans_document:
        raise DesynchronisationEntrees(
            f"{len(ids_occurrence_sans_document)} géométrie(s) occurrence_locale de {chemin_etape5.name} "
            f"sans aucune ligne dans {chemin_documents.name} : "
            f"{', '.join(sorted(ids_occurrence_sans_document))}."
        )

    ids_manquantes_etape4 = ids_messages - set(details_par_geometrie)
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
        details = details_par_geometrie.get(id_geometrie, {"communes": "", "nature_sonore_zone": ""})
        communes_brutes = details["communes"]
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

        precedent = export_precedent.get(id_geometrie)
        if precedent:
            alert_slug_propose = precedent["alert_slug_propose"]
            description_slug = precedent["description_slug"]
        else:
            alert_slug_propose = f"alert-{_slugifier_territoire(territoire_propose)}-" if territoire_propose else ""
            description_slug = ""

        documents = documents_par_synthese.get(id_geometrie, [])
        message_synthese = _texte(ligne.get("message_synthese"))
        message_strapi = assembler_message(message_synthese, documents)
        strapi_source, strapi_reference = assembler_source_reference(documents)
        label_propose = _label_propose(details["nature_sonore_zone"])
        titre_propose = _texte(ligne.get("titre_propose"))

        nom_fichier_geometrie = f"{id_geometrie}.geojson"
        geodf_ligne = gpd.GeoDataFrame([{"id_geometrie": id_geometrie}], geometry=[ligne.geometry], crs=gdf.crs)
        geodf_ligne.to_file(dossier_geometries / nom_fichier_geometrie, driver="GeoJSON")

        lignes_export.append(
            {
                "id_geometrie": id_geometrie,
                "territoire_propose": territoire_propose,
                "description_slug": description_slug,
                "alert_slug_propose": alert_slug_propose,
                "message_strapi": message_strapi,
                "message_content": message_synthese,
                "strapi_source": strapi_source,
                "strapi_reference": strapi_reference,
                "label_propose": label_propose,
                "titre_propose": titre_propose,
                "nom_fichier_geometrie": nom_fichier_geometrie,
                "communes": communes_brutes,
            }
        )

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

    if export_precedent:
        print(f"{len(export_precedent)} alert_slug déjà saisi(s) repris depuis {chemin_export.name}.")
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
