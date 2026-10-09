"""Étape 4 — Contrôle de la portée administrative (lecture seule).

Ajouté le 09/10/2026, suite au diagnostic des doublons de messages du 067
hors Eurométropole (voir `docs/diagnostic-portee-administrative-067.md`) :
la portée `administrative` est décidée par le LLM à l'étape 2, avec un choix
par défaut vers `administrative` quand le passage ne nomme pas de zone, et
plus rien ne la contrôle ensuite. Or la couche `geometries_administratives`
n'est pas relue en Phase 2 (sa géométrie, le contour du document, est
correcte) : une règle en réalité propre à une zone y passe donc inaperçue,
et finit appliquée à toute la commune.

Ce script ne corrige rien, et peut être relancé à tout moment pendant la
Phase 2 : il relit la colonne `verification_portee` saisie dans QGIS et
affiche l'avancement de la relecture. Il liste toutes les occurrences réelles
(`nature_zone == "occurrence_locale"`) de `geometries_administratives`, avec
un niveau de suspicion calculé à partir de cinq indices, pour que
l'opérateur sache lesquelles vérifier en priorité dans le PDF avant ou
pendant la Phase 2. Voir `docs/etape-4-conception-technique.md`,
"Contrôle de la portée administrative (`controle_portee.py`)".

Usage :
    python -m etape4_geometries.controle_portee --dept 033

Entrées (dans `output/`, voir `--output-dir`) :
    etape4_{dept}_a_completer.gpkg — les deux couches, jamais modifiées ici
    etape3_{dept}.csv              — relu pour `contexte_documentaire` et
                                     `extrait_significatif`, absents du gpkg

Sortie (dans le même dossier, réécrite à chaque exécution) :
    etape4_{dept}_portee_a_verifier.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import geopandas as gpd

from .preparer_geometries import COUCHE_A_GEOREFERENCER, COUCHE_ADMINISTRATIVE

NATURE_ZONE_REGLE = "occurrence_locale"

# Code de zone de PLU tel qu'on le trouve dans les règlements : U, UA, 1AU,
# AUh, 1AUe, A1, N... (une lettre de base U/AU/A/N, éventuellement précédée
# de 1 ou 2, suivie d'au plus 4 caractères de sous-secteur). Utilisé
# uniquement à la suite d'un mot-clé ("zone", "secteur", "article") : seul,
# il reconnaîtrait n'importe quel mot court commençant par a, n ou u.
CODE_ZONE = r"(?:1|2)?(?:AU|U|A|N)[a-z0-9]{0,4}"

# C2 — la référence ressemble à un article de zone : "Article AU5",
# "Article au6", "Art. 2-UC". "Article 2" ou "Article 11" seuls ne
# déclenchent rien (il faut une lettre de zone après le numéro).
MOTIF_REFERENCE_ZONE = re.compile(rf"\b(?:article|art\.?)\s*[0-9.]*\s*-?\s*{CODE_ZONE}\b", re.IGNORECASE)

# C3 — la justification du LLM parle d'une zone : "de la zone",
# "dans la zone", "en zone", "zone UA", "secteur 1AUh". Indice plus faible
# que C2 : "la zone" peut aussi désigner une zone de bruit.
MOTIF_JUSTIFICATION_ZONE = re.compile(
    rf"\b(?:de|dans|en)\s+(?:la\s+)?zones?\b|\bzone\s+{CODE_ZONE}\b|\bsecteurs?\s+{CODE_ZONE}\b",
    re.IGNORECASE,
)

# C4 — le contexte documentaire (texte autour du passage) nomme une zone :
# "zone UC", "secteur 1AU", "Art. 2-UC".
MOTIF_CONTEXTE_ZONE = re.compile(
    rf"\bzone\s+{CODE_ZONE}\b|\bsecteurs?\s+{CODE_ZONE}\b|\b(?:article|art\.?)\s*[0-9]*\s*-\s*{CODE_ZONE}\b",
    re.IGNORECASE,
)

# C5 — exception : une zone mentionnée du type "Toutes les zones U, AU, A,
# N" est cohérente avec une portée administrative (cas réel : Weitbruch).
MOTIF_TOUTES_ZONES = re.compile(r"^\s*tou", re.IGNORECASE)

# Libellés préfixés d'un chiffre : un simple tri alphabétique (Excel,
# LibreOffice) remet ainsi les lignes dans l'ordre de priorité.
NIVEAU_FORTE = "1 - forte"
NIVEAU_MOYENNE = "2 - moyenne"
NIVEAU_FAIBLE = "3 - faible"
NIVEAU_AUCUN = "4 - aucun signal"

# Ajouté le 09/10/2026 : suivi de la vérification, saisi par l'opérateur
# dans QGIS (colonne verification_portee de geometries_administratives) —
# le CSV produit ici est réécrit à chaque exécution, la décision doit donc
# vivre dans le gpkg, là où la correction est faite.
VERIFICATION_CONFIRMEE = "confirmée"
VERIFICATION_CORRIGEE = "corrigée"
VERIFICATION_REJETEE = "rejetée"
STATUT_GEOMETRIE_REJETE = "rejeté"  # même valeur que synthese_geometries.STATUT_GEOMETRIE_REJETE

COLONNES_SORTIE = [
    "niveau",
    "verification_portee",
    "statut_geometrie",
    "alerte",
    "criteres",
    "id_geometrie",
    "id_gpu",
    "id_occurrence",
    "communes",
    "nom_document",
    "type_piece_source",
    "reference_precise",
    "numero_page",
    "zone_reglementaire_mentionnee",
    "nature_sonore_zone",
    "justification",
    "extrait_significatif",
    "contexte_documentaire",
    "lien_web_document",
]


class FichierIntrouvable(Exception):
    pass


def _texte(valeur) -> str:
    """Valeur d'attribut en texte. Un champ vide relu depuis le gpkg peut
    revenir en None ou en NaN (voir synthese_geometries._texte) — NaN est
    le seul float différent de lui-même, d'où le test `valeur != valeur`."""
    if valeur is None or (isinstance(valeur, float) and valeur != valeur):
        return ""
    return str(valeur).strip()


