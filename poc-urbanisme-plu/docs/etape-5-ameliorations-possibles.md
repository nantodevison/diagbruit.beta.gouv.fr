# Étape 5 — Améliorations possibles (non mises en œuvre)

*Document de suivi, distinct des documents de cadrage (`etape-5-redaction-messages-diagbruit.md`, `etape-5-conception-technique.md`) : il liste des limites identifiées en utilisant réellement le pipeline, pour lesquelles une correction a été envisagée puis délibérément reportée. Chaque entrée date la décision et le contexte, pour que la même discussion n'ait pas à être refaite de zéro plus tard — dans le même esprit que `etape-2-ameliorations-possibles.md`, `etape-3-ameliorations-possibles.md` et `etape-4-ameliorations-possibles.md`.*

## Pas de mise en forme (gras, listes) capturée lors de la correction manuelle des messages — complique la conversion HTML en aval

**Identifié le 24/08/2026**, en préparant l'étape 7 (voir `etape-7-stockage-diagbruit.md`) : le champ `content` du content-type Strapi (`cms/src/api/noisezone-alert/content-types/noisezone-alert/schema.json`) attend du HTML riche (éditeur CKEditor). Une capture d'écran d'une saisie manuelle réelle montre que l'opérateur met en gras les citations réglementaires exactes dans `content`. Rien dans `message_synthese`/`message_synthese_corrige` (étape 5, texte brut) ne capture cette intention de mise en forme.

**Contexte** : `outil_validation.html` (étape 5, Phase 3) permet de corriger `message_synthese`/`message_occurrence` dans un simple `<textarea>` — texte brut, sans aucune option de mise en forme. Le message final (`message_synthese`, résolu en Phase 4) reste donc toujours du texte brut : au mieux des retours à la ligne (`\n`) et des puces en tirets ("- ...", recommandées par `ton_de_voix.py`, "Phrases courtes, énumérations privilégiées") — mais rien qui distingue explicitement "ceci doit apparaître en gras" d'un texte normal, ni "nouveau paragraphe" d'une simple puce de la même liste.

**Problème** : à l'étape 7, convertir ce texte brut en HTML pour `content` (Strapi) ne peut se faire que par une heuristique mécanique (ex. un `<p>` par ligne, ou un `<br>` par retour à la ligne — voir `etape-7-stockage-diagbruit.md`) — qui ne peut pas reproduire une mise en forme que l'opérateur aurait appliquée à la main (gras, vraie liste `<ul>/<li>`). Le texte source, à l'étape 5, ne porte tout simplement pas cette information : elle ne peut pas être reconstituée automatiquement en aval, quelle que soit l'heuristique choisie à l'étape 7.

