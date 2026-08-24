"""Étape 5 — Phase 2 : génération des messages (`message_occurrence` et
`message_synthese`) par LLM, voir `docs/etape-5-conception-technique.md`,
"Phase 2".

Lit `etape4_{dept}.gpkg`, reconstruit les groupes fusionnés (voir
`etape4_geometries/synthese_geometries.py`, "Mécanisme de fusion"), et pour
chaque géométrie finale :

- `nature_zone != "occurrence_locale"` (`rnu`/`document_non_significatif`/
  `trou_de_couverture`) → le message fixe correspondant
  (`messages_fixes.py`), aucun appel LLM ;
- `nature_zone == "occurrence_locale"` → un appel LLM par occurrence du
  groupe (`message_occurrence`, jamais montré à l'utilisateur final), puis,
  si le groupe compte plus d'une occurrence, un second appel LLM qui les
  combine en un unique `message_synthese`. Pour un groupe d'une seule
  occurrence, `message_synthese` reprend directement `message_occurrence`.
  Dans tous les cas, un troisième appel LLM génère ensuite `titre_propose_llm`
  (titre court, quelques mots) à partir de ce `message_synthese`. Pour les
  cas fixes, un titre fixe (`TITRES_FIXES`) est utilisé à la place, comme
  pour le message.

Usage :
    python -m etape5_redaction_messages.preparer_messages --dept 033

Entrée (dans `output/`, voir `--output-dir`) :
    etape4_{dept}.gpkg
    etape3_{dept}.csv — relu pour `extrait_significatif`/`contexte_documentaire`/
                         `nature_occurrence`, absents du contrat de l'étape 4

Sortie (dans le même dossier) :
    etape5_{dept}_a_completer.gpkg           — une géométrie par ligne, `message_synthese`
                                                proposé ; à relire en Phase 3
    etape5_{dept}_occurrences.csv            — un message individuel par occurrence,
                                                support de la Phase 3
    etape5_{dept}_documents_par_synthese.csv — un document par ligne (voir "Contrat de
                                                données" dans etape-5-conception-technique.md)
    etape5_{dept}_erreurs.csv                — échecs d'appel LLM isolés, si non vide
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import anthropic
import geopandas as gpd
import pandas as pd
from anthropic import Anthropic
from dotenv import load_dotenv
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .messages_fixes import MESSAGES_FIXES, TITRES_FIXES
from .ton_de_voix import TON_DE_VOIX

load_dotenv()


class CleApiManquante(Exception):
    """ANTHROPIC_API_KEY absente de l'environnement ou du fichier .env."""


if not os.environ.get("ANTHROPIC_API_KEY"):
    raise CleApiManquante(
        "ANTHROPIC_API_KEY n'est pas définie. Copier .env.example vers .env "
        "à la racine de poc-urbanisme-plu/ et y renseigner une clé créée sur "
        "la Console Anthropic (console.anthropic.com)."
    )

client = Anthropic()

# Même modèle que l'étape 2 (classification.py), pour la même raison :
# bon équilibre qualité/coût pour du texte français, avec une vérification
# humaine prévue en aval (Phase 3 de cette étape).
MODELE_REDACTION = "claude-sonnet-5"

NATURE_ZONE_ELIGIBLE = "occurrence_locale"

SCHEMA_MESSAGE_OCCURRENCE = {
    "type": "object",
    "properties": {"message_occurrence": {"type": "string"}},
    "required": ["message_occurrence"],
    "additionalProperties": False,
}

SCHEMA_MESSAGE_SYNTHESE = {
    "type": "object",
    "properties": {"message_synthese": {"type": "string"}},
    "required": ["message_synthese"],
    "additionalProperties": False,
}

# Appel dédié et uniforme, un par géométrie finale (occurrence unique ou
# groupe fusionné), toujours généré
# à partir du message_synthese natif (jamais de la version corrigée en
# Phase 3, même principe que "Correction humaine : natif + correction,
# jamais de cascade" pour message_synthese).
SCHEMA_TITRE = {
    "type": "object",
    "properties": {"titre_propose": {"type": "string"}},
    "required": ["titre_propose"],
    "additionalProperties": False,
}