def _lire_etape3(chemin: Path) -> dict[tuple[str, str], dict[str, str]]:
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        return {(l["id_gpu"], l["id_occurrence"]): l for l in csv.DictReader(fichier) if l.get("id_occurrence")}


def evaluer(occurrence: dict, contexte: str, document_mixte: bool) -> tuple[str, list[str]]:
    """Renvoie (niveau, liste des indices relevés, en clair) pour une
    occurrence de la couche administrative.

    Combinaison retenue le 09/10/2026, mesurée sur le 067 hors
    Eurométropole (52 occurrences) :
    - forte   : C5 ou C2 — la donnée elle-même contredit la portée ;
    - moyenne : règlement écrit, avec C3 ou C4 — indice dans le texte, dans
                la pièce où une règle de zone est la plus probable ;
    - faible  : C1 seul — le document mélange les deux portées ;
    - aucun   : aucun indice (souvent PADD/OAP, où une portée administrative
                est habituellement légitime).
    """
    indices: list[str] = []

    zone = _texte(occurrence.get("zone_reglementaire_mentionnee"))
    c5 = bool(zone) and not MOTIF_TOUTES_ZONES.match(zone)
    if c5:
        indices.append(f"C5 zone mentionnée « {zone} » malgré la portée administrative")

    reference = _texte(occurrence.get("reference_precise"))
    c2 = bool(MOTIF_REFERENCE_ZONE.search(reference))
    if c2:
        indices.append(f"C2 référence d'article de zone « {reference} »")

    c3 = bool(MOTIF_JUSTIFICATION_ZONE.search(_texte(occurrence.get("justification"))))
    if c3:
        indices.append("C3 la justification parle d'une zone")

    c4 = bool(MOTIF_CONTEXTE_ZONE.search(contexte))
    if c4:
        indices.append("C4 le contexte documentaire nomme une zone")

    if document_mixte:
        indices.append("C1 le document a aussi des occurrences zone_specifique")

    est_reglement = _texte(occurrence.get("type_piece_source")).lower().startswith("règlement")

    if c5 or c2:
        niveau = NIVEAU_FORTE
    elif est_reglement and (c3 or c4):
        niveau = NIVEAU_MOYENNE
    elif document_mixte:
        niveau = NIVEAU_FAIBLE
    else:
        niveau = NIVEAU_AUCUN
    return niveau, indices


def alerte_saisie(verification: str, statut_geometrie: str) -> str:
    """Repère une saisie incohérente entre les deux colonnes remplies à la
    main dans QGIS. Seul `statut_geometrie = "rejeté"` retire réellement la
    ligne du livrable (synthese_geometries.py) ; `verification_portee` n'est
    qu'un suivi. Oublier l'un des deux est facile : on le signale ici plutôt
    que de le découvrir à l'étape 5."""
    if verification == VERIFICATION_REJETEE and statut_geometrie != STATUT_GEOMETRIE_REJETE:
        return "verification_portee = rejetée mais statut_geometrie ≠ rejeté : la ligne restera dans le livrable"
    if statut_geometrie == STATUT_GEOMETRIE_REJETE and verification not in ("", VERIFICATION_REJETEE):
        return f"statut_geometrie = rejeté mais verification_portee = {verification}"
    if verification and verification not in (VERIFICATION_CONFIRMEE, VERIFICATION_CORRIGEE, VERIFICATION_REJETEE):
        return f"valeur inattendue « {verification} » (attendu : confirmée, corrigée ou rejetée)"
    return ""


