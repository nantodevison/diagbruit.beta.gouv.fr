# Feuille de route — Veille documentaire bruit-santé

<!--
Tâches ouvertes : kanban Grist (projet diagBruit, EPIC 37 « Veille-Santé »),
recopié ci-dessous par taches.py. Ce fichier garde aussi l'historique de
ce qui est fait et les décisions. Gardez-le court.
-->

<!-- début kanban : section régénérée par taches.py, ne pas modifier à la main -->
## Kanban (Grist)
_Projet « diagBruit » — EPIC 37 « Veille-Santé » — lu le 2026-11-18 17:36_

### 🖐️ À faire
- [ ] #250 Artefact lot 2 : colonnes verdict et piste_actualite (Haute)
- [ ] #252 Artefact lot 4 : script de génération de la page HTML (Jinja2) (Haute)
- [ ] #253 Artefact lot 5 : publication sur GitHub Pages du fork (Haute)
- [ ] #254 Run de contrôle de la veille de bout en bout (Haute)
- [ ] #251 Artefact lot 3 : run à 15 jours et retrait du déclencheur push (Moyenne)
- [ ] #257 Coût : tester effort low ou extraction sans thinking (Moyenne)
- [ ] #258 Canal web : un contexte propre à chaque source (Moyenne)
- [ ] #259 Repérer les reprises d'études déjà connues (Moyenne)
- [ ] #260 Vérifier l'écart date d'ajout Notion / date de publication OpenAlex (Moyenne)
- [ ] #255 Artefact v2 : regard transversal Enfants (Basse)
- [ ] #256 Diagnostiquer les 2 échecs d'extraction sur des pages Inserm (Basse)
- [ ] #261 Comparer favoris et non-favoris pour affiner le PROMPT_SYSTEME (Basse)
- [ ] #262 regenerer_resumes --estimer écrit ajout_manuel dans Notion (Basse)

<!-- fin kanban -->

## Historique (fait)
<!-- Les tâches ouvertes sont suivies dans Grist (kanban ci-dessus) depuis le 18/11/2026. -->

### Artefact de synthèse (étape 5)
- 30/09 — Cadrage → `docs/etape-5-artefact-synthese-diagbruit.md` ; support
  hybride (vue Notion « À trier » + page HTML publique sur GitHub Pages du fork).
- 30/09–02/10 — Socle « état des connaissances » rédigé puis validé (v1.0) →
  `veille-bruit-sante/socle/etat-connaissances.yaml` : 6 effets, encadré
  auditif, 2 pistes émergentes ; 27 chiffres vérifiés dans leur source.
  Revues OMS gêne et cognition ajoutées à la base Notion.
- 17/11 — Socle v1.1 : chiffre « ×3 à ×5 » de la revue OMS gêne vérifié (avion
  seulement ; c'est la cote d'être fortement gêné qui est multipliée). Fiche
  OMS cognition : `sens_conclusion` → « Effet demontre ».
- 17/11 — Conception technique validée →
  `veille-bruit-sante/docs/etape-5-conception-technique.md` (7 décisions, 5 lots).
- 17/11 — Lot 1, nettoyage de `domaine_sante` : 97 fiches modifiées, schéma
  Notion réduit de 112 à 10 options, `OPTIONS_DOMAINE_SANTE` et `PROMPT_SYSTEME`
  alignés sur le socle ; sauvegarde des anciennes étiquettes dans
  `analyse_relecture/export/etudes_2026-11-17_avant_nettoyage.csv`.

### Veille et analyse de la relecture manuelle
- 24/09 — `veille-bruit-sante/CLAUDE.md` créé. Export de la base, comparaison
  favoris / non-favoris → `analyse_relecture/analyse-2026-09-24.md`.
- 24–25/09 — Qualification (type_document, sens_conclusion, elements_probants,
  reprise_de, nouveaute) puis `priorite` à 3 niveaux à la place de
  `candidat_favori` : Haute = 81 % de favoris, Haute + A examiner = 93 % des
  favoris retrouvés. Rien n'est plus écarté silencieusement (`a_verifier`).
- 25/09 — Qualification des 102 fiches existantes ; régénération des résumés
  à partir du texte intégral pour les 29 fiches avec fichier (7,46 $).
- 25/09 — Schéma du workflow → `veille-bruit-sante/docs/workflow-veille.md`.
- 29/09 — Case `ajout_manuel` cochée automatiquement, ignorée pour la date de
  départ du run.

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
- 2026-11-18 — Suivi des tâches dans Grist (projet diagBruit, EPIC 37) plutôt
  que dans ce fichier — kanban commun aux autres projets ; ce fichier garde
  l'historique et les décisions.
