"""Étape 3 — Phase 3 : synthèse finale.

Consolide le dernier export de l'outil de relecture (`outil_validation.html`)
avec `etape2_{dept}.csv` pour produire le contrat de sortie de l'étape 3 —
l'entrée attendue par l'étape 4 (assignation de géométrie).

Révisé le 17/08/2026, suite à la conception de l'étape 4 : `etape1_{dept}.csv`
n'est plus seulement une source de contexte documentaire, c'est aussi
désormais la source directe des lignes de synthèse RNU et trou de couverture
(voir "Réintégration RNU et trou de couverture" plus bas et
`etape-3-validation-manuelle.md`) — ces communes n'apparaissent jamais dans
`etape2_{dept}.csv`, il n'y a donc rien à y lire pour elles.

Révisé le 26/08/2026 : `etape2_{dept}_erreurs.csv` devient lui aussi une
entrée obligatoire, source directe des lignes `document_non_exploitable`
(voir `_lignes_document_non_exploitable`) — les documents dont la
résolution en pièces a totalement échoué en étape 2 n'apparaissent jamais
dans `etape2_{dept}.csv` non plus, pour la même raison.

Usage :
    python -m etape3_validation_manuelle.synthese_finale --dept 033

Entrée (dans `output/`, voir `--output-dir`) :
    etape1_{dept}.csv                     — contexte documentaire (nom, communes)
                                             ET source directe des lignes RNU
                                             / trou de couverture
    etape2_{dept}.csv                     — référence complète (tous les id_gpu traités)
    etape2_{dept}_erreurs.csv             — source directe des lignes
                                             document_non_exploitable
    etape3_export_outil_{horodatage}.csv  — export(s) de l'outil ; le plus
                                             récent (horodatage le plus
                                             grand) est détecté automatiquement

Sortie (dans le même dossier) :
    etape3_{dept}.csv                  — contrat pour l'étape 4
    etape3_{dept}_rejetees.csv         — audit : occurrences écartées (si non vide)
    etape3_{dept}_non_traitees.csv     — occurrences oubliées par l'opérateur (si non vide)
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

from .contexte_documents import charger_contexte_documents

# Une occurrence "corrigé" a été retouchée par l'opérateur avant validation —
# voir etape-3-validation-manuelle.md, "États de validation". Les deux
# valeurs comptent comme retenues pour la suite du pipeline.
STATUT_VALIDE = "validé"
STATUT_CORRIGE = "corrigé"
STATUTS_RETENUS = {STATUT_VALIDE, STATUT_CORRIGE}
STATUT_AUCUNE_OCCURRENCE = "aucune occurrence trouvée"
# Réservé aux lignes RNU (ajouté le 17/08/2026) : rend explicite qu'aucun
# opérateur ne les a relues, contrairement à validé/corrigé qui supposent un
# passage par l'outil de relecture.
STATUT_VALIDE_AUTOMATIQUE = "validé automatique"

# Valeurs de la colonne `statut` d'etape1_{dept}.csv (voir
# etape1_identification/documents_urbanisme.py) identifiant les communes RNU
# et les trous de couverture, réintégrées ici sans jamais passer par l'outil
# de relecture — voir "Réintégration RNU et trou de couverture" plus bas.
STATUT_ETAPE1_RNU_CONFIRME = "RNU confirmé"
STATUT_ETAPE1_TROU_DE_COUVERTURE = "trou de couverture"
STATUT_ETAPE1_PSMV_ADDITIONNEL = "PSMV additionnel"

# Valeur de `niveau_couverture` (etape1_{dept}.csv) indiquant qu'un document a
# été trouvé au niveau de l'EPCI plutôt qu'au niveau de la commune — voir
# etape1_identification/documents_urbanisme.py (NIVEAU_EPCI).
NIVEAU_COUVERTURE_EPCI = "EPCI"

# Une commune fusionnée/renommée peut avoir son document GPU resté indexé
# sous un ancien code INSEE plutôt que le code actuel — etape1_{dept}.csv
# l'annote alors "{code actuel} (ancien code {ancien code})" (voir
# etape1_identification/synthese.py, _code_insee_avec_origine). C'est ce
# second code, pas le code actuel, qui a été réellement utilisé pour
# rechercher le document, et qu'il faut donc utiliser pour reconstruire
# partition_gpu (voir _partition_gpu ci-dessous).
_PATRON_ANCIEN_CODE = re.compile(r"^\S+ \(ancien code (?P<ancien>\S+)\)$")

# Valeurs de `nature_zone` (ajouté le 17/08/2026) : origine de la ligne,
# déterminante pour le choix du processus de géométrie à l'étape 4 — voir
# etape-3-conception-technique.md, "Contrat de données".
NATURE_OCCURRENCE_LOCALE = "occurrence_locale"
NATURE_RNU = "rnu"
NATURE_DOCUMENT_NON_SIGNIFICATIF = "document_non_significatif"
NATURE_TROU_DE_COUVERTURE = "trou_de_couverture"
# Ajouté le 26/08/2026 : distinct de document_non_significatif — ici le
# document n'a jamais pu être lu (échec de résolution en pièces exploitables,
# phase 1 de l'étape 2 : writingMaterials vide, archive de repli
# indisponible, ou aucun fichier ne correspondant à une pièce attendue),
# alors que document_non_significatif signifie qu'il a bien été lu mais ne
# mentionne rien sur le bruit. Voir "Document non exploitable" dans
# etape-3-validation-manuelle.md.
NATURE_DOCUMENT_NON_EXPLOITABLE = "document_non_exploitable"

# Phase de etape2_{dept}_erreurs.csv identifiant un échec de résolution en
# pièces exploitables (voir etape2_analyse_reglements/resolution_pieces.py).
PHASE_ETAPE2_RESOLUTION = "1-resolution"

# Justification pré-remplie pour chaque ligne RNU (le régime national ne
# vient pas d'un document à citer, contrairement aux occurrences locales) —
# voir etape-3-validation-manuelle.md, "RNU et trou de couverture :
# réintégration dans le pipeline".
JUSTIFICATION_RNU = (
    "Commune soumise au règlement national d'urbanisme (RNU) : l'article "
    "R.111-2 du code de l'urbanisme permet à l'autorité compétente de refuser "
    "un projet, ou de le conditionner à des prescriptions spéciales, s'il "
    "porte atteinte à la salubrité ou à la sécurité publique — la "
    "jurisprudence y range les nuisances sonores."
)

# Fiche Légifrance de la section du code de l'urbanisme portant le RNU
# (articles R.111-1 et suivants) — pas de document GPU à citer pour une
# ligne RNU, ce lien en tient lieu (ajouté le 26/08/2026, corrige un écart
# entre la doc et le code : lien_web_document n'était jamais renseigné pour
# ces lignes malgré la documentation, voir etape-3-conception-technique.md,
# "Contrat de données").
LIEN_LEGIFRANCE_RNU = "https://www.legifrance.gouv.fr/codes/id/LEGISCTA000031721322"

COLONNES_FINALES = [
    "id_gpu",
    "partition_gpu",
    "id_occurrence",
    "code_insee_commune",
    "nature_zone",
    "portee_geometrique",
    "statut_verification_finale",
    "nom_document",
    "communes",
    "type_piece_source",
    "lien_web_document",
    "reference_type",
    "reference_precise",
    "zone_reglementaire_mentionnee",
    "extrait_significatif",
    "contexte_documentaire",
    "confiance_extrait",
    "justification",
    "nature_occurrence",
    "nature_juridique_piece",
    "nature_sonore_zone",
    "ocr_utilise",
    "ocr_confiance",
    "validation_manuelle_statut",
    "validation_manuelle_commentaire",
]


class FichiersEntreeIntrouvables(Exception):
    pass


class ExportOutilInvalide(Exception):
    pass


# Nom généré par exporterCSV() dans outil_validation.html (fonction
# horodatage()) : pas de code département dedans, l'outil étant réutilisable
# tel quel pour n'importe quel département. Chaque clic sur "Exporter", et
# chaque export automatique tous les SEUIL_EXPORT_AUTO traitements, produit
# un nouveau fichier plutôt que d'écraser le précédent — d'où la nécessité de
# repérer le plus récent plutôt que d'attendre un nom fixe.
PATRON_EXPORT_OUTIL = re.compile(r"^etape3_export_outil_(\d{8}_\d{6})\.csv$")


def _dernier_export(dossier: Path) -> Path:
    """Retourne le fichier `etape3_export_outil_{horodatage}.csv` le plus
    récent du dossier, l'horodatage encodé dans le nom (format
    `AAAAMMJJ_HHMMSS`) servant de clé de tri plutôt que la date de
    modification du fichier, moins fiable (copie, synchro, téléchargement
    différé...).
    """
    candidats = sorted(
        (correspondance.group(1), chemin)
        for chemin in dossier.glob("etape3_export_outil_*.csv")
        if (correspondance := PATRON_EXPORT_OUTIL.match(chemin.name))
    )
    if not candidats:
        raise FichiersEntreeIntrouvables(
            f"{dossier / 'etape3_export_outil_*.csv'} (aucun export de outil_validation.html trouvé)"
        )
    return candidats[-1][1]


def _code_insee_pour_partition(code_insee_commune: str) -> str:
    correspondance = _PATRON_ANCIEN_CODE.match(code_insee_commune)
    return correspondance.group("ancien") if correspondance else code_insee_commune


def _partition_gpu(ligne_etape1: dict[str, str]) -> str:
    """Construit la valeur attendue par le paramètre `partition` de la couche
    `document` de l'API Carto GPU (format `<DU/PSMV>_<INSEE/SIREN>`) — voir
    `etape-3-conception-technique.md`, "Calcul de partition_gpu". `id_gpu`
    seul ne suffit pas : ce n'est pas la valeur attendue par ce paramètre."""
    famille = "PSMV" if ligne_etape1["statut"] == STATUT_ETAPE1_PSMV_ADDITIONNEL else "DU"
    if ligne_etape1["niveau_couverture"] == NIVEAU_COUVERTURE_EPCI:
        code = ligne_etape1["code_siren_epci"]
    else:
        code = _code_insee_pour_partition(ligne_etape1["code_insee_commune"])
    return f"{famille}_{code}"


