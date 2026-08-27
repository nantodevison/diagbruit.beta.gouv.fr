# Étape 5 — Rédaction des messages associés aux géométries

*Document de cadrage détaillé de l'étape 5 du plan d'automatisation des règles PLU de diagBruit (voir `plan-automatisation-regles-plu-diagbruit.md`). Suite de `etape-4-construction-geometries-diagbruit.md` et `etape-4-conception-technique.md`.*

**Entrée** : `etape4_{dept}.gpkg` (couche unique `geometries`, une ligne par occurrence — voir `etape-4-conception-technique.md`, "Contrat de données"), complété par une jointure vers `etape3_{dept}.csv` sur le couple `id_gpu` + `id_occurrence`, pour retrouver le contenu textuel qui n'est pas dupliqué dans le gpkg (`extrait_significatif`, `contexte_documentaire`, `nature_occurrence`). Cette jointure ne concerne que les occurrences `nature_zone == "occurrence_locale"` : les quatre autres cas (`rnu`, `document_non_significatif`, `document_non_exploitable`, `trou_de_couverture`) n'ont pas d'`id_occurrence` et utilisent des messages fixes, voir plus bas.

## Principe

Deux objectifs indépendants, dans l'ordre où ils s'exécutent :

1. **Un garde-fou de cohérence géométrique**, en tout début d'étape : un contrôle a posteriori des décisions de fusion prises à l'étape 4, pour repérer les occurrences qui *auraient dû* être fusionnées mais ne le sont pas — jamais bloquant, à charge de l'opérateur d'en tenir compte ou de l'ignorer.
2. **La rédaction d'un message par géométrie finale**, à l'intention de l'utilisateur de diagBruit, respectant le ton de voix défini par le design de diagBruit (voir "Ton de voix" plus bas) — générée par LLM pour les occurrences réelles, fixe pour les quatre cas qui n'en portent pas. Un titre court est associé à chaque message, destiné à `title` (Strapi) et `Description` (Notion) — même distinction généré/fixe que pour le message lui-même.

## Garde-fou de cohérence géométrique

Un contrôle vérifie, avant de rédiger quoi que ce soit, que le travail de fusion de l'étape 4 (voir `etape-4-conception-technique.md`, "Mécanisme de fusion") n'a pas laissé passer une paire d'occurrences qui décrivent en réalité la même règle sans avoir été reliées par `fusionne_avec_*`.

Deux occurrences sont candidates à un tel signalement si leurs géométries sont à la fois :
- **d'aire équivalente** — moins de 10 % de variation entre les deux aires ;
- **de forme similaire** — comparaison géométrique automatique des deux contours (voir `etape-5-conception-technique.md`, "Phase 1", pour le détail du calcul), avec un seuil de 10 % également. Les deux seuils sont provisoires : jamais validés sur des données réelles, à ajuster une fois ce contrôle utilisé en pratique sur davantage de départements.

Ce contrôle ne porte que sur les paires déjà éligibles à une fusion selon les critères de l'étape 4 (`nature_zone == "occurrence_locale"`, même `nature_sonore_zone`) et exclut les paires déjà reliées par `fusionne_avec_id_gpu`/`fusionne_avec_id_occurrence` — l'objectif est de repérer les fusions *manquées*, pas de redire ce qui est déjà résolu. Le résultat est une liste d'avertissements, jamais une transformation automatique des données ni un blocage du reste du traitement — dans le même esprit que le reste du pipeline, mais avec un vocabulaire différent (avertissement, pas erreur) pour marquer que rien n'est objectivement invalide ici.

## Rédaction du message

Le contenu et la forme du message dépendent de `nature_zone`, repris de l'étape 4.

### `rnu`, `document_non_significatif`, `document_non_exploitable`, `trou_de_couverture` — messages fixes

Ces quatre cas ne portent pas de citation d'un document à reformuler : le message est un texte fixe, indépendant de toute génération :

**`trou_de_couverture`** :
> Aucun document d'urbanisme n'est référencé dans le Géoportail de l'urbanisme pour cette commune. diagBruit ne peut pas déterminer si cette absence provient du Géoportail ou de la commune elle-même. Visitez le site de celle-ci pour plus de détails.

**`rnu`** :
> La commune ne dispose pas de document d'urbanisme propre à son territoire. Le Règlement National de l'Urbanisme s'applique, notamment son article R.111-2, qui stipule qu'un « projet peut être refusé ou n'être accepté que sous réserve (…) s'il est de nature à porter atteinte à la salubrité ou à la sécurité publique (…) ». Si votre projet présente un risque sonore fort ou extrême, rapprochez-vous de l'autorité compétente.

