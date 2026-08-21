# Étape 6 — Mise en forme pour ingestion

*Note de cadrage initiale, volontairement minimale — issue des échanges du 20/08/2026 lors de la conception de l'étape 5. Suite de `etape-5-redaction-messages-diagbruit.md` et `etape-5-conception-technique.md`. À développer plus en détail une fois l'étape 5 elle-même stabilisée en usage réel.*

**Rappel issu de l'étape 5** : l'assemblage du message final selon le formalisme attendu par diagBruit —

```
Message : {corps du message}
Docs sources : {liste, séparés par " / "}
références : {liste, séparés par " / ", même ordre que les documents}
```

— se fait ici, en Python, à partir de `message_synthese` (validé à l'étape 5) et de `etape5_{dept}_documents_par_synthese.csv` (donnée déjà fiable, jamais régénérée par un LLM — voir `etape-5-conception-technique.md`, "Documents concernés"). Pas de nouvel appel LLM pour cet assemblage : c'est un problème de mise en forme déterministe, pas de rédaction — délibérément gardé hors de l'étape 5 pour ne pas faire retranscrire par un LLM une donnée déjà connue avec certitude.

**Décision du 20/08/2026** : `documents_par_synthese.csv` n'a pas de colonne `nom_document` — le champ `nature` (`type_piece_source`, ex. "règlement écrit") identifie chaque entrée de la liste "Docs sources" à l'assemblage.

*Point noté pour mémoire : le plan global (`plan-automatisation-regles-plu-diagbruit.md`, étape 6) prévoyait initialement que cette étape porte aussi les "gabarits de message pour les documents non significatifs, les communes RNU et les trous de couverture" — ces trois textes fixes ont finalement été intégrés directement à l'étape 5 (voir `etape-5-redaction-messages-diagbruit.md`, "Messages fixes"), pas reportés ici.*

## Prochaine étape

Conception détaillée de l'étape 6, une fois l'étape 5 testée et stabilisée en usage réel.
