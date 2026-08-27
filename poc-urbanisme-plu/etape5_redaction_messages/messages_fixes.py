"""Étape 5 — aide partagée : messages fixes pour les occurrences qui ne
portent pas de citation d'un document à reformuler (`rnu`,
`document_non_significatif`, `trou_de_couverture`, `document_non_exploitable`).

Textes validés le 19/08/2026 (voir `docs/etape-5-redaction-messages-diagbruit.md`,
"Messages fixes") — définitifs, ne passent jamais par la génération LLM ni
par le circuit de validation humaine propre aux messages générés.

`TITRES_FIXES` : même principe que pour le message — un titre
fixe écrit une fois pour chacun de ces cas, jamais régénéré ni soumis à
correction.

`document_non_exploitable` (ajouté le 26/08/2026, voir
`etape3_validation_manuelle/synthese_finale.py`) : distinct de
`document_non_significatif` — ici le document n'a jamais pu être lu (aucune
pièce écrite exploitable résolue en étape 2), alors que
`document_non_significatif` signifie qu'il a bien été lu mais ne mentionne
rien sur le bruit. Le texte ne doit donc pas affirmer l'absence de
prescription, seulement l'impossibilité de l'établir automatiquement.
"""

MESSAGES_FIXES: dict[str, str] = {
    "trou_de_couverture": (
        "Aucun document d'urbanisme n'est référencé dans le Géoportail de "
        "l'urbanisme pour cette commune. diagBruit ne peut pas déterminer si "
        "cette absence provient du Géoportail ou de la commune elle-même. "
        "Visitez le site de celle-ci pour plus de détails."
    ),
    "rnu": (
        "La commune ne dispose pas de document d'urbanisme propre à son "
        "territoire. Le Règlement National de l'Urbanisme s'applique, "
        "notamment son article R.111-2, qui stipule qu'un « projet peut être "
        "refusé ou n'être accepté que sous réserve (…) s'il est de nature à "
        "porter atteinte à la salubrité ou à la sécurité publique (…) ». Si "
        "votre projet présente un risque sonore fort ou extrême, "
        "rapprochez-vous de l'autorité compétente."
    ),
    "document_non_significatif": (
        "Les documents d'urbanisme présents sur le territoire ne mentionnent "
        "pas de recommandations ou de prescriptions particulières relatives "
        "au bruit. Seul le plan d'exposition au bruit limite la "
        "constructibilité, et seul le classement sonore protège les "
        "habitants. Toutefois, l'autorité compétente en matière de permis de "
        "construire peut toujours s'appuyer sur l'article R.111-2 du code de "
        "l'urbanisme, qui stipule qu'un « projet peut être refusé ou n'être "
        "accepté que sous réserve (…) s'il est de nature à porter atteinte à "
        "la salubrité ou à la sécurité publique (…) ». Si votre projet "
        "présente un risque sonore fort ou extrême, rapprochez-vous de "
        "l'autorité compétente."
    ),
    "document_non_exploitable": (
        "Le document disponible sur le Géoportail de l'Urbanisme (GPU) n'a "
        "pu être analysé automatiquement. Il peut s'agir de document "
        "graphique uniquement par exemple. Rendez-vous sur le GPU pour le "
        "consulter."
    ),
}

TITRES_FIXES: dict[str, str] = {
    "trou_de_couverture": "Absence de document d'urbanisme référencé",
    "rnu": "Règlement National de l'Urbanisme applicable",
    "document_non_significatif": "Aucune prescription bruit spécifique",
    "document_non_exploitable": "Document non analysable automatiquement",
}
