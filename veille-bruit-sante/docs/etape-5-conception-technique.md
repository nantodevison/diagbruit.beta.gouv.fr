# Étape 5 — Conception technique : artefact de synthèse

*Rédigé et validé le 17/11/2026 par Martin Schoreisz. Fait suite au cadrage `etape-5-artefact-synthese-diagbruit.md` (validé le 30/09/2026) et au socle `socle/etat-connaissances.yaml` (v1.1, révisé le 17/11/2026). Les arbitrages faits lors de la validation sont résumés en fin de document.*

## Vue d'ensemble

```
lundi 6 h UTC (cron hebdomadaire)
  ├─ semaine paire  : python main.py            (veille payante, Décision 5)
  └─ chaque semaine : python -m etape5_artefact.generer_page   (gratuit, Décision 6)
                        lit socle/etat-connaissances.yaml + base Notion
                        → site/index.html → GitHub Pages du fork
```

Ordre de réalisation proposé (chaque lot est utile seul) :
1. nettoyage de `domaine_sante` (Décisions 1 et 2) — prérequis du cadrage ;
2. colonnes `verdict` et `piste_actualite` (Décisions 3 et 4) ;
3. rythme de 15 jours et retrait du déclencheur `push` (Décision 5) ;
4. script de génération de la page (Décision 6) ;
5. publication : fusion dans le `main` du fork, secrets, Pages (Décision 7, actions manuelles).

## Décision 1 — `domaine_sante` reprend la liste des effets du socle

Constat (export du 17/11/2026, 104 fiches) :
- la colonne contient **105 étiquettes différentes**, héritées des premiers runs où le LLM écrivait librement ; toutes sont déjà classées dans le socle (`alias_domaine_sante`, `alias_non_rattaches`) — aucune n'est inconnue ;
- la liste fermée utilisée par l'extraction depuis (`OPTIONS_DOMAINE_SANTE` : Cardiovasculaire, Sante mentale, Cognition, Metabolique, Sommeil, Enfant) **ne correspond pas au socle** : la **gêne**, effet démontré, n'y figure pas ; « Cognition » mêle apprentissages de l'enfant et démence ; « Enfant » désigne un public, pas un effet.

Nouvelle liste fermée, une option par entrée du socle :

| Option Notion | Entrée du socle | Rôle |
|---|---|---|
| `Cardiovasculaire` | effet `cardiovasculaire` | effet |
| `Sommeil` | effet `sommeil` | effet |
| `Gene` | effet `gene` | effet |
| `Enfant` | effet `apprentissage_enfant` | thème enfants : apprentissages, et tout autre effet étudié chez l'enfant (cumulable) |
| `Metabolique` | effet `metabolique` | effet |
| `Sante mentale` | effet `sante_mentale` | effet |
| `Auditif` | encadré `auditif` | encadré « À ne pas confondre » |
| `Cancer` | piste `cancer` | piste émergente |
| `Demence` | piste `demence` | piste émergente |
| `Grossesse` | thème hors socle `grossesse` | conservé, non affiché |
| `General` | — | document d'ensemble, sans effet précis (18 fiches) |

Les noms restent sans accents, comme les autres options du projet. La correspondance option ↔ entrée du socle est écrite **dans le socle** (champ `etiquette_notion` sur chaque effet, piste et thème) ; `OPTIONS_DOMAINE_SANTE` reste défini dans `creer_base_notion.py` (règle du projet : un seul endroit pour les options), et le script de génération **vérifie** au démarrage que les deux concordent, sinon il s'arrête avec un message clair.

**Pourquoi :** le cadrage demande que les options soient « alignées sur la liste des effets du socle » pour que le script fasse les comptes par effet. `General` évite de forcer un effet sur les rapports d'ensemble (AEE, lignes directrices OMS) ou de les laisser sans étiquette, ce qui les rendrait indiscernables d'un oubli. Une seule option `Enfant` regroupe l'effet « apprentissages » et le public enfants (décision du 17/11/2026) : c'est plus simple à trier, l'option existe déjà dans l'extraction, et le futur regard « Enfants » s'appuiera dessus.

**Conséquence acceptée :** le compte de nouveautés du bloc « Apprentissages chez l'enfant » inclut aussi les études sur d'autres effets chez l'enfant (par exemple la cohorte ELFE, santé mentale). Ces fiches portent aussi l'option de leur effet, donc elles comptent aussi dans ce bloc-là.

**Conséquences :**
- le `PROMPT_SYSTEME` change (définitions de `domaine_sante`) : le cache est invalidé une fois, puis se reconstitue ;
- les fiches déjà en base passent par le nettoyage (Décision 2) ;
- les anciennes options devenues inutiles sont retirées du schéma Notion, **après** le nettoyage des fiches.

