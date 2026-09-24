# Feuille de route — Veille documentaire bruit-santé

<!--
Ce fichier liste ce qui reste à faire. Il est lu par la compétence
"etat-des-lieux" en début de séance et mis à jour en fin de séance.
Gardez-le court : quelques lignes par section suffisent.
-->

## En cours
- [x] Créer la documentation spécifique au projet de veille documentaire
      (`veille-bruit-sante/CLAUDE.md` + mention dans le `CLAUDE.md` racine)

## Prochaines étapes
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
  - [ ] Décider d'un ajustement de la règle (variantes A/B de l'analyse) ou
        la garder telle quelle.
  - [ ] Diagnostiquer les 2 échecs d'extraction (`ValidationError`) sur des
        pages Inserm en français.
  - [x] Ajouter les colonnes de qualification à la base Notion
        (`--ajouter-qualification`), fait le 24/09.
  - [ ] Coût : la réflexion (thinking) de Sonnet 5 est active par défaut sur
        l'extraction et représente environ la moitié du coût. Mesurer si
        `effort: low` ou thinking désactivé garde la qualité.
  - [ ] Nettoyer les étiquettes domaine_sante / source_bruit des 102 fiches.
  - [ ] Canal web : donner à chaque source son propre contexte (aujourd'hui
        la synthèse globale est partagée par toutes).
  - [ ] Régénérer `resume` et `resultat_cle` à partir du texte intégral pour
        les fiches dont la colonne `fichier` est renseignée (liens externes :
        PDF ou page web ; fichiers Notion : lien valable ~1 h). Estimer le
        coût avant tout lancement.
  - [ ] Affiner la détection des contenus réellement nouveaux :
    - [ ] repérer les reprises (communiqués, relais presse) d'études déjà
          connues ou anciennes, que le dédoublonnage DOI/titre ne voit pas ;
    - [ ] vérifier l'écart date d'ajout Notion / date de publication OpenAlex
          (risque d'études indexées tardivement jamais retrouvées) ;
    - [ ] comparer favoris / non-favoris pour en tirer des critères de
          recherche et d'extraction pour le LLM (`PROMPT_SYSTEME`).
  - [ ] Produire une première version de l'artefact de synthèse
        (forme à préciser : périmètre, support, fréquence).

## Plus tard / idées
- …

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
