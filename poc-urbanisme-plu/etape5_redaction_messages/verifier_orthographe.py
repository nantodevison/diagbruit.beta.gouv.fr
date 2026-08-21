"""Étape 5 — vérification orthographique et grammaticale des messages
corrigés manuellement.

Lit `etape5_{dept}.gpkg` (couche `messages`, sortie de `synthese_messages.py`
— Phase 4) et ajoute une colonne `_validation_orthographe` : pour chaque
ligne où `synthese_corrigee` est vrai, le texte de `message_synthese_corrige`
est passé à Grammalecte (`pygrammalecte`), et les erreurs détectées
(orthographe, grammaire) sont concaténées dans cette colonne, séparées par
" | ". Vide si rien n'est détecté, ou si la ligne n'a pas été corrigée
manuellement — voir `docs/etape-5-conception-technique.md`, "Vérification
orthographique".

Décision (voir échanges du 21/08/2026) : seuls les messages *corrigés*
manuellement sont vérifiés, pas les messages natifs du LLM — le risque de
faute humaine à la frappe est le problème visé, pas la qualité rédactionnelle
du LLM. Jamais de correction automatique du texte : un signalement à trier,
comme le reste des garde-fous de ce pipeline (voir `controle_similarite.py`,
Phase 1).

Réécrit `etape5_{dept}.gpkg` en place (même fichier, même couche) : ce script
doit donc être relancé après toute nouvelle exécution de `synthese_messages.py`
(qui réécrit le gpkg en entier sans connaître cette colonne) — discipline
opérationnelle plutôt que verrou technique, même esprit que l'ordre des
phases déjà documenté ailleurs dans ce pipeline.

Usage :
    python -m etape5_redaction_messages.verifier_orthographe --dept 033

Entrée (dans `output/`, voir `--output-dir`) :
    etape5_{dept}.gpkg

Sortie : le même fichier, avec la colonne `_validation_orthographe` en plus.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pygrammalecte import GrammalecteGrammarMessage, grammalecte_text

COUCHE_MESSAGES = "messages"
# Même valeur que TYPE_GEOMETRIE_SORTIE de etape4_geometries/preparer_geometries.py
# et etape5_redaction_messages/preparer_messages.py — réimplémentée ici plutôt
# qu'importée, chaque étape (et chaque script au sein d'une étape) reste
# indépendante du code des autres (voir etape-1-conception-technique.md,
# "Décision 2").
TYPE_GEOMETRIE_SORTIE = "MultiPolygon"


class GpkgIntrouvable(Exception):
    pass


def _texte(valeur) -> str:
    """Même normalisation NaN-safe que le reste du pipeline — voir
    `etape4_geometries/synthese_geometries.py`, `_texte()`. Réimplémentée ici
    plutôt qu'importée : chaque étape reste indépendante du code des autres
    (voir `etape-1-conception-technique.md`, "Décision 2")."""
    if valeur is None:
        return ""
    if isinstance(valeur, float) and pd.isna(valeur):
        return ""
    return str(valeur).strip()


def _formater_message(msg, texte_source: str) -> str:
    extrait = texte_source[msg.start : msg.end]
    if isinstance(msg, GrammalecteGrammarMessage):
        base = f'[grammaire] "{extrait}" — {msg.message}'
        if msg.suggestions:
            base += f" (suggestion : {', '.join(msg.suggestions)})"
        return base
    return f'[orthographe] "{extrait}" — {msg.message}'


def _verifier_ligne(ligne: str, identifiant: str) -> list[str]:
    try:
        messages = list(grammalecte_text(ligne))
    except Exception as exc:  # Grammalecte est local/déterministe : un échec
        # ici serait inattendu, mais ne doit pas faire perdre la ligne pour
        # autant — signalé dans la colonne elle-même plutôt que silencieux.
        print(f"Attention : échec de la vérification pour {identifiant} sur la ligne {ligne[:60]!r} ({exc}).", file=sys.stderr)
        return ["[erreur de vérification orthographique sur une partie du message]"]
    return [_formater_message(m, ligne) for m in messages]


def _verifier_texte(texte_source: str, identifiant: str) -> str:
    if not texte_source:
        return ""
    # Découpage ligne par ligne avant l'appel à Grammalecte, plutôt qu'un
    # seul appel sur le texte entier — vérifié en réel le 21/08/2026 :
    # `grammalecte_text` échoue (JSONDecodeError interne à Grammalecte,
    # "Illegal trailing comma") sur environ 40 % des messages corrigés réels
    # de ce projet dès qu'ils contiennent plusieurs lignes (l'énumération à
    # tirets encouragée par `ton_de_voix.py` en écrit justement beaucoup),
    # alors qu'aucun échec ne se reproduit une fois le texte découpé par
    # ligne. Limite acceptée : un accord grammatical qui s'étendrait sur deux
    # lignes (sujet sur une ligne, verbe sur la suivante) ne serait pas
    # détecté — jugé marginal au vu du style de messages produits (phrases
    # courtes, énumérations, voir "Règles complémentaires" dans
    # ton_de_voix.py).
    resultats: list[str] = []
    for ligne in texte_source.split("\n"):
        if not ligne.strip():
            continue
        resultats.extend(_verifier_ligne(ligne, identifiant))
    return " | ".join(resultats)


def verifier(code_departement: str, dossier_sortie: str | Path = "output") -> Path:
    dossier = Path(dossier_sortie)
    chemin_gpkg = dossier / f"etape5_{code_departement}.gpkg"

    if not chemin_gpkg.exists():
        raise GpkgIntrouvable(str(chemin_gpkg))

    gdf = gpd.read_file(chemin_gpkg, layer=COUCHE_MESSAGES)

    validations: list[str] = []
    for _, ligne in gdf.iterrows():
        corrigee = _texte(ligne.get("synthese_corrigee")) in ("True", "true")
        texte_corrige = _texte(ligne.get("message_synthese_corrige"))
        if not corrigee or not texte_corrige:
            validations.append("")
            continue
        identifiant = str(ligne.get("id_geometrie", ""))
        validations.append(_verifier_texte(texte_corrige, identifiant))

    gdf["_validation_orthographe"] = validations

    gdf.to_file(
        chemin_gpkg,
        layer=COUCHE_MESSAGES,
        driver="GPKG",
        geometry_type=TYPE_GEOMETRIE_SORTIE,
        promote_to_multi=True,
    )

    nb_signalements = sum(1 for v in validations if v)
    print(
        f"{nb_signalements} message(s) corrigé(s) avec au moins un signalement, "
        f"sur {sum(1 for v in validations if v is not None)} ligne(s) au total — "
        f"colonne _validation_orthographe mise à jour dans {chemin_gpkg}."
    )
    return chemin_gpkg


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Étape 5 — vérifie l'orthographe/grammaire des messages corrigés manuellement."
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

    print(f"Étape 5 — vérification orthographique, département {args.dept}")
    try:
        verifier(args.dept, dossier_sortie=args.output_dir)
    except GpkgIntrouvable as exc:
        print(f"Arrêt : etape5_{args.dept}.gpkg introuvable ({exc}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
