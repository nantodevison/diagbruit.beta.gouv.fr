# Feuille de route — poc-urbanisme-plu

<!--
Ce fichier liste ce qui reste à faire. Il est lu par la compétence
"etat-des-lieux" en début de séance et mis à jour en fin de séance.
Gardez-le court : quelques lignes par section suffisent.
-->

## En cours
- [ ] Étape 6, phase 2 (saisie des alert_slug dans outil_validation.html), 067 hors
      Eurométropole : export généré le 2026-10-13 (402 lignes, 249 slugs automatisés) ;
      saisie manuelle en cours (26 faits, 127 restants au 2026-10-13, dernier export
      etape6_export_alert_slugs_20261013_180833.csv). En fin de saisie, renommer le
      dernier export en etape6_067_export.csv.

## Prochaines étapes
- [ ] Vérifier l'occurrence 2_67239 (PADD 67239, mention "axes routiers" à vérifier contre
      le contexte documentaire), si ce n'a pas été fait pendant la passe rapide du 2026-10-12.
- [ ] Mesurer combien d'occurrences `zone_urba_auto` du 067 oublient des sous-secteurs : la
      correspondance zone-urba ne retient que le code exact (ex. g308 Diemeringen : « UB »
      retenu, secteur UBa couvert à 0 % alors que la règle vaut « dans l'ensemble de la zone »).
      Corriger aussi la référence de g308 (page 8 → page 13, art. UB 1.1).
- [ ] Documenter dans docs/ameliorations-identifiees.md : la couche texte des PDF « modèle »
      (Heiligenberg, Kurtzenhouse, Lauterbourg, Scheibenhard, Weitbruch, Munchhausen) est décalée
      par rapport à l'affichage, ce qui fausse pages et portées à l'étape 2.
- [ ] Retirer le TODO(alert_slug) de etape7_stockage/inserer.py une fois le correctif implémenté
      (voir docs/etape-7-conception-technique.md).
      À faire avant tout --envoyer : ajouter alert_slug aux .geojson et contrôler sa forme avec
      la règle Strapi uid (A-Z a-z 0-9 - _ . ~, appliquée seulement à la publication, pas au
      brouillon — lue dans @strapi/core 5.13.0).

## Plus tard / idées
- Renforcer l'étape 2 : un en-tête ou un article de zone (« Art. 2-UC », « au5 ») doit
  empêcher le classement en `administrative` (point 5 de docs/diagnostic-portee-administrative-067.md).
- Réinjecter les corrections humaines accumulées (message_*_corrige) comme exemples de
  recalibrage du prompt pour les prochains départements (reporté, voir
  docs/etape-5-conception-technique.md).
- Faire cascader une correction d'occurrence vers une régénération de synthèse, si le besoin se
  confirme à l'usage (reporté, même document).
- Nettoyer les doublons Strapi résiduels d'un bug d'idempotence désormais corrigé (voir
  docs/ameliorations-identifiees.md).
- (Suggestion) Contrôler la forme du slug dès la saisie dans outil_validation.html, pour
  repérer une erreur tout de suite plutôt qu'à l'étape 7.

## Décisions récentes
<!-- Une ligne par décision : date — décision — raison en quelques mots -->
- 2026-10-13 — Villé (géométrie 412, OAP p.69) : message corrigé du 2026-10-12 confirmé
  sur l'image du PDF (la règle bruit est une puce distincte de la partie Est), rien à modifier.
- 2026-10-13 — Slugs remplis automatiquement pour les cas sans contenu métier mono-commune,
  selon nature_zone : alert-{Territoire}-{Commune}{RNU|AbsenceGPU|PasDeReferenceBruit|
  DocNonAnalysable} — « prescription »/« recommandation » évités (sens précis en urbanisme).
- 2026-10-13 — Noms de territoire/commune réduits à A-Z a-z 0-9 dans le slug : le tiret est
  réservé au séparateur. Statuts de slug (vide, initialisé, automatisé, manuel) : seuls les
  manuels sont repris à la relance de generer_export.py.
- 2026-10-13 — Résolution de territoire : ne garder que la commune au nom exact (la recherche
  geo.api.gouv.fr est approximative, 36 lignes sans territoire sur le 067).
- 2026-10-12 — Ne pas fusionner Heiligenberg g193/g314, Lupstein g224/g353 et Munchhausen
  g298/g417 (avertissements de similarité) : règles distinctes sur une même zone (émergences
  acoustiques ou agricole vs « établissements de toute nature »), même logique que le 2026-09-29.
- 2026-10-12 — Portées administratives du 067 corrigées après vérification de chaque page sur
  l'image du PDF : 23 recalées sur leur zone (geometrie_origine = correction_portee), 7 rejetées
  (doublons, ou règle absente du 2AUh), 1 confirmée (Weitbruch g273) ; fusion Dorlisheim
  12_67101 / 7_67101 annulée (g175 → 1AU, g176 → UC). Preuves dans
  output/067_horsEurometropole/etape4_067_propositions_portee.csv.
- 2026-10-09 — Contrôle de portée (controle_portee.py) et rejet étendu à la couche
  geometries_administratives : la portée décidée par le LLM n'était plus contrôlée après l'étape 2.
- 2026-10-07 — La décision du 2026-09-29 de fusionner 12_67101 et 7_67101 est remise en cause :
  le PDF montre deux zones distinctes (7 = UC p.35, 12 = 1AU p.88), il faut les séparer, pas les
  fusionner.
- 2026-09-29 — Ne pas fusionner les occurrences 67188 (zones Ur/Uh/Uhe/Ue/Ut) ni 67308/67443 —
  le message actuel affiche déjà la zone concernée, une fusion ferait perdre cette distinction.
- 2026-09-29 — Fusionner uniquement 12_67101 et 7_67101 (étape 4) : citation de 7_67101 tronquée,
  mais le contenu "agricole" de son message vient bien de contexte_documentaire (pas une
  invention du LLM, vérifié après coup) — la fusion produit un message qui couvre les deux volets
  de l'article 2 (activités + agricole), plus complet que chaque message pris séparément.
- 2026-09-29 — Prompt caching + cache disque ajoutés à preparer_messages.py (étape 5) pour
  réduire le coût LLM (~-60 % mesuré sur le 067, cache lu dès le 2e appel).
