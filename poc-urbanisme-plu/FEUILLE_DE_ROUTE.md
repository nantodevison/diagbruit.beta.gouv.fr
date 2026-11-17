# Feuille de route — poc-urbanisme-plu

<!--
Ce fichier liste ce qui reste à faire. Il est lu par la compétence
"etat-des-lieux" en début de séance et mis à jour en fin de séance.
Gardez-le court : quelques lignes par section suffisent.
-->

## En cours
- [x] Étape 7, 067 hors Eurométropole : envoyé le 2026-11-10 (Strapi préprod en brouillon,
      Notion, Box 428951751647). Après nettoyage du 2026-11-13 : 398 alertes cohérentes dans les
      trois bases (audit préprod : 0 doublon, 0 absent).
- [x] Un seul fichier géométrie par run : envoyé le 2026-11-16 (Box = 1 fichier de 398 zones,
      Notion = 398 pages recréées — ne pas restaurer les anciennes depuis la corbeille, Strapi
      préprod = 398 mises à jour). Dagster passe (Senhao, 2026-11-17) ; branche fusionnée.
- [ ] Question à l'équipe de dev : regrouper aussi les 28 fichiers de l'Eurométropole (dossier
      Box 398163261000) en un seul fichier ?
- [ ] Étape 8 (publication préprod, pour relecture par l'ATIP) : doc et code écrits le
      2026-11-13, dry-run conforme (398 à publier). ⚠️ HYPOTHÈSE NON VÉRIFIÉE sur la requête de
      publication : publier UNE alerte (--ids), la vérifier à l'œil (admin + front préprod),
      puis le reste. Voir docs/etape-8-conception-technique.md.
- [ ] Question à l'équipe de dev (2026-11-13) : séparation des géométries Box entre préprod
      et prod (Dagster lit 390359250129 et ses sous-dossiers) — risque d'encadrés vides en prod.
      Et chargement des géométries du 067 dans la base de préprod pour l'ATIP.
- [ ] Après les retours de l'ATIP : envoi et publication en prod, liens Legifrance dans reference.

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
- [ ] Avant le prochain territoire : proposition automatique des termes métier (niveaux 3 puis
      1 puis 2, voir docs/etape-6-conception-technique.md, "Évolution prévue").
- [ ] (Suggestion) Relire les autres titres et messages fixes (messages_fixes.py) avec le même
      regard sur le vocabulaire juridique (« prescription », « recommandation »).

## Plus tard / idées
- Renforcer l'étape 2 : un en-tête ou un article de zone (« Art. 2-UC », « au5 ») doit
  empêcher le classement en `administrative` (point 5 de docs/diagnostic-portee-administrative-067.md).
- Réinjecter les corrections humaines accumulées (message_*_corrige) comme exemples de
  recalibrage du prompt pour les prochains départements (reporté, voir
  docs/etape-5-conception-technique.md).
- Faire cascader une correction d'occurrence vers une régénération de synthèse, si le besoin se
  confirme à l'usage (reporté, même document).
- Étape 7 : envois limités pour les tests (option `--ids` listant des id_geometrie, contrôles
  bloquants toujours faits sur l'export entier ; éventuellement `--strapi-seulement` pour ne pas
  écrire dans Notion/Box, qui n'ont pas de préprod). Idée du 2026-11-10, test à 5 lignes
  abandonné au profit de l'envoi complet.
- (Intégré au niveau 3 de l'évolution prévue) Contrôler forme et unicité du slug dès la saisie
  dans outil_validation.html — unicité **sans tenir compte des majuscules**, comme le contrôle
  de l'étape 7 depuis le 2026-11-13 (aujourd'hui l'erreur n'est arrêtée qu'au dry-run).

## Décisions récentes
<!-- Une ligne par décision : date — décision — raison en quelques mots -->
- 2026-11-16 — Un seul .geojson par run (etape7_{dept}_geometries.geojson) au lieu d'un par
  zone, constitué à l'étape 7 (seule à connaître le slug final) ; zones, alertes Strapi et pages
  Notion restent une par zone, et chaque page Notion pointe vers ce fichier unique (un premier
  essai à un fichier par territoire a été abandonné le même jour). — Dagster traite
  les fichiers un par un et bloquait sur 398 ; une fois en base, la notion de fichier disparaît
  (l'alert_slug de chaque entité fait la jointure). Regroupement des zones elles-mêmes écarté.
- 2026-11-13 — Collision de casse : g303 (ZoneUA, « PAC et climatisation ») et g275
  (Secteur1AUe, « activités commerciales ») supprimés de Strapi préprod (à la main, le jeton n'a
  pas le droit delete), de Box et de l'export étape 6 (398 lignes) ; g358/g394 conservés, leurs
  pages Notion sont justes. Retirés de l'export seulement : une relance de generer_export.py
  les ferait revenir. Le journal etape7_067_insertions.csv garde leur trace. — Préférer perdre
  deux règles peu impactantes plutôt que risquer l'intégrité de bases qui ont une partie prod.
- 2026-11-13 — Étape 7 : recherche Notion par slug au caractère près (le filtre `equals` de
  Notion ignore la casse) et contrôle d'unicité des slugs sans tenir compte des majuscules —
  le 2026-11-10, ZoneUa/ZoneUA et Secteur1Aue/Secteur1AUe ont fusionné dans Notion.
- 2026-11-10 — Envoi complet du 067 plutôt qu'un lot test de 5 (décision prise avec l'équipe
  de dev). L'idée d'envois limités (`--ids`) est notée dans « Plus tard ».
- 2026-10-20 — Titre fixe « Aucune prescription bruit spécifique » → « Aucune disposition
  relative au bruit » (messages_fixes.py, etape5_067.gpkg, export étape 6 : 97 lignes) —
  « prescription » a un sens précis en urbanisme ; les titres fixes échappaient à la relecture.
- 2026-10-20 — Source/référence des cas sans document (obligatoires dans Strapi, vérifiées
  seulement à la publication) : RNU → Code de l'urbanisme / art. L111-1 à L111-35 et R111-1 à
  R111-64 ; absence GPU → Géoportail / « à date du » consultation étape 1 (25/08/2026) ; pas de
  référence bruit et non analysable → nom complet du document. Liens Legifrance : question
  posée à l'équipe de dev (option C).
- 2026-10-20 — Correctif étape 7 : contrôles bloquants sur l'export entier (format uid, unicité,
  géométrie, champs obligatoires, label), alert_slug écrit dans le .geojson local avant dépôt
  Box (option A : pas de copie modifiée silencieuse), recherche Strapi/Notion stricte, journal
  avec environnement et action, mode --audit en lecture seule.
- 2026-10-20 — Audit préprod/prod : 50 documents identiques, tous publiés avec brouillon, aucun
  doublon ; l'outil passe par l'API REST et n'envoie aucun id. Objectif : ne pas casser
  l'alignement prod/préprod.
- 2026-10-19 — Slugs : convention CamelCase pour le terme métier (tiret = séparateur) ; commune
  devant le terme en cas de répétition ; doublons g341 (de g337) et g403 (de g402) retirés de
  l'export étape 6 seulement (une relance de generer_export.py les ferait revenir).
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