**`document_non_significatif`** :
> Les documents d'urbanisme présents sur le territoire ne mentionnent pas de recommandations ou de prescriptions particulières relatives au bruit. Seul le plan d'exposition au bruit limite la constructibilité, et seul le classement sonore protège les habitants. Toutefois, l'autorité compétente en matière de permis de construire peut toujours s'appuyer sur l'article R.111-2 du code de l'urbanisme, qui stipule qu'un « projet peut être refusé ou n'être accepté que sous réserve (…) s'il est de nature à porter atteinte à la salubrité ou à la sécurité publique (…) ». Si votre projet présente un risque sonore fort ou extrême, rapprochez-vous de l'autorité compétente.

**`document_non_exploitable`** (ajouté le 26/08/2026) :
> Le document disponible sur le Géoportail de l'Urbanisme (GPU) n'a pu être analysé automatiquement. Il peut s'agir de document graphique uniquement par exemple. Rendez-vous sur le GPU pour le consulter.

Distinct de `document_non_significatif` : le message ne doit pas affirmer une absence de prescription (on ne le sait pas, faute d'avoir pu lire le document), seulement l'impossibilité de l'établir automatiquement — voir `etape-3-validation-manuelle.md`, "Document non exploitable : réintégration dans le pipeline", pour l'origine de ce cas.

Ces quatre textes sont considérés définitifs : ils ne passent pas par le circuit de validation humaine décrit plus bas, propre aux messages générés.

**Titres fixes** : ces quatre cas ont de même un titre court fixe (`TITRES_FIXES` dans `messages_fixes.py`), jamais soumis au circuit de correction — même principe que leur message.

### `occurrence_locale` — message généré

Contenu attendu, par géométrie finale :
- les **recommandations** que le ou les documents concernés proposent (`nature_occurrence == "recommandation"`) ;
- les **prescriptions** qu'ils imposent (`nature_occurrence == "prescription"`) ;
- pour **chaque document d'urbanisme concerné** par la géométrie : sa nature (`type_piece_source`), un lien web vers le GPU (`lien_web_document`), et la référence précise vers la partie de document utilisée (`reference_precise`).

**Cas des groupes fusionnés** : une géométrie finale peut regrouper plusieurs occurrences reliées par `fusionne_avec_*` (voir `etape-4-conception-technique.md`, "Mécanisme de fusion"). Le mécanisme de fusion ne vérifie jamais l'égalité d'`id_gpu` entre meneur et membres — un groupe peut donc légitimement mélanger plusieurs documents distincts. Le message doit refléter tous les documents concernés par le groupe, pas seulement celui du meneur.

### Ton de voix

Toute rédaction (occurrence isolée ou synthèse de groupe) doit respecter les 5 piliers du ton de voix définis par le design de diagBruit, reproduits ici intégralement — texte source du design, à joindre tel quel au prompt du LLM (voir "Génération par LLM" ci-dessous) plutôt qu'à reformuler : les exemples associés à chaque pilier sont le matériau de calibration du ton, pas un habillage à résumer.

#### 1️⃣ Informatif et institutionnel

Vous êtes la voix de référence du service public.

- Vous citez les textes de référence de manière synthétique et sourcée
- Vous restez factuel sans recopier intégralement les articles de loi
- Vous renvoyez vers les textes officiels pour approfondir

**Exemple :** "L'arrêté du 1er octobre 2025 fixe les seuils d'exposition au bruit à 60 dB en zone modérée. **Consultez** le texte complet sur Légifrance."

#### 2️⃣ Préventif et sécuritaire

Vous protégez la santé des résidents et alertez sur les risques réels.

- Vous alertez sur les risques sanitaires sans dramatiser
- Vous proposez des solutions techniques concrètes à chaque problématique
- Vous guidez systématiquement vers des professionnels qualifiés
- Vous associez chaque préconisation à un bénéfice clair

**Exemple :** "L'exposition prolongée à plus de 65 dB présente des risques pour la santé. **Installez** un double vitrage acoustique sur la façade sud **pour améliorer votre confort de nuit et protéger vos résidents**. **Consultez** un acousticien certifié avant les travaux."

#### 3️⃣ Pédagogique et vulgarisateur

Vous rendez accessible la complexité technique.

- Vous employez un vocabulaire courant avec des exemples concrets
- Vous expliquez les termes techniques via un glossaire et des schémas illustrés
- Vous traduisez le technique en compréhensible sans condescendre
- Vous intégrez des encadrés « **À retenir** » en fin de section pour alléger la charge mentale

**Exemple :**
"Le **bruit aérien** désigne les nuisances sonores provenant des avions. Pour votre projet en zone d'exposition modérée, cela implique une isolation renforcée des toitures et des façades orientées vers l'aéroport.

Un **isolement acoustique** mesure la capacité d'une paroi à bloquer le bruit. Plus l'isolement est élevé, moins vous entendez les nuisances extérieures.

> À retenir :
>
> - Zone d'exposition : **modérée** (55-60 dB)
> - Isolement requis : 40 dB minimum
> - Action : **consulter** un acousticien avant le dépôt de permis"

#### 4️⃣ Direct et actionnable

Vous guidez vers l'action avec clarté et efficacité.

- Vous privilégiez les verbes d'action à l'impératif
- Vous éliminez le superflu et les tournures passives
- Vous dites une fois, mais bien
- Vous structurez l'information en sections courtes et hiérarchisées

**Exemple :** "**Vérifiez** l'isolation de la façade ouest **pour réduire le bruit de trafic routier de 30 dB**" plutôt que "Il serait recommandé de procéder à une vérification de l'isolation..."

#### 5️⃣ Collectif et altruiste

Vous portez une mission d'intérêt général.

- Vous rappelez que la gestion du bruit est un enjeu partagé par tous les acteurs
- Vous valorisez les démarches exemplaires et les bonnes pratiques déjà mises en œuvre
- Vous inscrivez chaque action individuelle dans une dynamique collective
- Vous reconnaissez la charge mentale des utilisateurs

**Exemple :** "En isolant votre bâtiment, vous protégez vos 45 futurs résidents **et contribuez** à réduire l'exposition sonore du quartier. Plus de 200 projets similaires ont déjà été réalisés dans votre commune, réduisant de 40% les plaintes liées au bruit."

**Note d'application** : ces exemples illustrent un contexte de recommandation technique (isolation, acousticien) qui ne correspond pas toujours à ce que porte réellement une occurrence PLU (souvent plus proche d'une contrainte d'urbanisme — implantation, hauteur, orientation — que d'une prescription technique de construction). Le ton (les 5 piliers) s'applique tel quel ; le contenu des exemples est illustratif, pas à reproduire littéralement quand il ne correspond pas à la nature de la règle réelle.