def controler(code_departement: str, dossier_sortie: str | Path = "output") -> Path:
    dossier = Path(dossier_sortie)
    chemin_gpkg = dossier / f"etape4_{code_departement}_a_completer.gpkg"
    chemin_etape3 = dossier / f"etape3_{code_departement}.csv"
    for chemin in (chemin_gpkg, chemin_etape3):
        if not chemin.exists():
            raise FichierIntrouvable(str(chemin))

    # ignore_geometry : seuls les attributs servent ici, et le fichier n'est
    # jamais réécrit — lecture plus rapide, aucun risque pour la Phase 2.
    administratives = gpd.read_file(chemin_gpkg, layer=COUCHE_ADMINISTRATIVE, ignore_geometry=True)
    a_georeferencer = gpd.read_file(chemin_gpkg, layer=COUCHE_A_GEOREFERENCER, ignore_geometry=True)
    index_etape3 = _lire_etape3(chemin_etape3)

    # C1 — documents qui ont au moins une vraie règle classée zone_specifique.
    documents_avec_zone = {
        _texte(l["id_gpu"])
        for _, l in a_georeferencer.iterrows()
        if _texte(l.get("nature_zone")) == NATURE_ZONE_REGLE
    }

    lignes_sortie: list[dict] = []
    for _, occurrence in administratives.iterrows():
        if _texte(occurrence.get("nature_zone")) != NATURE_ZONE_REGLE:
            continue  # RNU, document non significatif... : aucune règle à interpréter

        id_gpu = _texte(occurrence.get("id_gpu"))
        id_occurrence = _texte(occurrence.get("id_occurrence"))
        ligne_etape3 = index_etape3.get((id_gpu, id_occurrence), {})
        contexte = ligne_etape3.get("contexte_documentaire", "") or ""

        niveau, indices = evaluer(occurrence, contexte, id_gpu in documents_avec_zone)
        # occurrence.get() renvoie None si la colonne n'existe pas encore
        # dans le gpkg (ajout manuel dans QGIS pas encore fait) : _texte()
        # en fait une chaîne vide, soit "pas encore vérifiée".
        verification = _texte(occurrence.get("verification_portee"))
        statut_geometrie = _texte(occurrence.get("statut_geometrie"))
        lignes_sortie.append(
            {
                **{colonne: _texte(occurrence.get(colonne)) for colonne in COLONNES_SORTIE if colonne in occurrence},
                "niveau": niveau,
                "verification_portee": verification,
                "statut_geometrie": statut_geometrie,
                "alerte": alerte_saisie(verification, statut_geometrie),
                "criteres": " ; ".join(indices),
                "numero_page": ligne_etape3.get("numero_page", ""),
                "extrait_significatif": ligne_etape3.get("extrait_significatif", ""),
                "contexte_documentaire": contexte,
            }
        )

    # Tri : priorité d'abord, puis document (les occurrences d'un même PDF
    # se suivent, pour ne l'ouvrir qu'une fois), puis id_geometrie.
    lignes_sortie.sort(key=lambda l: (l["niveau"], l["nom_document"], int(l["id_geometrie"] or 0)))

    chemin_sortie = dossier / f"etape4_{code_departement}_portee_a_verifier.csv"
    with chemin_sortie.open("w", newline="", encoding="utf-8-sig") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=COLONNES_SORTIE)
        writer.writeheader()
        writer.writerows({colonne: ligne.get(colonne, "") for colonne in COLONNES_SORTIE} for ligne in lignes_sortie)

    # Avancement par niveau : "vérifiées" = verification_portee renseignée.
    print(f"{len(lignes_sortie)} occurrence(s) à portée administrative examinée(s) :")
    for niveau in (NIVEAU_FORTE, NIVEAU_MOYENNE, NIVEAU_FAIBLE, NIVEAU_AUCUN):
        du_niveau = [l for l in lignes_sortie if l["niveau"] == niveau]
        verifiees = sum(1 for l in du_niveau if l["verification_portee"])
        print(f"  {niveau} : {len(du_niveau)} (dont {verifiees} vérifiée(s))")
    alertes = [l for l in lignes_sortie if l["alerte"]]
    for ligne in alertes:
        print(f"  ⚠ g{ligne['id_geometrie']} : {ligne['alerte']}")
    print(f"Liste écrite dans {chemin_sortie} (aucun fichier d'entrée modifié).")
    return chemin_sortie


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Liste les occurrences à portée administrative de l'étape 4, avec un niveau de suspicion."
    )
    parser.add_argument(
        "--dept",
        required=True,
        help="Code département diagBruit (ex. 033, 067) — doit correspondre à un etape4_{dept}_a_completer.gpkg existant.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Dossier de lecture/écriture des fichiers (défaut : output/).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    print(f"Étape 4, contrôle de la portée administrative — département {args.dept}")
    try:
        controler(args.dept, dossier_sortie=args.output_dir)
    except FichierIntrouvable as exc:
        print(f"Arrêt : fichier introuvable ({exc}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
