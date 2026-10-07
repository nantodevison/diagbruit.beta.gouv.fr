# Diagnostic — doublons de messages liés à `portee_geometrique = administrative` (067 hors Eurométropole)

*Rédigé le 2026-10-07, pendant la relecture manuelle de l'étape 5 (Phase 3).*

## Le constat

Pendant la relecture dans `outil_validation.html`, beaucoup de messages semblent en double : un
même bâtiment reçoit deux messages très proches issus du même document.

Cas étudié : **Dorlisheim** (`71be1d2fe04f069bd2638676c5c499ec`), fichier
`output/067_horsEurometropole/etape5_export_syntheses_20261007_175332.csv`.

- Synthèse **g175** = fusion des occurrences `12_67101` et `7_67101`, classées `administrative`
  (donc appliquées à **toute la commune**).
- Synthèse **g310** = occurrence `3_67101`, classée `zone_specifique`.
- Un bâtiment de la zone de g310 reçoit donc les deux messages.

## Ce que dit le règlement (PDF scanné, pages lues à l'image)

| Occurrence | Page PDF | Zone réelle | Contenu | Portée enregistrée |
|---|---|---|---|---|
| `3_67101` | 17 | UA (Art. 2-UA, en-tête de zone p.16 non relu) | artisanat, industrie, commerce, tertiaire sans nuisances incompatibles avec le caractère de la zone | `zone_specifique` |
| `7_67101` | 35 | **UC** (Art. 2-UC) | activités économiques sans nuisances incompatibles avec le caractère résidentiel + alinéa distinct sur les constructions **agricoles** | `administrative` ❌ |
| `12_67101` | 88 | **1AU** (Art. 2.3) | activités admises **dans une opération d'ensemble** à vocation résidentielle | `administrative` ❌ |

**Conclusion** : il ne faut pas fusionner ces messages, mais rattacher chaque occurrence à sa zone (UA,
UC, 1AU). Le doublon disparaît alors de lui-même.

⚠️ Cela remet en cause la **décision du 2026-09-29** (fusion `12_67101` + `7_67101`) : elle
reposait sur l'idée que les deux occurrences portaient sur le même périmètre. En réalité, la synthèse
g175 annonce à toute la commune une règle agricole propre à la zone UC.

## Cause probable

Dans ce cas, l'étape 2 classe en `administrative` des règles qui figurent dans l'article d'une zone
précise, surtout quand l'OCR rend l'en-tête de zone illisible. La feuille de route signalait déjà ces
faux positifs en Phase 1.

## Les 15 documents concernés

