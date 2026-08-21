"""Étape 6 — aide partagée : assemblage déterministe du message Strapi.

Assemble `message_synthese` (rédigé et validé à l'étape 5) et la liste des
documents concernés (`etape5_{dept}_documents_par_synthese.csv`, filtrée sur
`id_geometrie_synthese == id_geometrie`) selon le formalisme défini le
20/08/2026 — voir `docs/etape-6-mise-en-forme-diagbruit.md`, "Assemblage du
message pour Strapi". Aucun appel LLM : pure mise en forme d'une donnée déjà
fiable, jamais régénérée.
"""

from __future__ import annotations

SEPARATEUR_LISTE = " / "


def assembler_message(message_synthese: str, documents: list[dict]) -> str:
    """`documents` : lignes de `etape5_{dept}_documents_par_synthese.csv`
    filtrées sur `id_geometrie_synthese == id_geometrie`, dans l'ordre où
    elles apparaissent dans le fichier — liste vide pour les cas `rnu`/
    `document_non_significatif`/`trou_de_couverture` (pas d'entrée dans ce
    fichier pour ces `id_geometrie`, voir `etape-6-conception-technique.md`,
    "Phase unique").
    """
    docs_sources = SEPARATEUR_LISTE.join(doc.get("nature", "") for doc in documents)
    references = SEPARATEUR_LISTE.join(doc.get("reference_precise", "") for doc in documents)

    return f"Message : {message_synthese}\nDocs sources : {docs_sources}\nréférences : {references}"
