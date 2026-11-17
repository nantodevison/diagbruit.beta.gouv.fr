# Feuille de route — Veille documentaire bruit-santé

<!--
Ce fichier liste ce qui reste à faire. Il est lu par la compétence
"etat-des-lieux" en début de séance et mis à jour en fin de séance.
Gardez-le court : quelques lignes par section suffisent.
-->

## En cours
- [x] Créer la documentation spécifique au projet de veille documentaire
      (`veille-bruit-sante/CLAUDE.md` + mention dans le `CLAUDE.md` racine)
- [x] Cadrer l'artefact de synthèse (30/09) → `docs/etape-5-artefact-synthese-diagbruit.md`
- [x] Choisir le support (30/09) : hybride, vue Notion « À trier » + page
      HTML publique (GitHub Pages du fork) pour le contenu validé.
- [x] Premier jet du socle (30/09) → `veille-bruit-sante/socle/etat-connaissances.yaml` :
      7 effets, 2 pistes émergentes, glossaire, 17 références. Chiffres
      vérifiés par script dans les sources (citation exacte conservée).
- [x] Validation du socle (30/09 et 02/10) → version 1.0, validée par Martin
      Schoreisz : 6 effets (cardiovasculaire, sommeil, gêne, apprentissages
      de l'enfant, métabolique, santé mentale), un encadré « À ne pas
      confondre » (effets auditifs), 2 pistes émergentes (cancer, démence) ;
      grossesse retirée. 27 chiffres et valeurs guides vérifiés dans leur source.
  - [x] Valeurs guides OMS 2018 vérifiées (résumé exécutif) ; `.venv` de la
        veille créé avec les dépendances du projet et `pypdf`.
  - [x] Revues OMS gêne et cognition ajoutées à la base et qualifiées
        (0,27 $ + 0,15 $) ; `domaine_sante` renseigné à la main.
  - [x] Chiffre « ×3 à ×5 » vérifié (17/11) dans la revue OMS gêne : vaut
        pour l'avion seulement (route et train ≈ ×3), et c'est la cote d'être
        fortement gêné qui est multipliée, pas le nombre de personnes. Ajouté
        à l'effet gêne → socle **v1.1**, validé le 17/11.
  - [x] Fiche OMS cognition (17/11) : `sens_conclusion` « Non concluant » →
        « Effet demontre » ; titre déjà sur une seule ligne.
- [x] **Conception technique validée** (17/11) → `veille-bruit-sante/docs/etape-5-conception-technique.md`
      (7 décisions). Lots à réaliser, dans l'ordre :
  - [x] **Lot 1 — nettoyage de `domaine_sante`** (terminé le 17/11) :
    - [x] Fiches nettoyées dans Notion (17/11) : 97 fiches modifiées,
          vérifié (0 restante) ; sauvegarde des anciennes étiquettes dans
          `analyse_relecture/export/etudes_2026-11-17_avant_nettoyage.csv`.
    - [x] Schéma Notion réduit de 112 à 10 options (`Demence` sera créée à
          la première fiche qui l'utilise).
    - [x] Nouvelle liste `OPTIONS_DOMAINE_SANTE` (11 options, identique au
          socle, vérifié par script) et définitions du `PROMPT_SYSTEME`
          (≈ 2 650 tokens, cache toujours actif) ; guide utilisateur à jour.
  - [ ] Lot 2 — colonnes `verdict` (LLM, résumé du socle dans le prompt) et
        `piste_actualite` (case manuelle), migration `--ajouter-artefact`.
  - [ ] Lot 3 — run à 15 jours (semaines ISO paires) et retrait du
        déclencheur `push` du workflow.
  - [ ] Lot 4 — script de génération de la page (`etape5_artefact/`, Jinja2).
  - [ ] Lot 5 — publication sur GitHub Pages du fork (voir « Rendre le run
        automatique » ci-dessous).
- [ ] **Version 2 de la page — regard transversal « Enfants »** (reporté le
      17/11, NE PAS OUBLIER) : validé dans le cadrage le 02/10 mais exclu de
      la v1 pour publier plus tôt. Rassemble apprentissages (bruit des avions),
      santé mentale de l'enfant (cohorte ELFE) et chiffres AEE (lecture,
      comportement, surpoids) ; s'appuie sur l'option `Enfant` de `domaine_sante`.

## Prochaines étapes
- [ ] **Passer le run à 15 jours**, le lundi, 6 h UTC (données prêtes avant
      8 h à Paris) — cron hebdomadaire, le run ne fait rien une semaine sur deux.
- [ ] **Rendre le run automatique** : aujourd'hui il se lance à la main
      (`python main.py`), car GitHub ne déclenche la tâche planifiée du lundi
      que depuis `main`, qui n'a ni le workflow ni le code de la veille.
      Il faut fusionner la branche dans le `main` **du fork**
      (`nantodevison/…`, décidé le 30/09), y configurer les 3 secrets
      (ANTHROPIC_API_KEY, NOTION_API_KEY, NOTION_DATABASE_ID), activer les
      tâches planifiées (désactivées par défaut sur un fork) et GitHub Pages.
      Le déclencheur `push` (un run payant à chaque fusion) sera retiré
      (décidé le 17/11, lot 3).
- [x] **Case `ajout_manuel`** (29/09) : cochée automatiquement (auteur Notion
      de la fiche ≠ intégration), ignorée pour la date de départ du run
      (vérifié : le prochain run repart bien du 26/08). `regenerer_resumes`
      ne classe plus hors périmètre un document retenu, et ne remplace plus
      un résumé par du vide.
- [ ] **Analyse de la relecture manuelle** — premier parcours de la base Notion
      fait, publications les plus importantes taguées « favoris ».
  - [x] Exporter la base en CSV (`analyse_relecture/exporter_base.py`) :
        102 fiches, 55 favoris, toutes au statut « Lu », `url_source` vide
        partout, `fichier` renseigné sur 29 favoris (24 liens, 5 fichiers Notion).
  - [x] Comparer favoris / non-favoris (chiffres + lecture) et lister les
        doublons présents dans la base → `analyse_relecture/analyse-2026-09-24.md`.
  - [x] Valider les hypothèses H1–H5 et les 3 questions de l'analyse.
  - [x] Implémenter la qualification (type_document, sens_conclusion,
        elements_probants, reprise_de → candidat_favori, nouveaute) et le
        résultat chiffré obligatoire.
  - [x] Tester la règle sur les 80 fiches relues ayant un contenu source :
        précision 81 %, rappel 60 %, 1,16 $ (analyse, section 7).
  - [x] Décider de la règle : remplacée par une priorité à 3 niveaux (voir
        décisions du 25/09).
  - [x] Trancher : les communiqués, pages d'information et revues narratives
        mis en favori peuvent devenir candidats (oui).
  - [x] Ajouter l'attribut `priorite` (Haute / A examiner / Faible) et
        retirer `candidat_favori` (code + colonne Notion, migrée le 25/09).
        Mesuré : Haute = 81 % de favoris, Haute + A examiner = 93 % des
        favoris retrouvés.
  - [x] Ne plus rien écarter silencieusement : `contenu_insuffisant` →
        case `a_verifier` au lieu d'exclure ; exclusions et doublons
        journalisés avec titre et motif.
  - [x] Créer un graphique Mermaid du workflow → `veille-bruit-sante/docs/workflow-veille.md`.
  - [x] Vérifier avec le nouveau prompt les 8 fiches écartées au test (0,10 $) :
        6 gardées dont le favori (5 avec `a_verifier`), 2 écartées avec motif.
        A révélé une erreur 400 « Schema is too complex » (corrigée : champs
        d'extraction sans valeur par défaut).
  - [x] Remplir la qualification des 102 fiches déjà en base
        (`analyse_relecture/qualifier_base_existante.py`, 25/09) — `favori`,
        `statut`, `fichier` vérifiés intacts. Résultat : Haute 32, A examiner
        38, Faible 32 ; 28 fiches `a_verifier`. 16 favoris en Faible, dont 14
        faute de contenu lisible (11 ont un `fichier` → la régénération à
        partir du texte intégral devrait les faire remonter).
  - [ ] Diagnostiquer les 2 échecs d'extraction (`ValidationError`) sur des
        pages Inserm en français.
  - [x] Ajouter les colonnes de qualification à la base Notion
        (`--ajouter-qualification`), fait le 24/09.
  - [ ] Coût : la réflexion (thinking) de Sonnet 5 est active par défaut sur
        l'extraction et représente environ la moitié du coût. Mesurer si
        `effort: low` ou thinking désactivé garde la qualité.
  - [ ] Nettoyer les étiquettes domaine_sante / source_bruit des 102 fiches
        — **prérequis de l'artefact** (rattachement de chaque document à un
        effet du socle).
  - [ ] Canal web : donner à chaque source son propre contexte (aujourd'hui
        la synthèse globale est partagée par toutes).
  - [x] Régénérer `resume`, `resultat_cle` et la qualification à partir du
        texte intégral (`analyse_relecture/regenerer_resumes.py`, 25/09) :
        les 29 fiches avec fichier, 7,46 $ (dont 4,47 $ pour les 3 gros
        rapports). Favoris : 32 Haute, 17 A examiner, 6 Faible (contre
        25 / 14 / 16) avant la dernière fiche. La fiche du communiqué Inserm
        ELFE a été supprimée (même source que l'article) : base à 101 fiches.
  - [ ] Affiner la détection des contenus réellement nouveaux :
    - [ ] repérer les reprises (communiqués, relais presse) d'études déjà
          connues ou anciennes, que le dédoublonnage DOI/titre ne voit pas ;
    - [ ] vérifier l'écart date d'ajout Notion / date de publication OpenAlex
          (risque d'études indexées tardivement jamais retrouvées) ;
    - [ ] comparer favoris / non-favoris pour en tirer des critères de
          recherche et d'extraction pour le LLM (`PROMPT_SYSTEME`).

## Plus tard / idées
- (suggestion) `regenerer_resumes --estimer` écrit la case `ajout_manuel` dans
  Notion avant d'estimer : le documenter, ou le déplacer hors du mode estimation.

## Décisions récentes
<!-- Une ligne par décision : date — décision — raison en quelques mots -->
- 2026-09-24 — Créer un CLAUDE.md dédié à la veille — le README et les docs
  existent, mais aucune consigne de travail n'est chargée automatiquement
  dans ce dossier.
- 2026-09-24 — Produire un artefact de synthèse en plus de la base Notion —
  revient sur le choix du cadrage (« pas de digest séparé ») : l'objectif
  inclut désormais de faciliter la compréhension des articles.
- 2026-09-24 — Le texte intégral (colonne `fichier`) sert à régénérer le
  résumé de la fiche Notion — la fiche reste la source unique, l'artefact de
  synthèse en profite automatiquement.
- 2026-09-24 — Critères d'un favori : conclusion claire (effet démontré ou
  infirmé), source fiable et reconnue, explications qui étayent — issus de
  la relecture manuelle de la base.
- 2026-09-24 — Textes de référence anciens conservés, mais distingués des
  nouveautés — ce sont des jalons qui contextualisent les nouveaux documents.
- 2026-09-24 — Article et communiqué qui le relaie : on garde les deux —
  pas de préférence, le lien entre les deux reste à établir.
- 2026-09-25 — Rappel avant précision : mieux vaut plus de documents à trier
  à la main que manquer silencieusement un favori potentiel.
- 2026-09-25 — Tous les types de documents (communiqués, revues narratives…)
  peuvent devenir candidats — plusieurs favoris manuels en font partie.
- 2026-09-25 — Priorité à 3 niveaux comme nouvel attribut automatique,
  distinct de la case `favori` — la priorité informe, la case traduit le
  choix de l'utilisateur. `candidat_favori` est retiré, devenu redondant.
- 2026-09-25 — Ne rien écarter silencieusement — conséquence directe du
  choix « rappel avant précision ».
- 2026-09-30 — Artefact en deux visions (état des connaissances fondé sur
  un socle validé ; sorties récentes « À trier » / « Retenus ») — deux
  usages et deux publics : le tri par le mainteneur, les actualités pour l'équipe.
- 2026-09-30 — Rythme de 15 jours, lundi 8 h (Paris), pour la veille comme
  pour l'artefact — fréquence jugée suffisante, coût réduit.
- 2026-09-30 — Support hybride : « À trier » en vue Notion, état des
  connaissances + « Retenus » en page HTML publique sur GitHub Pages du
  fork — rendu visuel pour le contenu validé, rien de non relu en public.
- 2026-09-30 — La veille tourne sur le fork, pas sur le dépôt `betagouv` —
  secrets, planification et Pages au même endroit, sans droits d'organisation.
- 2026-09-30 — Le socle décrit les effets sur la santé, pas les moyens d'y
  remédier — le contenu reste factuel ; les recommandations d'action (isolation,
  aménagement) n'y ont pas leur place.
- 2026-09-30 — Chiffres du socle vérifiés par script (téléchargement + recherche
  de texte, sans LLM), citation exacte conservée — une extraction LLM ne suffit
  pas : « 112 à 150 millions d'exposés » était introuvable dans le rapport AEE.
- 2026-10-02 — Les chiffres affichés concernent les gens (personnes touchées,
  hausse de risque) ; les chiffres de spécialiste (nombre d'études) restent
  internes — ton « compréhensible par un non-spécialiste ».
- 2026-10-02 — Effets auditifs en encadré « À ne pas confondre » plutôt qu'en
  effet du socle — effet le plus connu, mais rarement causé par le bruit des
  transports chez soi.
- 2026-10-02 — Grossesse retirée du socle, démence ajoutée en piste émergente —
  la seule source sur la grossesse mêle bruit professionnel et preuves très faibles.
- 2026-10-02 — Étude E3N (diabète) : chiffres du modèle principal (+8 % / +12 %),
  pas les +21 % de la fiche Notion — plus prudents, et ce sont ceux du résumé.
- 2026-11-17 — `domaine_sante` reprend la liste du socle, plus `General` pour les
  documents d'ensemble — la gêne manquait à l'ancienne liste fermée, et le
  script de la page doit compter les documents par effet.
- 2026-11-17 — Une seule option `Enfant` (apprentissages + public enfants) —
  plus simple à trier ; le compte du bloc « apprentissages » inclut donc les
  autres études chez l'enfant.
- 2026-11-17 — Retrait du déclencheur `push` du workflow — évite un run payant
  à chaque fusion ; le lancement manuel reste possible.
- 2026-11-17 — Regard « Enfants » reporté à la v2 de la page — publier plus tôt
  la lecture par effet.
