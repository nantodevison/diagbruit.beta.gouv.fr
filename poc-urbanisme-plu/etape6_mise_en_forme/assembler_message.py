"""Étape 6 — aide partagée : assemblage déterministe des champs Strapi/Notion.

À partir de `message_synthese` (rédigé et validé à l'étape 5) et de la liste
des documents concernés (`etape5_{dept}_documents_par_synthese.csv`, filtrée
sur `id_geometrie_synthese == id_geometrie`) : le bloc `message_strapi`
(formalisme défini le 20/08/2026, voir `docs/etape-6-mise-en-forme-diagbruit.md`,
"Assemblage du message pour Strapi"), et — depuis le 24/08/2026 — les mêmes
listes `source`/`reference` exposées séparément, pour correspondre aux
champs réels du content-type Strapi (`content`/`source`/`reference`, voir
`docs/etape-7-stockage-diagbruit.md`), distincts en pratique. Aucun appel
LLM : pure mise en forme d'une donnée déjà fiable, jamais régénérée.

================================================================================
DÉDUPLICATION — lire avant de toucher à ce fichier (décision du 24/08/2026,
confirmée après une hésitation le même jour, voir `etape-6-conception-technique.md`,
"Pourquoi la déduplication est correcte")
================================================================================

`assembler_source_reference` DÉDUPLIQUE les listes `nature`/`reference_precise`
avant de les joindre. Ce n'est PAS un oubli ni un raccourci risqué : c'est la
conséquence directe d'une décision humaine déjà prise et validée en amont, à
l'étape 5.

**Mise à jour du 24/08/2026** (voir `docs/etape-5-ameliorations-possibles.md`,
"Génération LLM d'un titre court") : `notion_description` n'est plus calculé
ici par déduplication de citations — le champ `Description` de Notion (comme
`title` de Strapi) est désormais alimenté par `titre_propose`, un titre court
généré par LLM à l'étape 5 et transmis tel quel par `generer_export.py`. Le
raisonnement ci-dessous reste valable pour `strapi_source`/`strapi_reference`.

Le raisonnement, en trois temps :

1. Un groupe fusionné (`fusionne_avec_id_gpu`/`fusionne_avec_id_occurrence`,
   voir `etape-4-conception-technique.md`, "Mécanisme de fusion") peut
   compter plusieurs occurrences distinctes — chacune avec son propre
   `extrait_significatif`, son propre `message_occurrence`, sa propre
   `reference_precise`. Ces occurrences NE SONT PAS des doublons entre
   elles : `etape5_{dept}_occurrences.csv` les garde donc toutes, une ligne
   chacune, sans jamais les fusionner ni les supprimer.
2. MAIS la fusion elle-même — le fait de regrouper ces occurrences en une
   seule géométrie de synthèse — est une décision **déjà validée par
   l'opérateur** (garde-fou `controle_similarite.py` en amont, fusion
   explicite à l'étape 4, relecture du `message_synthese` résultant dans
   `outil_validation.html` à l'étape 5). Une fois cette fusion validée, le
   groupe produit **un seul message cohérent** (`message_synthese`) : les N
   occurrences ne sont plus, du point de vue du lecteur final, N informations
   séparées, mais UNE seule règle déjà reformulée.
3. `strapi_source`/`strapi_reference` ne sont pas des
   journaux de traçabilité (ce rôle est déjà tenu par
   `etape5_{dept}_documents_par_synthese.csv`/`etape5_{dept}_occurrences.csv`,
   jamais dédupliqués, jamais touchés ici) — ce sont des **champs de
   synthèse pour le lecteur final** de Strapi/Notion, répondant à "quels
   documents/références soutiennent cette règle ?". Une fois la fusion
   validée, citer 4 fois "Article 4" dans ce champ n'apporte aucune
   information supplémentaire par rapport à le citer une fois : la
   granularité des 4 occurrences a déjà été absorbée dans un unique
   `message_synthese`, cohérent, à l'étape 5.

**Erreur à ne pas reproduire** : une première version (24/08/2026) avait
retiré cette déduplication, sur la base d'un raisonnement incomplet — "deux
valeurs identiques ne veulent pas dire deux occurrences identiques" (vrai,
vérifié sur `067-plui-strasbourg`, 4 occurrences réellement distinctes citant
"Article 4"). Ce raisonnement s'arrêtait avant l'étape 2 ci-dessus : le fait
que les occurrences soient distinctes n'implique pas qu'il faille les citer
séparément dans les champs de synthèse, précisément parce que la fusion
(déjà validée) les a déjà rendues indissociables aux yeux du lecteur final.
Ne pas dédupliquer produirait `"Article 4 / Article 4 / Article 4 / Article 4"`
dans le champ Strapi `reference` — un artefact de mise en forme, jamais
souhaité, jamais produit par une saisie manuelle (vérifié sur une capture
d'écran réelle).
"""

from __future__ import annotations

SEPARATEUR_LISTE = " / "


def dedupliquer_en_conservant_ordre(valeurs: list[str]) -> list[str]:
    """Retire les doublons exacts, garde la première occurrence de chacun et
    ignore les valeurs vides. Voir la section "DÉDUPLICATION" en tête de
    module pour pourquoi ce n'est pas un nettoyage de donnée, mais la
    conséquence directe de la fusion déjà validée à l'étape 5."""
    vues: set[str] = set()
    resultat = []
    for valeur in valeurs:
        if valeur and valeur not in vues:
            vues.add(valeur)
            resultat.append(valeur)
    return resultat


def assembler_source_reference(documents: list[dict]) -> tuple[str, str]:
    """Listes `nature` et `reference_precise`, dédupliquées et jointes par
    `" / "` — correspond aux champs Strapi `source`/`reference`. Voir la
    section "DÉDUPLICATION" en tête de module : la déduplication ici reflète
    la fusion déjà validée à l'étape 5, ce n'est pas une correction de
    données.

    `documents` : lignes de `etape5_{dept}_documents_par_synthese.csv`
    filtrées sur `id_geometrie_synthese == id_geometrie`, dans l'ordre où
    elles apparaissent dans le fichier — liste vide pour les cas `rnu`/
    `document_non_significatif`/`trou_de_couverture` (pas d'entrée dans ce
    fichier pour ces `id_geometrie`, voir `etape-6-conception-technique.md`,
    "Phase 1").
    """
    sources = dedupliquer_en_conservant_ordre([doc.get("nature", "") for doc in documents])
    references = dedupliquer_en_conservant_ordre([doc.get("reference_precise", "") for doc in documents])
    return SEPARATEUR_LISTE.join(sources), SEPARATEUR_LISTE.join(references)


def assembler_message(message_synthese: str, documents: list[dict]) -> str:
    """Bloc `message_strapi` complet (`Message : ... / Docs sources : ... /
    références : ...`), pour la saisie manuelle groupée. Voir
    `assembler_source_reference` pour les mêmes listes exposées séparément.
    """
    docs_sources, references = assembler_source_reference(documents)
    return f"Message : {message_synthese}\nDocs sources : {docs_sources}\nréférences : {references}"