COLONNES_OCCURRENCES = [
    "id_geometrie_synthese",
    "id_gpu",
    "id_occurrence",
    "message_occurrence",
    # Correction humaine (Phase 3, voir outil_validation.html) — jamais
    # remplies ici, écrites vides par Phase 2 : message_occurrence reste la
    # sortie native du LLM, jamais réécrite en place (voir
    # etape-5-conception-technique.md, "Correction humaine : natif +
    # correction, jamais de cascade").
    "occurrence_corrigee",
    "message_occurrence_corrige",
    "validation_message_commentaire",
    "extrait_significatif",
    "contexte_documentaire",
    "justification",
    "lien_web_document",
    "reference_precise",
    "nature_sonore_zone",
]

COLONNES_DOCUMENTS = [
    "id_geometrie_synthese",
    "id_gpu",
    "nature",
    "lien_web_document",
    "reference_precise",
]

# message_synthese_llm : sortie native du LLM, jamais réécrite en place —
# même principe que message_occurrence ci-dessus. La valeur "active" (native
# ou corrigée) n'est calculée qu'à la Phase 4 (synthese_messages.py), jamais
# ici.
# titre_propose_llm : même principe, sortie native de _generer_titre (ou du
# titre fixe pour rnu/document_non_significatif/trou_de_couverture), jamais
# réécrite en place. validation_message_commentaire reste partagé entre les
# deux corrections (message et titre) de la ligne — pas de colonne dédiée.
COLONNES_SYNTHESES = [
    "id_geometrie",
    "id_gpu",
    "id_occurrence",
    "message_synthese_llm",
    "synthese_corrigee",
    "message_synthese_corrige",
    "titre_propose_llm",
    "titre_corrigee",
    "titre_propose_corrige",
    "validation_message_commentaire",
]

COLONNES_ERREURS = ["identifiant", "source", "message", "date_traitement"]


class GpkgIntrouvable(Exception):
    pass


class Etape3CsvIntrouvable(Exception):
    pass


class _ErreurRedaction(Exception):
    """Échec de l'appel de génération pour une occurrence ou une synthèse."""


def _texte(valeur) -> str:
    """Normalise une valeur d'attribut en texte, en traitant `None`/`NaN`
    comme une chaîne vide — même bug que celui corrigé dans
    `etape4_geometries/synthese_geometries.py` (`_texte`). Réimplémenté ici
    plutôt qu'importé : chaque étape du pipeline reste indépendante du code
    des autres étapes, seule la donnée circule entre elles (voir
    `etape-1-conception-technique.md`, "Décision 2")."""
    if valeur is None:
        return ""
    if isinstance(valeur, float) and pd.isna(valeur):
        return ""
    return str(valeur).strip()


def _cle(ligne: pd.Series) -> tuple[str, str]:
    return (_texte(ligne.get("id_gpu")), _texte(ligne.get("id_occurrence")))


def _cle_groupe(ligne: pd.Series) -> tuple[str, str]:
    """Clé du meneur du groupe auquel appartient `ligne` — sa propre clé si
    elle n'a pas de fusion déclarée (meneur ou occurrence isolée), sinon la
    clé référencée par `fusionne_avec_id_gpu`/`fusionne_avec_id_occurrence`."""
    fusion = (_texte(ligne.get("fusionne_avec_id_gpu")), _texte(ligne.get("fusionne_avec_id_occurrence")))
    if fusion != ("", ""):
        return fusion
    return _cle(ligne)


def _lire_etape3(chemin: Path) -> dict[tuple[str, str], dict[str, str]]:
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        return {(l["id_gpu"], l["id_occurrence"]): l for l in csv.DictReader(fichier) if l.get("id_occurrence")}