**Règles complémentaires propres aux occurrences PLU** (distinctes des 5 piliers ci-dessus, qui restent la consigne d'origine du design — ces règles répondent à des besoins spécifiques constatés à l'usage sur des occurrences PLU réelles) :

- Fidélité stricte au texte réglementaire : le résumé ne doit jamais déformer le texte source. Reste synthétique, clair, sans terme trop technique, mais en respectant strictement le sens des passages de la réglementation concernée — jamais une reformulation qui édulcore, généralise ou durcit une prescription ou une recommandation au-delà de ce que dit réellement le texte source.
- Phrases courtes, énumérations privilégiées : évite les phrases longues ou à subordonnées multiples. Préfère des phrases courtes et, quand plusieurs éléments doivent être listés, une énumération plutôt qu'une phrase qui les enchaîne.
- Localisation oui, nature du document non : décris la localisation de la règle (secteur, zone réglementaire mentionnée) quand elle est disponible, mais ne mentionne jamais la nature du document source (OAP, PLU, PLUi, PSMV, règlement écrit, PADD...) — déjà donnée séparément à l'utilisateur (voir "Docs sources" dans `etape-6-mise-en-forme-diagbruit.md`), pas la peine de la répéter dans le message.
  - *À éviter* : "Cette parcelle se situe dans le secteur OAP « à l'Ouest de la rue des Floralies » à Mundolsheim, exposé aux nuisances sonores de la voie ferrée. Pour limiter ces impacts, l'OAP recommande d'agir sur plusieurs leviers : le maillage des voies, les ouvertures et fermetures visuelles, l'implantation et la hauteur du bâti. L'isolation phonique des constructions peut également contribuer à répondre à cet enjeu. Anticipez ces choix d'aménagement dès la conception de votre projet, pour le confort de vos futurs résidents."
  - *À suivre* : "Pour limiter les nuisances sonores de la voie ferrée dans le secteur « à l'Ouest de la rue des Floralies », il est recommandé d'agir sur : le maillage des voies, les ouvertures et fermetures visuelles, l'implantation du bâti, la hauteur du bâti. Anticipez ces choix d'aménagement dès la conception de votre projet, pour le confort des futurs résidents."
- Pas de périmètre administratif non garanti (précision apportée sur la règle précédente) : n'affirme jamais un périmètre administratif précis (nom de commune, limite communale) qui ne serait pas explicitement confirmé par la citation source — un document intercommunal (PLUi) peut porter sur un périmètre plus large que la seule commune de la parcelle consultée. Reste sur une formulation générale de la localisation (secteur, zone réglementaire) plutôt que d'assumer une limite communale non garantie par le texte. C'est pour cette raison que l'exemple "à suivre" ci-dessus ne mentionne pas la commune de Mundolsheim, contrairement à l'exemple "à éviter".

