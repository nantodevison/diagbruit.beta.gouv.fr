# Étape 2 — Recherche hebdomadaire et extraction structurée

*Document de cadrage détaillé de l'étape 2 du plan de veille bruit & santé de diagBruit (voir `plan-veille-bruit-sante-diagbruit.md`). Suite de `etape-1-base-notion-diagbruit.md`.*

**Entrée** : aucune donnée en entrée depuis une étape précédente — cette étape s'exécute chaque semaine et déclenche elle-même sa recherche. Elle a cependant besoin de connaître la date de la dernière recherche effectuée (voir Phase 1).

## Principe

Un appel API automatisé n'a pas de mémoire d'une exécution à l'autre : contrairement à une conversation, il ne peut pas comprendre une instruction du type "depuis ma dernière demande". Le script doit donc **calculer et injecter explicitement une date** dans le prompt de recherche avant chaque envoi. Deux cas :
- **Premier run** : recherche sur les 10 dernières années.
- **Runs suivants** : recherche depuis la date de la précédente exécution (calculée par le script, par exemple à partir de la date d'ajout la plus récente présente dans la base Notion).

## Phase 1 — Recherche, sur deux canaux complémentaires

Un seul canal de recherche ne suffit pas à l'exigence d'exhaustivité et de fiabilité des sources, les deux canaux ne couvrant pas le même type de contenu :

| Canal | Couvre | Mécanisme de fiabilité |
|---|---|---|
| API scientifiques structurées (OpenAlex, Europe PMC) | Articles publiés dans des revues à comité de lecture, avec DOI | Interrogation directe et structurée (date, pays/institution) — pas d'intermédiaire LLM pour la découverte |
| `web_search` (outil serveur de l'API Anthropic) | Littérature grise institutionnelle (rapports OMS, EEA, communiqués Inserm...), souvent sans DOI et non indexée dans les bases académiques | Restreint à une liste de domaines autorisés (`allowed_domains`), voir fichier de configuration `domains_whitelist.yaml` — une contrainte dure, pas une simple préférence donnée au modèle |

## Phase 2 — Extraction structurée

Pour chaque étude retenue sur l'un ou l'autre canal, extraction des champs suivants — repris à l'identique des noms de colonnes de la base Notion (`etape-1-base-notion-diagbruit.md`), pour que l'étape 3 n'ait aucun mapping intermédiaire à faire :

`titre`, `auteurs`, `annee`, `revue`, `organisme`, `doi_url`, `domaine_sante`, `source_bruit`, `resume`, `resultat_cle`.

Le `resume` (2-3 phrases) et le `resultat_cle` sont rédigés par le modèle à partir du contenu trouvé, pas recopiés tels quels d'une source.

## Phase 3 — Dédoublonnage interne au run

Les deux canaux peuvent remonter la même étude (par exemple un article académique également relayé par un communiqué institutionnel). Avant de transmettre la liste finale à l'étape 3, dédoublonnage en deux temps :
1. **Comparaison stricte par `doi_url`** (normalisé : minuscules, sans préfixe `https://doi.org/`) — fiable quand les deux résultats en portent un.
2. **Comparaison de secours par titre** (normalisé : minuscules, ponctuation retirée, comparaison de similarité) — pour les cas sans DOI des deux côtés (ex. un rapport institutionnel).

Ce dédoublonnage est distinct du dédoublonnage contre l'existant, qui a lieu à l'étape 3 (comparaison avec les fiches déjà présentes dans la base Notion, pas seulement entre les résultats d'un même run).

## Prochaine étape

Étape 3 — intégration Notion : dédoublonnage contre les fiches déjà existantes dans la base, puis écriture des nouvelles fiches selon le contrat de données de l'étape 1.