def _partitions_gpu_par_id_gpu(lignes_etape1: list[dict[str, str]]) -> dict[str, str]:
    """Une entrée par `id_gpu` distinct (déduplication déjà pratiquée par le
    reste du pipeline, voir etape2_analyse_reglements/resolution_pieces.py :
    un PLUi intercommunal apparaît sur autant de lignes que de communes
    couvertes, mais une seule valeur partition_gpu lui correspond)."""
    partitions: dict[str, str] = {}
    for ligne in lignes_etape1:
        id_gpu = ligne.get("id_gpu", "")
        if id_gpu and id_gpu not in partitions:
            partitions[id_gpu] = _partition_gpu(ligne)
    return partitions


def _ligne_rnu(ligne_etape1: dict[str, str]) -> dict[str, str]:
    nouvelle = {colonne: "" for colonne in COLONNES_FINALES}
    nouvelle.update(
        code_insee_commune=ligne_etape1["code_insee_commune"],
        nature_zone=NATURE_RNU,
        portee_geometrique="administrative",
        statut_verification_finale=STATUT_VALIDE_AUTOMATIQUE,
        communes=ligne_etape1["nom_commune"],
        justification=JUSTIFICATION_RNU,
        lien_web_document=LIEN_LEGIFRANCE_RNU,
    )
    return nouvelle


