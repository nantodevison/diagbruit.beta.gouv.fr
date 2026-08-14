"""Aide partagée par les deux phases de l'étape 3 (`preparer_revue.py` et
`synthese_finale.py`) : reconstituer, à partir d'`etape1_{dept}.csv`, le nom
du document et les communes couvertes pour chaque `id_gpu`.

Nécessaire car l'étape 2 ne porte que l'`id_gpu`, un identifiant opaque pour
un opérateur humain — le rattacher au nom du document et aux communes rend
la relecture manuelle exploitable sans devoir rouvrir `etape1_{dept}.csv` à
côté. Ne fait aucun appel réseau, comme le reste de l'étape 3.
"""

from __future__ import annotations

import csv
from pathlib import Path


def charger_contexte_documents(chemin_etape1: str | Path) -> dict[str, dict[str, str]]:
    """Retourne un dict `id_gpu -> {"nom_document": ..., "communes": ...}`,
    `communes` étant la liste triée des noms de commune couvertes par ce
    document, jointe par une virgule.

    Les lignes sans `id_gpu` (communes RNU confirmé ou en trou de
    couverture, voir `etape-1-identification-documents-urbanisme-diagbruit.md`)
    sont hors périmètre ici : elles n'atteignent jamais l'étape 2, donc
    jamais l'étape 3.
    """
    communes_par_document: dict[str, set[str]] = {}
    nom_document_par_id: dict[str, str] = {}

    with open(chemin_etape1, encoding="utf-8-sig", newline="") as fichier:
        for ligne in csv.DictReader(fichier):
            id_gpu = ligne.get("id_gpu", "")
            if not id_gpu:
                continue
            communes_par_document.setdefault(id_gpu, set()).add(ligne["nom_commune"])
            nom_document_par_id.setdefault(id_gpu, ligne["nom_document"])

    return {
        id_gpu: {
            "nom_document": nom_document_par_id[id_gpu],
            "communes": ", ".join(sorted(communes)),
        }
        for id_gpu, communes in communes_par_document.items()
    }
