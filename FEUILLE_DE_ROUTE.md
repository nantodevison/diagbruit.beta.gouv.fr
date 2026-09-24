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
  - [ ] Comparer favoris / non-favoris (chiffres + lecture) et lister les
        doublons présents dans la base.
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
