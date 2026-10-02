# Étape 5 — Artefact de synthèse

*Document de cadrage de l'étape 5 de la veille bruit & santé de diagBruit, validé le 30/09/2026. Fait suite à la décision du 24/09/2026 de produire un artefact de synthèse en plus de la base Notion. Il s'agit d'un **MVP** : la version la plus simple qui rende le service attendu. Le support est choisi (voir « Support ») ; la conception technique reste à mener.*

**Entrée** : la base Notion « Études », alimentée automatiquement (étapes 2 à 4) et triée à la main.

## Public et finalité

- **Public** : l'équipe diagBruit (le responsable du projet, les développeurs, le chargé de déploiement, la PO). Tous ont accès à Notion.
- **Finalité** : servir de support pour publier des **actualités sur le site de diagBruit**. Elles rappellent pourquoi il est important de traiter le problème du bruit. L'équipe a choisi l'angle santé, et l'artefact doit permettre de l'étayer.
- **Mainteneur unique** pour l'instant : aucun dispositif de maintien en condition opérationnelle n'est prévu.

## Ton

Fournir des informations **factuelles et compréhensibles par un non-spécialiste** sur l'impact du bruit sur la santé, issues d'études scientifiques ou de sources qui relaient ces études. Concrètement :
- le **niveau de certitude** de chaque affirmation est affiché (démontré / probable / débattu) ;
- une **étude originale** et une **source qui la relaie** (communiqué, article de presse) se distinguent visuellement ;
- un **glossaire** court explique les termes techniques (Lden, Lnight, risque relatif, méta-analyse, cohorte…) ;
- une **mention de limites** accompagne le contenu : « synthèse de veille, pas une expertise sanitaire » ;
- tout est rédigé en **français**, même quand les sources sont en anglais ;
- le contenu décrit les **effets du bruit sur la santé**, pas les moyens d'y remédier (isolation, aménagement…) : pas de recommandation d'action dans le socle (décision du 30/09/2026) ;
- les chiffres affichés **concernent les gens** (personnes touchées, hausse de risque) ; les chiffres de spécialiste (nombre d'études, qualité méthodologique) servent à justifier les niveaux de preuve mais ne sont pas mis en avant (décision du 02/10/2026).

## Vision 1 — État des connaissances

Un rendu **plutôt visuel** (sans que ce soit obligatoire) qui répond à la question : quels impacts du bruit sur la santé sont prouvés ?

- Il repose sur un **socle rédigé puis validé** par le responsable du projet. Le socle n'est pas déduit automatiquement de la base : affirmer qu'un effet est « prouvé » demande une relecture humaine.
- Il est **organisé par effet sur la santé**. La liste de départ reprend celle des lignes directrices OMS 2018 : maladies cardiovasculaires, troubles du sommeil, gêne, apprentissage chez l'enfant, santé mentale, troubles métaboliques, effets auditifs.
- Chaque effet présente :
  - son niveau de preuve, en s'appuyant sur les gradations existantes (OMS, ANSES) plutôt que sur des critères maison ;
  - un ou deux chiffres clés, exprimés si possible avec les indicateurs utilisés par diagBruit (Lden, Lnight, sources routière, ferroviaire et aérienne) ;
  - les 2 ou 3 études les plus emblématiques et les moins controversées, avec leur lien ;
  - une phrase « pourquoi c'est important », réutilisable dans une actualité.
- **Premier jet** : rédigé une fois à partir des textes de référence déjà présents dans la base, puis validé. Le socle est ensuite **révisé ponctuellement**, quand une étude marquante le justifie.
- **Regards transversaux** (validé le 02/10/2026) : en plus de la lecture par effet, la page propose des angles de vue qui rassemblent des éléments du socle sans les dupliquer. Premier angle : **« Enfants »** (apprentissages avec le bruit des avions, santé mentale de l'enfant avec le bruit routier d'après la cohorte ELFE, chiffres AEE sur les enfants : difficultés de lecture, troubles du comportement, surpoids).
- Le socle est un **fichier versionné dans le dépôt** (YAML ou Markdown) : chaque validation ou révision passe par un commit, donc elle est tracée.

## Vision 2 — Sorties récentes

Deux sections, parce que ce sont deux usages et deux publics différents :

- **« À trier »** (pour le responsable du projet, **vue filtrée de la base Notion**, pas sur la page publique) : tous les documents non encore lus. Chacun est accompagné de l'aide produite par le LLM lors de l'intégration dans Notion : résumé, résultat clé, priorité, effet concerné, verdict par rapport au socle, et les autres attributs utiles au classement.
- **« Retenus »** (pour l'équipe, sur la page HTML) : les documents cochés `favori`. Chacun y apparaît avec sa conclusion, son apport, son verdict par rapport au socle, le lien vers l'étude et une case **« piste d'actualité »** que le responsable du projet coche.

Les attributs se **modifient dans Notion** : chaque document de l'artefact renvoie vers sa fiche.

## Lien entre les deux visions

Chaque document nouveau est rattaché au socle par deux attributs :
- l'**effet** concerné (colonne `domaine_sante`, à nettoyer au préalable et dont les options sont alignées sur la liste des effets du socle ; le script de génération fait les comptes) ;
- un **verdict par rapport au socle** : *confirme / nuance / contredit / sujet absent du socle*. C'est une nouvelle colonne, proposée par le LLM à l'intégration et validée pendant le tri.

Dans la vision 1, chaque effet affiche le nombre de documents nouveaux depuis la dernière révision du socle. Un « contredit » ou un « sujet absent du socle » signale qu'une révision est peut-être nécessaire.

## Support (décidé le 30/09/2026)

**Hybride** :
- **« À trier »** reste une **vue filtrée de la base Notion**. C'est l'outil de travail du mainteneur, le tri s'y fait de toute façon, et la vue est à jour en direct.
- **L'état des connaissances et les « Retenus »** forment une **page HTML statique**. Elle est générée par un script après chaque run, dans le workflow GitHub Actions, puis publiée sur **GitHub Pages**.

**Pourquoi :** le contenu validé est celui qui profite d'un vrai rendu visuel et qui sert à l'équipe. Le contenu non relu (« À trier ») ne doit pas être public.

**Conséquences acceptées :**
- La page est **publique**, puisque le dépôt est un fork public : `nantodevison.github.io/diagbruit.beta.gouv.fr`. Son référencement par les moteurs de recherche est désactivé, mais elle reste accessible à quiconque a le lien.
- Le workflow, les secrets et GitHub Pages vivent sur le **fork** (`nantodevison/diagbruit.beta.gouv.fr`), pas sur le dépôt `betagouv`.
- Modifier un attribut se fait dans Notion : chaque document de la page renvoie vers sa fiche.

**Écarté :**
- une page entièrement dans Notion : rendu visuel trop limité pour l'état des connaissances ;
- un artefact claude.ai : ne se met pas à jour tout seul sans séance Claude ou connecteur par lecteur.

## Fraîcheur

- **Rythme** : tous les 15 jours, le lundi. Le pipeline de la veille passe lui aussi à ce rythme, pour rester simple et limiter les coûts.
- **Horaire** : données prêtes à **8 h, heure de Paris**. GitHub Actions ne connaît que l'heure UTC : un lancement à 6 h UTC garantit que tout est prêt avant 8 h toute l'année. GitHub ne sait pas non plus planifier « tous les 15 jours » : le déclenchement reste hebdomadaire et le run ne fait rien une semaine sur deux.
- L'artefact affiche la **date de la dernière récupération** des données et **celle de la prochaine**.

## Coût

On réutilise les champs déjà produits (`resume`, `resultat_cle`, qualification). Le seul appel LLM ajouté est le verdict par rapport au socle. Comme le socle est un texte stable, il peut entrer dans le prompt système de l'extraction et profiter du cache. Il faut toutefois surveiller deux points : l'allongement du prompt, et la limite de complexité du schéma d'extraction (un champ de plus). La rédaction du premier jet du socle est un appel ponctuel.

## Prérequis

- **Fusion de la branche dans le `main` du fork**, pour que le run se lance automatiquement (voir `FEUILLE_DE_ROUTE.md`). Sur un fork, GitHub désactive par défaut les tâches planifiées : il faut les activer dans l'onglet Actions. Sur un dépôt public, GitHub les désactive aussi après 60 jours sans activité sur le dépôt.
- **Activation de GitHub Pages** sur le fork, avec comme source « GitHub Actions ».
- **Nettoyage des étiquettes `domaine_sante`** des fiches existantes.

## Hors MVP

- Modifier les attributs Notion depuis l'artefact.
- Historique des éditions : Notion conserve tout, et l'artefact montre l'état du moment.

## Suite

1. ~~Choisir le support~~ : fait le 30/09/2026 (hybride Notion + page HTML).
2. Rédiger le premier jet du socle, puis le faire valider.
3. Mener la conception technique (`etape-5-conception-technique.md`) : colonnes `verdict` et `piste d'actualité`, alignement de `domaine_sante`, passage du run à 15 jours, script de génération et publication sur GitHub Pages.