**Pistes de correction envisageables, non retenues pour l'instant** :
- Ajouter un bandeau de mise en forme minimal (gras, liste à puces) au-dessus du champ de correction (`message_synthese_corrige`) dans `outil_validation.html`, Phase 3 de l'étape 5 — l'opérateur appliquerait directement la mise en forme au moment de la relecture, avec une sortie qui la porte (HTML minimal stocké dans `message_synthese_corrige`, ou une syntaxe légère type Markdown `**gras**`/`- puce` à interpréter ensuite à l'étape 7). Réglerait le problème à la source plutôt que de tenter de le deviner en aval.
- Implique de revoir le contrat de données de l'étape 5 (`message_synthese`/`message_synthese_corrige` ne seraient alors plus strictement du texte brut) et son impact sur les usages actuels en aval — l'étape 6 assemble aussi `message_strapi` en texte brut (voir `etape-6-mise-en-forme-diagbruit.md`) — pas un changement anodin.
- Alternative plus légère : n'introduire qu'une convention Markdown minimale (`**...**` pour le gras, `- ` déjà utilisé pour les puces), sans changer `outil_validation.html` lui-même, la conversion HTML de l'étape 7 sachant alors interpréter ces marqueurs. Reste à vérifier si les opérateurs l'adopteraient spontanément sans un bandeau qui la facilite — sinon la convention resterait lettre morte.

**Décision** : non mis en œuvre pour l'instant (24/08/2026) — l'étape 7 se contente dans un premier temps d'une conversion mécanique simple, sans mise en forme (voir `etape-7-stockage-diagbruit.md`). À reprendre si l'écart de qualité entre la saisie manuelle et l'automatisation s'avère gênant à l'usage.

## Génération LLM d'un titre court à l'étape 5 — nécessaire pour `title` (Strapi) et à réutiliser pour `Description` (Notion)

**Implémenté le 24/08/2026**, dans la même session Claude Code dédiée annoncée ci-dessous. Décisions prises pour lever les points ouverts (section "Points à trancher" plus bas, conservée pour mémoire) :
1. **Génération** : appel LLM dédié et uniforme (`_generer_titre`, dans `preparer_messages.py`), un par géométrie finale, plutôt que fusionné avec l'appel de synthèse.
2. **Source** : toujours le `message_synthese` natif (jamais la version corrigée en Phase 3) — cohérent avec "Correction humaine : natif + correction, jamais de cascade".
3. **Correction humaine** : oui, même mécanisme que `message_synthese` (natif immuable + case à cocher + reformulation), ajouté à `outil_validation.html`.
4. **Cas fixes** : un titre fixe par cas (`TITRES_FIXES`, dans `messages_fixes.py`), jamais régénéré ni corrigible — même traitement que leur message fixe.
5. **067-plui-strasbourg** (déjà poussé sur Strapi/Notion) : laissé tel quel, non régénéré — le nouveau titre ne s'applique qu'aux prochains départements.
6. **`notion_description`** : abandonné, remplacé par `titre_propose` (nouvelle colonne à l'étape 6), réutilisé pour `title` (Strapi) et `Description` (Notion) — voir `docs/etape-6-conception-technique.md` et `docs/etape-7-stockage-diagbruit.md` pour le détail.

*Section originale, sanctuarisée le 24/08/2026, à la demande de l'opérateur, pour être reprise dans une session Claude Code dédiée — conservée ci-dessous pour mémoire, rédigée pour être autoportante.*

### Contexte (état actuel du pipeline, sans cette amélioration)

Le pipeline est décrit en détail dans `docs/plan-automatisation-regles-plu-diagbruit.md` (vue d'ensemble) et les documents `docs/etape-{1..7}-*.md` (un cadrage + une conception technique par étape). Rappel du morceau concerné :

- **Étape 5** (`etape5_redaction_messages/preparer_messages.py`) génère, par appel LLM, `message_occurrence` (un message par occurrence) puis `message_synthese` (un message par géométrie finale, combinant les `message_occurrence` d'un groupe fusionné — voir `docs/etape-5-conception-technique.md`, Phase 2). **Aucun titre court n'est généré nulle part dans le pipeline actuel.**
- **Étape 6** (`etape6_mise_en_forme/generer_export.py`) calcule aujourd'hui la colonne `notion_description` de `etape6_{dept}_export.csv` à partir des citations `extrait_significatif` de l'étape 3 (relu depuis `etape5_{dept}_occurrences.csv`), dédupliquées et jointes par `" / "` — voir `docs/etape-6-conception-technique.md`, "Pourquoi la déduplication est correcte", et `docs/etape-7-stockage-diagbruit.md`, "Colonne Description" (décidé le 23-24/08/2026). **Ce n'est pas un titre court, ce sont des citations réglementaires brutes, potentiellement longues.**
- **Étape 7** (`etape7_stockage/client_strapi.py`) laisse le champ `title` de Strapi **vide** à la création (`_payload()` ne le renseigne jamais) — voir `docs/etape-7-conception-technique.md`, section sur le schéma Strapi. L'opérateur le complète manuellement en relisant le brouillon dans Strapi avant publication (`draftAndPublish` actif sur le content-type `noisezone-alert`, voir `cms/src/api/noisezone-alert/content-types/noisezone-alert/schema.json`).
- Une capture d'écran d'une saisie manuelle réelle (24/08/2026) confirme que `title` est en pratique toujours rempli par l'opérateur, avec une phrase courte (ex. "Autoriser les murs au lieu des clôtures sur la Métropole Européenne de Lille") — voir aussi `docs/etape-7-stockage-diagbruit.md`, "Schéma Strapi".

### Problème

Deux champs distincts, dans deux systèmes différents, n'ont aujourd'hui aucune source fiable et automatisée :
1. `title` (Strapi) — laissé vide, saisie manuelle requise avant chaque publication.
2. `Description` (Notion) — rempli automatiquement, mais avec des citations réglementaires brutes plutôt qu'un résumé court et lisible (la base Notion documente ce champ comme "résumé libre, à usage interne Notion, distinct du message final" — voir `docs/etape-6-mise-en-forme-diagbruit.md`, "Structure réelle de la base Notion").

### Piste retenue à explorer

Faire générer par le LLM, à l'étape 5, **un titre court (quelques mots)** — un troisième texte généré en plus de `message_occurrence` et `message_synthese`, au même niveau de granularité que `message_synthese` (un titre par géométrie finale, pas par occurrence). Ce même titre serait ensuite :
- transmis par l'étape 6 dans une nouvelle colonne de `etape6_{dept}_export.csv` (ex. `titre_propose`) ;
- utilisé par l'étape 7 pour remplir `title` (Strapi) **et** `Description` (Notion) — à la place du calcul actuel par citations, qui serait alors abandonné pour ce champ.

### Points à trancher dans la session dédiée (non résolus ici)

1. **Génération** : nouvel appel LLM séparé, ou même appel structuré que celui produisant déjà `message_synthese` (moins coûteux, un seul appel) ? Voir `etape5_redaction_messages/preparer_messages.py`, `_generer_message_synthese`, pour le mécanisme actuel de sortie structurée (`output_config.format`, SDK Anthropic).
2. **À partir de quel texte** : le titre doit-il être généré à partir de `message_synthese_llm` (natif) ou de la version finale résolue après correction humaine (`message_synthese`, potentiellement corrigée en Phase 3) ? Impact sur le principe "pas de cascade" déjà en place pour les corrections (voir `docs/etape-5-conception-technique.md`, "Correction humaine : natif + correction, jamais de cascade") — un titre généré depuis le texte natif ne se mettrait pas à jour si l'opérateur corrige `message_synthese` ensuite.
3. **Correction humaine** : ce nouveau titre a-t-il besoin du même mécanisme que `message_occurrence`/`message_synthese` (natif immuable + case à cocher + champ corrigé, affiché dans `outil_validation.html`) ? Cohérence avec le reste de l'étape 5 à préserver si oui.
4. **Cas fixes** (`rnu`/`document_non_significatif`/`trou_de_couverture`, voir `etape5_redaction_messages/messages_fixes.py`) : ces trois cas ont un message fixe, jamais généré par LLM — leur faut-il aussi un titre fixe, ou restent-ils sans titre (comme `notion_description` reste vide pour eux aujourd'hui) ?
5. **Longueur/style** : contrainte à donner au prompt pour rester dans "quelques mots" — cohérence à vérifier avec `etape5_redaction_messages/ton_de_voix.py` (texte des 5 piliers déjà joint aux prompts).
6. **Remplacement ou coexistence** : ce nouveau titre remplace-t-il entièrement `notion_description` (calculé aujourd'hui à partir des citations), ou les deux doivent-ils coexister d'une façon ou d'une autre ? La base Notion n'a qu'une seule propriété `Description` (voir `docs/etape-6-mise-en-forme-diagbruit.md`) — priori : remplacement complet, à confirmer.
7. **Départements déjà traités** : `067-plui-strasbourg` a déjà été intégralement poussé sur Strapi/Notion (voir `docs/etape-7-conception-technique.md`, "Implémenté le 24/08/2026") sans ce titre — faut-il régénérer l'étape 5 pour ce département (coût : nouveaux appels LLM, nouvelle relecture Phase 3) ou seulement l'appliquer aux prochains départements ?

### Fichiers à modifier (recensement, pas un plan figé)

- `etape5_redaction_messages/preparer_messages.py` (génération), potentiellement `etape5_redaction_messages/synthese_messages.py` (résolution finale du titre, Phase 4) et `etape5_redaction_messages/outil_validation.html` (relecture, si point 3 ci-dessus retenu) ;
- `etape6_mise_en_forme/generer_export.py` (nouvelle colonne, remplacement de `notion_description`) ;
- `etape7_stockage/client_strapi.py` (`_payload()`, ajouter `title`) — la doc `docs/etape-7-conception-technique.md` note explicitement, dans la description du champ `title`, que son absence est liée à cette limite : à mettre à jour une fois résolue.

**Décision** : mise en œuvre le 24/08/2026 — voir le résumé des décisions en tête de section, ci-dessus.