## Décision 2 — Nettoyage des fiches existantes par script, sans LLM

Script `analyse_relecture/nettoyer_domaine_sante.py` :
- lit le socle et la base Notion ;
- pour chaque fiche, traduit chaque ancienne étiquette en option de la Décision 1 grâce aux alias du socle ; une étiquette « non rattachée » ne donne rien ; une fiche qui n'a plus aucun effet reçoit `General` ;
- ajoute `Enfant`, en plus de l'effet, quand une ancienne étiquette porte sur les enfants (enfant, infantile, scolaire, nouveau-nés, néonatal) ;
- conserve telle quelle, et signale, toute étiquette inconnue du socle (rien n'est retiré sans trace) ;
- **simulation par défaut** : écrit le tableau « avant → après » dans `analyse_relecture/export/nettoyage_domaine_sante.csv`, sans rien modifier ; `--appliquer` écrit dans Notion, uniquement la colonne `domaine_sante`, uniquement sur les fiches qui changent ;
- l'export CSV du jour sert de sauvegarde (anciennes étiquettes conservées hors de Notion).

**Simulation du 17/11/2026** : 104 fiches lues, 97 à modifier, aucune étiquette inconnue. Fiches par option après nettoyage : Cardiovasculaire 61, Sommeil 35, Sante mentale 35, Gene 27, Enfant 20 (17 sur les apprentissages, 3 autres dont la cohorte ELFE), General 18, Metabolique 10, Auditif 5, Cancer 2, Grossesse 2. Démence : 0 fiche, la piste ne s'appuie que sur le rapport AEE (étiqueté avec les autres effets).

**Appliqué le 17/11/2026** : 97 fiches modifiées, vérification à 0 fiche restante ; schéma réduit de 112 à 10 options. Deux pièges de l'API Notion rencontrés au passage :
- une liste d'options envoyée par `data_sources.update` est limitée à **100 éléments** ;
- l'API **ne renomme pas** une option (le changement de nom est ignoré sans erreur), et un nom d'option est reconnu **sans tenir compte de la casse** : écrire `Cancer` réutilisait l'ancienne option `cancer`. Correction : noter les fiches concernées, retirer l'option du schéma, puis réécrire ces fiches.

**Pourquoi :** les alias sont déjà validés dans le socle ; une règle simple suffit, un appel LLM n'apporterait rien (règle « Coût » du projet). La simulation permet de relire le résultat fiche par fiche avant d'écrire.

## Décision 3 — Colonne `verdict`, proposée par le LLM à l'extraction

- Colonne Notion `verdict` (select) : `Confirme`, `Nuance`, `Contredit`, `Sujet absent du socle`.
- Nouveau champ `verdict: Optional[Verdict]` dans `EtudeExtraite`, **sans valeur par défaut** (règle « Schema is too complex »). On passe de 3 à 4 champs optionnels : marge confortable.
- Le LLM juge le document par rapport à un **résumé du socle** injecté dans `PROMPT_SYSTEME` : pour chaque effet, son nom, son niveau de preuve, son « en bref » et ses chiffres clés. Ce résumé est **généré depuis le YAML** au chargement du module (quelques centaines de mots, pas les 700 lignes du fichier). Il ne change qu'à une révision du socle : le cache de prompt reste efficace au sein d'un run.
- **Pas de rattrapage** sur les 104 fiches existantes : elles ont servi à rédiger le socle, un verdict n'y aurait pas de sens. La page compte les documents nouveaux depuis `date_revision` du socle, qui en sont tous pourvus.
- Le verdict est **validé pendant le tri** dans Notion, comme `priorite` : il informe, l'utilisateur corrige.

**Pourquoi :** c'est le seul appel LLM supplémentaire prévu par le cadrage (section « Coût »), et il se loge dans l'appel d'extraction existant (aucun appel de plus par étude). Coût estimé : le prompt système grossit d'environ 1 500 tokens, lus depuis le cache à 10 % du prix après le premier appel — négligeable devant le coût de la réflexion (thinking).

## Décision 4 — Colonne `piste_actualite`, case manuelle

Case à cocher, jamais écrite par le script. Affichée dans la section « Retenus » de la page. Ajoutée avec `verdict` par une nouvelle migration `creer_base_notion --ajouter-artefact <data_source_id>`, sur le modèle de `--ajouter-qualification`.

**Pourquoi :** même principe que `favori` : la décision revient au responsable du projet.

## Décision 5 — Rythme de 15 jours : semaine ISO paire, et plus de déclencheur `push`

- Le cron reste hebdomadaire (`0 6 * * 1`) : GitHub ne sait pas planifier « tous les 15 jours ».
- Une étape du workflow calcule le numéro de semaine ISO (`date +%V`) ; `main.py` ne tourne que **les semaines paires**. Un lancement manuel (`workflow_dispatch`) tourne toujours.
- La génération de la page (Décision 6), gratuite, tourne **chaque semaine**, pour que les « Retenus » cochés entre deux runs apparaissent sans attendre.
- Le déclencheur `push` sur `main` est **retiré**.

**Pourquoi :** la parité de semaine est déterministe et ne demande aucun état (le projet n'a pas d'état local entre deux runs). L'autre piste, « ne rien faire si le dernier run date de moins de 14 jours » d'après `date_ajout` dans Notion, échoue quand un run ne trouve rien : la date n'avance pas et le run repartirait la semaine suivante. Les années à 53 semaines donnent une fois un écart de 3 semaines (semaine 53 impaire, puis semaine 1 impaire) : sans conséquence, la date de départ du run est calculée depuis Notion, aucune période n'est perdue. Le déclencheur `push` servait à la mise au point (`etape-4-conception-technique.md`, Décision 1) ; une fois la veille sur `main`, il lancerait un run payant à chaque fusion — c'est le point laissé ouvert dans la feuille de route.

## Décision 6 — Script de génération de la page

Module `etape5_artefact/generer_page.py`, lancé par `python -m etape5_artefact.generer_page` :
1. lit le socle ; **refuse de générer** si `statut` vaut `brouillon` (règle du socle : rien n'est publié tant qu'il n'est pas validé) ;
2. vérifie la concordance des options `domaine_sante` (Décision 1) ;
3. lit la base Notion (lecture seule) : fiches `favori` pour « Retenus », comptes par effet des documents ajoutés depuis `date_revision` (dont nombre de « Contredit » et « Sujet absent du socle ») ;
4. remplit un gabarit HTML (`etape5_artefact/gabarit.html`, avec **Jinja2**, seule dépendance ajoutée) et écrit `site/index.html` (dossier ignoré par Git) ;
5. la page contient `<meta name="robots" content="noindex">`, la date de la dernière récupération et celle de la prochaine, la mention « synthèse de veille, pas une expertise sanitaire » ; chaque document renvoie vers sa fiche Notion.

Ce que la page affiche (repris du cadrage) : encadré « À ne pas confondre » en tête, chiffres européens mis en avant, un bloc par effet (niveau de preuve, en bref, chiffres `mise_en_avant`, détail repliable, références, nombre de nouveautés), pistes émergentes, glossaire, puis « Retenus ». Le **regard transversal « Enfants »** (validé dans le cadrage le 02/10/2026) est **reporté à la version 2** de la page (décision du 17/11/2026, suivi dans `FEUILLE_DE_ROUTE.md`) : il s'appuiera sur l'option `Enfant`. Les chiffres dont `verification` vaut `a_faire` ne sont **pas affichés** (aujourd'hui : un seul appui de l'encadré auditif).

**Pourquoi :** une page statique se publie sans serveur, gratuitement, et Jinja2 sépare la mise en page (HTML) de la logique (Python), ce qui la rend plus facile à relire et à retoucher qu'un HTML construit par concaténation de chaînes. Aucun appel LLM : tout le texte vient du socle validé ou des fiches relues.

## Décision 7 — Publication sur GitHub Pages du fork (actions manuelles)

Dans le workflow, après la génération : `actions/upload-pages-artifact` puis `actions/deploy-pages` (permissions `pages: write`, `id-token: write`). À faire à la main, une fois, sur `nantodevison/diagbruit.beta.gouv.fr` :
- fusionner la branche dans `main` du fork ;
- enregistrer les 3 secrets (ANTHROPIC_API_KEY, NOTION_API_KEY, NOTION_DATABASE_ID) ;
- activer les tâches planifiées (onglet Actions, désactivées par défaut sur un fork) ;
- Settings > Pages > Source : « GitHub Actions ».

**Pourquoi :** déjà décidé dans le cadrage (« Support », 30/09/2026) ; seule la mécanique est précisée ici.

## Arbitrages de la validation (17/11/2026)

1. **Options** : noms sans accents validés ; `Apprentissages enfant` et `Enfant` fusionnés en une seule option `Enfant` (thème enfants).
2. **`General`** retenu pour les documents d'ensemble.
3. **`Enfant`** reste une option de `domaine_sante`, pas une colonne séparée.
4. **Déclencheur `push`** retiré.
5. **Jinja2** retenu.
6. **Regard « Enfants »** reporté à la version 2 de la page.