@retry(
    retry=retry_if_exception_type(
        (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError)
    ),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _appeler_claude(prompt: str, schema: dict) -> anthropic.types.Message:
    return client.messages.create(
        model=MODELE_REDACTION,
        max_tokens=800,
        thinking={"type": "disabled"},
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )


def _extraire_champ(response: anthropic.types.Message, champ: str) -> str:
    if response.stop_reason == "refusal":
        raise _ErreurRedaction("le modèle a refusé de répondre (stop_reason=refusal)")
    if response.stop_reason == "max_tokens":
        raise _ErreurRedaction("réponse tronquée (stop_reason=max_tokens)")
    try:
        texte_reponse = next(bloc.text for bloc in response.content if bloc.type == "text")
        return json.loads(texte_reponse)[champ]
    except (StopIteration, json.JSONDecodeError, KeyError) as exc:
        raise _ErreurRedaction(f"réponse inexploitable : {exc}") from exc


def _construire_prompt_occurrence(donnees_etape4: pd.Series, donnees_etape3: dict[str, str]) -> str:
    nature = _texte(donnees_etape3.get("nature_occurrence"))
    return f"""Tu rédiges, pour diagBruit (service public d'information sur le bruit), un
message à l'intention d'un porteur de projet ou d'un professionnel de
l'urbanisme qui consulte le diagnostic bruit d'une parcelle. Le message
résume UNE règle issue d'un document d'urbanisme, extraite du passage
ci-dessous. Respecte le ton de voix suivant :

{TON_DE_VOIX}

Nature de la règle : {nature or "non précisée"} — "prescription" est une
obligation, "recommandation" est un conseil non obligatoire : formule le
message différemment selon le cas (verbe d'obligation vs verbe de conseil).

Type de pièce source : {_texte(donnees_etape4.get("type_piece_source"))}
Référence précise : {_texte(donnees_etape4.get("reference_precise"))}
Zone réglementaire mentionnée : {_texte(donnees_etape4.get("zone_reglementaire_mentionnee")) or "non précisée"}

Citation exacte extraite du document : "{_texte(donnees_etape3.get("extrait_significatif"))}"
Contexte de la citation : "{_texte(donnees_etape3.get("contexte_documentaire"))}"
Raisonnement d'un modèle qui a extrait cette citation à une étape antérieure
du pipeline (aide à la compréhension, ne jamais citer directement) :
{_texte(donnees_etape4.get("justification"))}

Rédige un message court (2 à 4 phrases), fidèle à la citation ci-dessus,
sans y ajouter d'information qu'elle ne contient pas. Ne mentionne jamais
l'existence d'une "citation", d'un "document source" au sens interne du
pipeline, ni le processus d'extraction — le message s'adresse à
l'utilisateur final, pas à un opérateur du pipeline."""


def _construire_prompt_synthese(messages_occurrence: list[str]) -> str:
    liste = "\n".join(f"{i}. {m}" for i, m in enumerate(messages_occurrence, start=1))
    return f"""Tu rédiges, pour diagBruit, la synthèse d'un ensemble de messages qui
décrivent tous la MÊME règle d'urbanisme liée au bruit — un opérateur humain
a déjà vérifié qu'ils se recouvrent (même secteur, même objectif). Combine-les
en un seul message cohérent, sans redite ni simple juxtaposition. Respecte le
ton de voix suivant :

{TON_DE_VOIX}

Messages à combiner :
{liste}

Rédige un message unique et cohérent (2 à 5 phrases), qui couvre l'ensemble
du contenu des messages ci-dessus sans ajouter d'information nouvelle."""


def _construire_prompt_titre(message_synthese: str) -> str:
    return f"""Tu rédiges, pour diagBruit, un titre court (quelques mots, pas une
phrase complète) qui résume le message ci-dessous — destiné à identifier ce
message dans une liste (titre d'une alerte, d'une fiche). Respecte le ton de
voix suivant :

{TON_DE_VOIX}

Message à résumer :
"{message_synthese}"

Rédige un titre de 3 à 8 mots, sans point final, sans guillemets, qui
identifie le sujet principal du message (ex. la nature de la règle et sa
localisation si elle y figure) sans en reprendre toutes les nuances."""


def _generer_titre(message_synthese: str) -> str:
    prompt = _construire_prompt_titre(message_synthese)
    try:
        response = _appeler_claude(prompt, SCHEMA_TITRE)
    except anthropic.APIError as exc:
        raise _ErreurRedaction(f"appel API échoué : {exc}") from exc
    return _extraire_champ(response, "titre_propose")


def _generer_message_occurrence(donnees_etape4: pd.Series, donnees_etape3: dict[str, str]) -> str:
    prompt = _construire_prompt_occurrence(donnees_etape4, donnees_etape3)
    try:
        response = _appeler_claude(prompt, SCHEMA_MESSAGE_OCCURRENCE)
    except anthropic.APIError as exc:
        raise _ErreurRedaction(f"appel API échoué : {exc}") from exc
    return _extraire_champ(response, "message_occurrence")


def _generer_message_synthese(messages_occurrence: list[str]) -> str:
    prompt = _construire_prompt_synthese(messages_occurrence)
    try:
        response = _appeler_claude(prompt, SCHEMA_MESSAGE_SYNTHESE)
    except anthropic.APIError as exc:
        raise _ErreurRedaction(f"appel API échoué : {exc}") from exc
    return _extraire_champ(response, "message_synthese")


@dataclass
class ResultatGroupe:
    id_geometrie_synthese: int
    geometry: object
    message_synthese: str
    titre_propose_llm: str
    lignes_documents: list[dict]


def _traiter_groupe_occurrence_locale(
    lignes_groupe: list[pd.Series],
    meneur: pd.Series,
    index_etape3: dict[tuple[str, str], dict[str, str]],
    erreurs: list[dict],
    lignes_occurrences: list[dict],
    date_traitement: str,
) -> ResultatGroupe | None:
    messages_occurrence: list[str] = []
    lignes_documents: list[dict] = []

    for ligne in lignes_groupe:
        cle = _cle(ligne)
        donnees_etape3 = index_etape3.get(cle)
        if donnees_etape3 is None:
            erreurs.append(
                {
                    "identifiant": ligne.get("id_occurrence", ""),
                    "source": "jointure_etape3",
                    "message": "occurrence introuvable dans etape3_{dept}.csv",
                    "date_traitement": date_traitement,
                }
            )
            continue

        try:
            message_occurrence = _generer_message_occurrence(ligne, donnees_etape3)
        except _ErreurRedaction as exc:
            erreurs.append(
                {
                    "identifiant": ligne.get("id_occurrence", ""),
                    "source": "generation_message_occurrence",
                    "message": str(exc),
                    "date_traitement": date_traitement,
                }
            )
            continue

        messages_occurrence.append(message_occurrence)
        lignes_occurrences.append(
            {
                "id_geometrie_synthese": meneur.get("id_geometrie", ""),
                "id_gpu": ligne.get("id_gpu", ""),
                "id_occurrence": ligne.get("id_occurrence", ""),
                "message_occurrence": message_occurrence,
                "occurrence_corrigee": "False",
                "message_occurrence_corrige": "",
                "validation_message_commentaire": "",
                "extrait_significatif": donnees_etape3.get("extrait_significatif", ""),
                "contexte_documentaire": donnees_etape3.get("contexte_documentaire", ""),
                "justification": ligne.get("justification", ""),
                "lien_web_document": ligne.get("lien_web_document", ""),
                "reference_precise": ligne.get("reference_precise", ""),
                "nature_sonore_zone": ligne.get("nature_sonore_zone", ""),
            }
        )
        lignes_documents.append(
            {
                "id_geometrie_synthese": meneur.get("id_geometrie", ""),
                "id_gpu": ligne.get("id_gpu", ""),
                "nature": ligne.get("type_piece_source", ""),
                "lien_web_document": ligne.get("lien_web_document", ""),
                "reference_precise": ligne.get("reference_precise", ""),
            }
        )

    if not messages_occurrence:
        # Tous les membres du groupe ont échoué (jointure ou génération) :
        # rien d'exploitable à synthétiser, le groupe entier est exclu de
        # cette exécution — déjà tracé individuellement dans `erreurs`.
        return None

    if len(messages_occurrence) == 1:
        message_synthese = messages_occurrence[0]
    else:
        try:
            message_synthese = _generer_message_synthese(messages_occurrence)
        except _ErreurRedaction as exc:
            erreurs.append(
                {
                    "identifiant": str(meneur.get("id_occurrence", "")),
                    "source": "generation_message_synthese",
                    "message": str(exc),
                    "date_traitement": date_traitement,
                }
            )
            return None

    # Un échec ici n'invalide pas le message déjà produit ci-dessus : tracé
    # dans `erreurs`, mais le groupe reste écrit avec un titre vide plutôt
    # qu'exclu (contrairement à un échec de message_synthese).
    try:
        titre_propose_llm = _generer_titre(message_synthese)
    except _ErreurRedaction as exc:
        erreurs.append(
            {
                "identifiant": str(meneur.get("id_occurrence", "")),
                "source": "generation_titre",
                "message": str(exc),
                "date_traitement": date_traitement,
            }
        )
        titre_propose_llm = ""

    return ResultatGroupe(
        id_geometrie_synthese=meneur.get("id_geometrie", ""),
        geometry=meneur.geometry,
        message_synthese=message_synthese,
        titre_propose_llm=titre_propose_llm,
        lignes_documents=lignes_documents,
    )


def preparer(code_departement: str, dossier_sortie: str | Path = "output") -> Path:
    dossier = Path(dossier_sortie)
    chemin_gpkg = dossier / f"etape4_{code_departement}.gpkg"
    chemin_etape3 = dossier / f"etape3_{code_departement}.csv"

    if not chemin_gpkg.exists():
        raise GpkgIntrouvable(str(chemin_gpkg))
    if not chemin_etape3.exists():
        raise Etape3CsvIntrouvable(str(chemin_etape3))

    gdf = gpd.read_file(chemin_gpkg, layer="geometries")
    index_etape3 = _lire_etape3(chemin_etape3)
    date_traitement = date.today().isoformat()

    erreurs: list[dict] = []
    lignes_occurrences: list[dict] = []
    lignes_documents: list[dict] = []
    resultats_synthese: list[dict] = []
    geometries_synthese: list = []

    # --- Cas fixes : rnu / document_non_significatif / trou_de_couverture ---
    masque_fixe = gdf["nature_zone"].apply(_texte).isin(MESSAGES_FIXES.keys())
    for _, ligne in gdf[masque_fixe].iterrows():
        resultats_synthese.append(
            {
                "id_geometrie": ligne.get("id_geometrie", ""),
                "id_gpu": ligne.get("id_gpu", ""),
                "id_occurrence": ligne.get("id_occurrence", ""),
                "message_synthese_llm": MESSAGES_FIXES[_texte(ligne.get("nature_zone"))],
                # Textes fixes : jamais soumis au circuit de correction (voir
                # etape-5-redaction-messages-diagbruit.md, "Messages fixes")
                # — outil_validation.html les exclut de son mode "fusion" en
                # filtrant sur id_occurrence non vide, ces colonnes restent
                # donc vides ici par construction, jamais lues.
                "synthese_corrigee": "False",
                "message_synthese_corrige": "",
                "titre_propose_llm": TITRES_FIXES[_texte(ligne.get("nature_zone"))],
                "titre_corrigee": "False",
                "titre_propose_corrige": "",
                "validation_message_commentaire": "",
            }
        )
        geometries_synthese.append(ligne.geometry)

    # --- Cas occurrence_locale : reconstruction des groupes fusionnés ---
    eligibles = gdf[gdf["nature_zone"].apply(_texte) == NATURE_ZONE_ELIGIBLE].copy()
    eligibles["_cle_groupe"] = eligibles.apply(_cle_groupe, axis=1)

    for cle_groupe, groupe in eligibles.groupby("_cle_groupe"):
        lignes_groupe = [ligne for _, ligne in groupe.iterrows()]
        meneurs = [ligne for ligne in lignes_groupe if _cle(ligne) == cle_groupe]
        if not meneurs:
            # Un membre référence un meneur absent du groupe reconstruit —
            # ne devrait pas arriver si etape4_{dept}.gpkg est cohérent
            # (voir synthese_geometries.py, _verifier_fusion, qui exige déjà
            # un meneur existant et géoréférencé). Tracé plutôt que supposé.
            for ligne in lignes_groupe:
                erreurs.append(
                    {
                        "identifiant": ligne.get("id_occurrence", ""),
                        "source": "reconstruction_groupe",
                        "message": "meneur du groupe introuvable dans etape4_{dept}.gpkg",
                        "date_traitement": date_traitement,
                    }
                )
            continue
        meneur = meneurs[0]

        resultat = _traiter_groupe_occurrence_locale(
            lignes_groupe, meneur, index_etape3, erreurs, lignes_occurrences, date_traitement
        )
        if resultat is None:
            continue

        resultats_synthese.append(
            {
                "id_geometrie": resultat.id_geometrie_synthese,
                "id_gpu": meneur.get("id_gpu", ""),
                "id_occurrence": meneur.get("id_occurrence", ""),
                "message_synthese_llm": resultat.message_synthese,
                "synthese_corrigee": "False",
                "message_synthese_corrige": "",
                "titre_propose_llm": resultat.titre_propose_llm,
                "titre_corrigee": "False",
                "titre_propose_corrige": "",
                "validation_message_commentaire": "",
            }
        )
        geometries_synthese.append(resultat.geometry)
        lignes_documents.extend(resultat.lignes_documents)

    # --- Écriture des sorties ---
    if resultats_synthese:
        geodf_synthese = gpd.GeoDataFrame(resultats_synthese, geometry=geometries_synthese, crs=gdf.crs)
    else:
        geodf_synthese = gpd.GeoDataFrame(
            columns=COLONNES_SYNTHESES, geometry=[], crs=gdf.crs
        )
    chemin_a_completer = dossier / f"etape5_{code_departement}_a_completer.gpkg"
    geodf_synthese.to_file(chemin_a_completer, layer="syntheses", driver="GPKG")

    # Miroir CSV de la table de synthèse (sans la géométrie), pour l'outil de
    # validation HTML de la Phase 3 (voir etape-5-conception-technique.md) :
    # un navigateur ne sait pas lire un GeoPackage (SQLite binaire) sans
    # bibliothèque supplémentaire, alors qu'un CSV se parse nativement en
    # JavaScript — même principe que l'outil de l'étape 3, aucune dépendance
    # externe.
    chemin_syntheses_csv = dossier / f"etape5_{code_departement}_syntheses.csv"
    with chemin_syntheses_csv.open("w", newline="", encoding="utf-8-sig") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=COLONNES_SYNTHESES)
        writer.writeheader()
        writer.writerows(
            {colonne: ligne.get(colonne, "") for colonne in COLONNES_SYNTHESES} for ligne in resultats_synthese
        )

    chemin_occurrences = dossier / f"etape5_{code_departement}_occurrences.csv"
    with chemin_occurrences.open("w", newline="", encoding="utf-8-sig") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=COLONNES_OCCURRENCES)
        writer.writeheader()
        writer.writerows(lignes_occurrences)

    chemin_documents = dossier / f"etape5_{code_departement}_documents_par_synthese.csv"
    with chemin_documents.open("w", newline="", encoding="utf-8-sig") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=COLONNES_DOCUMENTS)
        writer.writeheader()
        writer.writerows(lignes_documents)

    chemin_erreurs = dossier / f"etape5_{code_departement}_erreurs.csv"
    if erreurs:
        with chemin_erreurs.open("w", newline="", encoding="utf-8-sig") as fichier:
            writer = csv.DictWriter(fichier, fieldnames=COLONNES_ERREURS)
            writer.writeheader()
            writer.writerows(erreurs)
        print(f"{len(erreurs)} erreur(s) de génération, listée(s) dans {chemin_erreurs}.")
    elif chemin_erreurs.exists():
        chemin_erreurs.unlink()

    print(
        f"{len(resultats_synthese)} synthèse(s) écrite(s) dans {chemin_a_completer}, "
        f"{len(lignes_occurrences)} message(s) individuel(s) dans {chemin_occurrences}."
    )
    return chemin_a_completer


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Étape 5, Phase 2 — génère les messages (par occurrence et de synthèse) par LLM."
    )
    parser.add_argument(
        "--dept",
        required=True,
        help="Code département diagBruit (ex. 033, 971) — doit correspondre à un etape4_{dept}.gpkg existant.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Dossier de lecture/écriture des fichiers (défaut : output/).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    print(f"Étape 5, phase 2 — département {args.dept}")
    try:
        preparer(args.dept, dossier_sortie=args.output_dir)
    except GpkgIntrouvable as exc:
        print(f"Arrêt : etape4_{args.dept}.gpkg introuvable ({exc}).", file=sys.stderr)
        return 1
    except Etape3CsvIntrouvable as exc:
        print(f"Arrêt : etape3_{args.dept}.csv introuvable ({exc}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