### Génération par LLM

Le projet dispose déjà d'une dépendance `anthropic`, utilisée à l'étape 2 pour un usage comparable (analyse par prompt). L'étape 5 suit le même principe plutôt que d'introduire un moteur de génération de texte différent.

Trois textes distincts sont demandés au LLM, par géométrie finale :
- un **message par occurrence** — un texte par occurrence individuelle, jamais montré à l'utilisateur final de diagBruit, purement interne ;
- un **message de synthèse** — pour un groupe fusionné, une reformulation unique qui combine les occurrences du groupe en un seul message cohérent (pas une simple concaténation des messages individuels — le pilier "vous dites une fois, mais bien" l'exclut). Pour une occurrence non fusionnée (groupe d'une seule occurrence), le message individuel tient lieu de message final — pas de génération de synthèse redondante dans ce cas ;
- un **titre court** — quelques mots, généré à partir du message de synthèse une fois celui-ci obtenu, destiné à `title` (Strapi) et `Description` (Notion). Pour les quatre cas à message fixe, un titre fixe est utilisé à la place (voir "Messages fixes" ci-dessus), sur le même principe que leur message.

C'est le message de synthèse (ou le message individuel pour une occurrence isolée) qui constitue le livrable final de cette étape, après validation humaine.

## Validation humaine

Le risque propre à cette étape — contrairement aux précédentes, qui extraient ou classifient du contenu existant — est celui d'une affirmation générée qui ne correspondrait pas fidèlement à la règle source. La validation humaine systématique décrite ci-dessous répond à ce risque.

Séquence retenue : l'humain valide les géométries et le contenu de l'étape 4 → le LLM propose un message par occurrence → le LLM propose un message de synthèse (et un titre court) pour chaque groupe → l'humain suit le raisonnement du LLM à travers les messages individuels → l'humain valide la synthèse et le titre proposés, ou en rédige d'autres. Les messages individuels servent de trace de raisonnement pour cette dernière étape : sans eux, l'opérateur devrait vérifier la synthèse directement contre les citations sources brutes, sans étape intermédiaire.

Pour que cette validation soit possible, les champs suivants doivent rester accessibles jusqu'à cette étape, pour chaque occurrence d'un groupe (pas seulement pour le meneur) :
- la citation exacte (`extrait_significatif`) et son contexte (`contexte_documentaire`) ;
- la `justification` (raisonnement du modèle à l'étape 2) ;
- le lien vers le document source (`lien_web_document`) ;
- la référence précise (`reference_precise`).

Ces champs, à l'exception de `lien_web_document` et `reference_precise` déjà présents dans `etape4_{dept}.gpkg`, ne sont récupérés qu'au moment de l'étape 5, par la jointure décrite en introduction — inutile de les dupliquer dans le contrat de l'étape 4, qui n'en a pas besoin pour son propre usage.

**Nouveau champ** : `validation_message_commentaire`, distinct de `validation_manuelle_commentaire` (étape 3) — ce dernier porte sur la validité de l'occurrence elle-même (une décision déjà actée et gelée à l'étape 3), tandis que `validation_message_commentaire` porte sur la qualité du message généré, un sujet différent apparu à cette étape. Les mélanger risquerait de faire perdre l'un des deux commentaires ou de brouiller leur lecture.

**Outil de validation** : `outil_validation.html`, page HTML autonome sur le modèle de l'étape 3, avec deux modes ("Message par occurrence", "Message fusion") correspondant aux deux niveaux de message décrits ci-dessus. En mode "Message fusion", le titre proposé se corrige indépendamment du message de synthèse, avec le même mécanisme (case à cocher + reformulation). Chaque texte généré (message d'occurrence, message de synthèse, titre) reste conservé tel quel, natif, même une fois corrigé — l'opérateur coche une case pour indiquer qu'une reformulation doit être utilisée à la place, sans jamais écraser la version native. Deux raisons à cette conservation : la traçabilité déjà pratiquée partout ailleurs dans ce pipeline, et la possibilité, plus tard, de se servir des corrections accumulées comme exemples pour recalibrer la rédaction sur de prochains départements (fonctionnalité non construite pour l'instant). Une correction de message d'occurrence ne déclenche jamais de nouvelle génération de la synthèse correspondante — les niveaux de correction (occurrence, synthèse, titre) sont indépendants, voir `etape-5-conception-technique.md`, "Correction humaine : natif + correction, jamais de cascade", pour le détail et la justification de ce choix.

## Prochaine étape

Étape 6 — mise en forme des données selon le format attendu pour ingestion dans la base diagBruit, à partir des messages validés par cette étape et des géométries de l'étape 4.