Ce sont les documents qui mélangent `administrative` et `zone_specifique` (source :
`etape4_067.gpkg` ; les communes sans document d'urbanisme, à `id_gpu` vide, sont exclues). Seul
Dorlisheim a été vérifié dans le PDF : le classement des autres documents est une
**interprétation à confirmer**.

### A. Portée `administrative` probablement fausse — priorité 1

| Commune | id_gpu | Géométries admin suspectes (page) | Indice |
|---|---|---|---|
| Dorlisheim | `71be1d2fe04f069bd2638676c5c499ec` | g175 (p.88), g176 (p.35) | ✅ vérifié : 1AU et UC |
| Heiligenberg | `5edf63b8118051e81a650e2a279541fd` | g195-199 (p.16), g193 (p.31), g194 (p.35) | g195-199 portent zone = Ur/Uh/Uhe/Ue/Ut mais sont classées admin |
| Kurtzenhouse | `d9f1902e01d10dfb16b87041193ba1c5` | g215 (p.25), g216 (p.30), g217 (p.35) | zones A, AU ; Art. AU1/AU5 |
| Lauterbourg | `8ae18694b57b473bb4461d1d66380731` | g221 (p.21), g219 (p.30), g220 (p.35) | zones U, AU, A |
| Munchhausen | `2e782afabec0a8c1c78ec25955bff2c3` | g297 (p.21), g298 (p.27), g299 (p.31), g300 (p.35) | zones U, 1AUh, A1, N |
| Scheibenhard | `fc6bee104103d89651e5a0410d49cd49` | g262 (p.21), g260 (p.29), g261 (p.41) | ZONE U, 1AUh, ZONE N |
| Weitbruch | `d699ee12b61bc58eb849e550fac799eb` | g275 (p.25) | 1AUe ; Art. au2 |

Les cinq documents après Dorlisheim semblent partager le même modèle de règlement : mise en page en
colonnes, avec un encadré « ÉMERGENCES ACOUSTIQUES » sur les pompes à chaleur et climatiseurs répété
dans chaque zone. L'OCR mélange les colonnes. La même règle ressort alors une fois en `admin` et une
fois par zone. Il faut choisir **une** des deux logiques par document :
- soit **une seule occurrence admin**, si la règle est identique dans toutes les zones ;
- soit **une occurrence par zone**, en supprimant l'occurrence admin.

### B. Incohérence à trancher — priorité 2

| Commune | id_gpu | Observation |
|---|---|---|
| Lupstein | `ad6748bd26d5270fed09bf7e8c200b8d` | p.6 : agricole = admin (g224), « établissements de toute nature » = UA (g353) |
| Printzheim | `5efb9b5e06dc686b9c2a2ac17632ff2d` | p.6 : les mêmes deux règles, **portées inversées** (établissements = admin g249, agricole = UA g357) |

Le texte semble identique dans les deux documents, donc au moins l'un des deux est mal classé.

### C. Portée `administrative` probablement légitime — priorité 3

| Commune | id_gpu | Occurrence admin | Remarque |
|---|---|---|---|
| Batzendorf + 35 communes (PLUi) | `171518c6d5441a4ad41c30cf32dbe4ca` | g282 PAC/clim, Art. 6, p.25 | probablement des dispositions générales |
| Dalhunden + 16 communes (PLUi) | `b5ae1da72ed7f5ecf4aa179df33e1076` | g288 PAC/clim, Art. 3, p.25 | idem |
| Duppigheim | `1413f9ce036f2b048fe492e3f46becd4` | g177 / g178, p.2 (PADD) | **g177 et g178 sont un doublon exact** |
| Niedernai | `712f0fae0fee0e49bf7d0bbd7e3d0b47` | g238, p.6 (PADD) | — |
| Scherwiller | `b41a7e70e8fbeb0240065dde230a8ce6` | g263, p.7 (PADD) | — |
| Colroy-la-Roche | `7ba5c245843c439061a106418e9f4c9b` | g169 PAC en façade, Art. 11, p.17 | ⚠️ l'article 11 est souvent propre à une zone : à vérifier |

(Weitbruch g273 « toutes les zones U, AU, A, N » et g274 PADD semblent également légitimes.)

## Plan pour la suite

1. **Suspendre la relecture étape 5 de ces 15 documents** : les corrections remonteront à l'étape 4
   et régénéreront leurs synthèses, donc une relecture faite maintenant serait perdue.
2. Vérifier les groupes A puis B sur le PDF, page par page (téléchargement GPU + rendu des pages en
   image, puisque ces PDF sont scannés), et fixer la bonne portée de chaque occurrence.
   Commencer par **Heiligenberg** (le cas le plus nombreux).
3. Avant de corriger : **regarder comment l'étape 4 gère un changement de portée** et l'annulation
   d'une fusion (`fusionne_avec_id_occurrence`). Ce point n'est pas encore vérifié.
4. Annuler la fusion `12_67101` / `7_67101` de Dorlisheim et revoir la décision du 2026-09-29 dans la
   feuille de route.
5. Plus tard : renforcer l'étape 2 pour que la présence d'un en-tête ou d'un article de zone
   (« Art. 2-UC », « au5 »…) empêche le classement en `administrative`.