def _ligne_trou_de_couverture(ligne_etape1: dict[str, str]) -> dict[str, str]:
    nouvelle = {colonne: "" for colonne in COLONNES_FINALES}
    nouvelle.update(
        code_insee_commune=ligne_etape1["code_insee_commune"],
        nature_zone=NATURE_TROU_DE_COUVERTURE,
        statut_verification_finale=STATUT_AUCUNE_OCCURRENCE,
        communes=ligne_etape1["nom_commune"],
    )
    return nouvelle


def _lignes_document_non_exploitable(
    lignes_etape2_erreurs: list[dict[str, str]],
    partitions_gpu: dict[str, str],
    contexte_documents: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    """Documents dont la résolution en pièces exploitables a totalement
    échoué en phase 1 de l'étape 2 (voir etape2_analyse_reglements/
    resolution_pieces.py). N'apparaissent jamais dans etape2_{dept}.csv —
    rien n'a pu en être extrait — donc jamais parmi `id_gpu_non_significatifs`
    ci-dessous non plus : sans cette réintégration depuis
    etape2_{dept}_erreurs.csv, ils disparaîtraient silencieusement de la
    synthèse finale (voir "Document non exploitable" dans
    etape-3-validation-manuelle.md).
    """
    ids_gpu = sorted(
        {
            ligne["id_gpu"]
            for ligne in lignes_etape2_erreurs
            if ligne.get("phase") == PHASE_ETAPE2_RESOLUTION and ligne.get("id_gpu")
        }
    )
    lignes: list[dict[str, str]] = []
    for id_gpu in ids_gpu:
        contexte = contexte_documents.get(id_gpu, {})
        nouvelle = {colonne: "" for colonne in COLONNES_FINALES}
        nouvelle.update(
            id_gpu=id_gpu,
            partition_gpu=partitions_gpu.get(id_gpu, ""),
            nature_zone=NATURE_DOCUMENT_NON_EXPLOITABLE,
            statut_verification_finale=STATUT_AUCUNE_OCCURRENCE,
            nom_document=contexte.get("nom_document", "(document non identifié)"),
            communes=contexte.get("communes", ""),
        )
        lignes.append(nouvelle)
    return lignes


def _lignes_rnu_et_trous(lignes_etape1: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Construit les lignes de synthèse RNU et trou de couverture directement
    depuis `etape1_{dept}.csv` (voir etape-3-validation-manuelle.md, "RNU et
    trou de couverture : réintégration dans le pipeline") — ces communes
    n'apparaissent jamais dans etape2_{dept}.csv ni dans un export de l'outil,
    donc jamais dans `retenues`/`id_gpu_non_significatifs` ci-dessus."""
    rnu = [
        _ligne_rnu(ligne) for ligne in lignes_etape1 if ligne.get("statut") == STATUT_ETAPE1_RNU_CONFIRME
    ]
    trous = [
        _ligne_trou_de_couverture(ligne)
        for ligne in lignes_etape1
        if ligne.get("statut") == STATUT_ETAPE1_TROU_DE_COUVERTURE
    ]
    return rnu, trous


def _lire_csv(chemin: Path) -> list[dict[str, str]]:
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        return list(csv.DictReader(fichier))


def _ecrire_csv(chemin: Path, colonnes: list[str], lignes: list[dict[str, str]]) -> None:
    with chemin.open("w", newline="", encoding="utf-8-sig") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=colonnes, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(lignes)


def synthetiser(code_departement: str, dossier_sortie: str | Path = "output") -> Path:
    dossier = Path(dossier_sortie)
    chemin_etape1 = dossier / f"etape1_{code_departement}.csv"
    chemin_etape2 = dossier / f"etape2_{code_departement}.csv"
    chemin_etape2_erreurs = dossier / f"etape2_{code_departement}_erreurs.csv"

    manquants = [str(c) for c in (chemin_etape1, chemin_etape2, chemin_etape2_erreurs) if not c.exists()]
    if manquants:
        raise FichiersEntreeIntrouvables(", ".join(manquants))

    chemin_export = _dernier_export(dossier)
    print(f"Dernier export de l'outil détecté : {chemin_export.name}")

    contexte_documents = charger_contexte_documents(chemin_etape1)
    lignes_etape1 = _lire_csv(chemin_etape1)
    lignes_etape2 = _lire_csv(chemin_etape2)
    lignes_etape2_erreurs = _lire_csv(chemin_etape2_erreurs)
    lignes_export = _lire_csv(chemin_export)
    partitions_gpu = _partitions_gpu_par_id_gpu(lignes_etape1)

    if lignes_export and "validation_manuelle_statut" not in lignes_export[0]:
        raise ExportOutilInvalide(
            "le fichier exporté ne contient pas la colonne validation_manuelle_statut "
            "— vérifiez qu'il s'agit bien d'un export de outil_validation.html, pas d'un autre CSV."
        )

    colonnes_export = list(lignes_export[0].keys()) if lignes_export else []
    non_traitees = [l for l in lignes_export if not l.get("validation_manuelle_statut")]
    traitees = [l for l in lignes_export if l.get("validation_manuelle_statut")]
    retenues = [l for l in traitees if l["validation_manuelle_statut"] in STATUTS_RETENUS]
    rejetees = [l for l in traitees if l["validation_manuelle_statut"] not in STATUTS_RETENUS]

    if non_traitees:
        chemin_non_traitees = dossier / f"etape3_{code_departement}_non_traitees.csv"
        _ecrire_csv(chemin_non_traitees, colonnes_export, non_traitees)
        print(
            f"Attention : {len(non_traitees)} occurrence(s) non traitée(s) par "
            f"l'opérateur, listée(s) dans {chemin_non_traitees}. Exclue(s) de "
            "la sortie finale — à reprendre avant de considérer le "
            "département terminé."
        )

    if rejetees:
        chemin_rejetees = dossier / f"etape3_{code_departement}_rejetees.csv"
        _ecrire_csv(chemin_rejetees, colonnes_export, rejetees)
        print(
            f"{len(rejetees)} occurrence(s) rejetée(s), conservée(s) pour "
            f"traçabilité dans {chemin_rejetees} (pas de suppression silencieuse)."
        )

    # Un document (id_gpu) est non significatif si aucune de ses occurrences
    # n'est retenue — que ce soit parce qu'aucune occurrence n'a jamais été
    # relevée en étape 2 (jamais soumis à relecture), ou parce que toutes ont
    # été rejetées ou laissées non traitées en étape 3. Une seule ligne de
    # synthèse le représente — voir etape-3-validation-manuelle.md,
    # "Agrégation par document".
    id_gpu_significatifs = {l["id_gpu"] for l in retenues}
    tous_les_id_gpu = {l["id_gpu"] for l in lignes_etape2}
    id_gpu_non_significatifs = tous_les_id_gpu - id_gpu_significatifs

    lignes_sortie: list[dict[str, str]] = []
    for ligne in retenues:
        nouvelle = {colonne: ligne.get(colonne, "") for colonne in COLONNES_FINALES}
        nouvelle["statut_verification_finale"] = ligne["validation_manuelle_statut"]
        nouvelle["nature_zone"] = NATURE_OCCURRENCE_LOCALE
        nouvelle["partition_gpu"] = partitions_gpu.get(ligne["id_gpu"], "")
        lignes_sortie.append(nouvelle)

    for id_gpu in sorted(id_gpu_non_significatifs):
        contexte = contexte_documents.get(id_gpu, {})
        nouvelle = {colonne: "" for colonne in COLONNES_FINALES}
        nouvelle.update(
            id_gpu=id_gpu,
            partition_gpu=partitions_gpu.get(id_gpu, ""),
            nature_zone=NATURE_DOCUMENT_NON_SIGNIFICATIF,
            statut_verification_finale=STATUT_AUCUNE_OCCURRENCE,
            nom_document=contexte.get("nom_document", "(document non identifié)"),
            communes=contexte.get("communes", ""),
        )
        lignes_sortie.append(nouvelle)

    # Réintégration RNU et trou de couverture (ajouté le 17/08/2026) : lignes
    # de synthèse construites directement depuis etape1_{dept}.csv, jamais
    # soumises à l'outil de relecture — voir "RNU et trou de couverture :
    # réintégration dans le pipeline" dans etape-3-validation-manuelle.md.
    lignes_rnu, lignes_trou_de_couverture = _lignes_rnu_et_trous(lignes_etape1)
    lignes_sortie.extend(lignes_rnu)
    lignes_sortie.extend(lignes_trou_de_couverture)

    # Réintégration des documents non exploitables (ajouté le 26/08/2026) :
    # comme RNU et trou de couverture ci-dessus, construite depuis une source
    # qui ne passe jamais par l'outil de relecture — voir "Document non
    # exploitable" dans etape-3-validation-manuelle.md.
    lignes_non_exploitables = _lignes_document_non_exploitable(
        lignes_etape2_erreurs, partitions_gpu, contexte_documents
    )
    lignes_sortie.extend(lignes_non_exploitables)

    lignes_sortie.sort(key=lambda l: (l["nom_document"], l["communes"], l["id_occurrence"]))

    chemin_sortie = dossier / f"etape3_{code_departement}.csv"
    _ecrire_csv(chemin_sortie, COLONNES_FINALES, lignes_sortie)
    print(
        f"{len(lignes_sortie)} ligne(s) écrite(s) dans {chemin_sortie} "
        f"({len(retenues)} occurrence(s) significative(s), "
        f"{len(id_gpu_non_significatifs)} document(s) non significatif(s), "
        f"{len(lignes_rnu)} commune(s) RNU, "
        f"{len(lignes_trou_de_couverture)} trou(s) de couverture, "
        f"{len(lignes_non_exploitables)} document(s) non exploitable(s))."
    )
    return chemin_sortie


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Consolide l'export de l'outil de validation manuelle avec etape2_{dept}.csv."
    )
    parser.add_argument(
        "--dept",
        required=True,
        help="Code département diagBruit, 3 chiffres (ex. 033, 971).",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Dossier de lecture/écriture des CSV (défaut : output/).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    print(f"Étape 3, phase 3 — département {args.dept}")
    try:
        synthetiser(args.dept, dossier_sortie=args.output_dir)
    except FichiersEntreeIntrouvables as exc:
        print(f"Arrêt : fichier(s) d'entrée introuvable(s) : {exc}", file=sys.stderr)
        return 1
    except ExportOutilInvalide as exc:
        print(f"Arrêt : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
