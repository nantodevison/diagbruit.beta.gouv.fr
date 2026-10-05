# Feuille de route — poc-urbanisme-plu

<!--
Ce fichier liste ce qui reste à faire. Il est lu par la compétence
"etat-des-lieux" en début de séance et mis à jour en fin de séance.
Gardez-le court : quelques lignes par section suffisent.
-->

## En cours
- [ ] Étape 5 (rédaction des messages), département 067 hors Eurométropole : Phase 1 (contrôle de
      similarité, 46 paires restantes, faux positifs liés à portee_geometrique=administrative) et
      Phase 2 (408 synthèses, fusion 12_67101/7_67101 appliquée) terminées. Reste la Phase 3
      (relecture manuelle) à faire.

## Prochaines étapes
- [ ] Relecture manuelle dans outil_validation.html (étape 5, Phase 3) — attention particulière à
      l'occurrence page 69 (Villé, secteur 1, risque de reformulation) et à 2_67239 (PADD 67239,
      mention "axes routiers" à vérifier contre le contexte documentaire).
- [ ] Une fois la relecture faite : synthese_messages.py puis verifier_orthographe.py (dans cet
      ordre, toujours).
- [ ] Retirer le TODO(alert_slug) de etape7_stockage/inserer.py une fois le correctif implémenté
      (voir docs/etape-7-conception-technique.md).

## Plus tard / idées
- Réinjecter les corrections humaines accumulées (message_*_corrige) comme exemples de
  recalibrage du prompt pour les prochains départements (reporté, voir
  docs/etape-5-conception-technique.md).
- Faire cascader une correction d'occurrence vers une régénération de synthèse, si le besoin se
  confirme à l'usage (reporté, même document).
- Nettoyer les doublons Strapi résiduels d'un bug d'idempotence désormais corrigé (voir
  docs/ameliorations-identifiees.md).

## Décisions récentes
<!-- Une ligne par décision : date — décision — raison en quelques mots -->
- 2026-09-29 — Ne pas fusionner les occurrences 67188 (zones Ur/Uh/Uhe/Ue/Ut) ni 67308/67443 —
  le message actuel affiche déjà la zone concernée, une fusion ferait perdre cette distinction.
- 2026-09-29 — Fusionner uniquement 12_67101 et 7_67101 (étape 4) : citation de 7_67101 tronquée,
  mais le contenu "agricole" de son message vient bien de contexte_documentaire (pas une
  invention du LLM, vérifié après coup) — la fusion produit un message qui couvre les deux volets
  de l'article 2 (activités + agricole), plus complet que chaque message pris séparément.
- 2026-09-29 — Prompt caching + cache disque ajoutés à preparer_messages.py (étape 5) pour
  réduire le coût LLM (~-60 % mesuré sur le 067, cache lu dès le 2e appel).
