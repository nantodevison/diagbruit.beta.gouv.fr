# CLAUDE.md — Veille bruit & santé

Consignes de travail pour ce sous-projet. Le cadrage complet est dans
`docs/plan-veille-bruit-sante-diagbruit.md`, le détail de chaque étape dans
`docs/etape-N-*.md`, et le **schéma validé du workflow** (du scan à la mise à
disposition des favoris) dans `docs/workflow-veille.md` — à tenir à jour quand
le circuit change.

## Objectif

Fournir un résumé des publications scientifiques récentes sur l'impact du bruit
sur la santé (populations européennes). Ce résumé doit permettre :
1. **d'identifier les contenus réellement nouveaux** — une nouvelle étude ou un
   nouveau rapport, et non une reprise (communiqué, article de presse, relais)
   d'une publication déjà connue ou ancienne ;
2. **de faciliter la compréhension** de ces articles scientifiques par un
   lecteur non spécialiste.

Toute évolution du pipeline (prompts, filtres, dédoublonnage) se juge à l'aune
de ces deux critères.

**Ce qui fait une publication importante** (critères de l'utilisateur, tirés de
sa relecture de la base — voir `analyse_relecture/analyse-2026-09-24.md`) :
- une conclusion claire, qui démontre ou infirme un impact du bruit sur la santé ;
- une source fiable et reconnue ;
- des explications (méthode, données) qui étayent cette conclusion.

Les **textes de référence anciens** (lignes directrices OMS, avis ANSES…) sont
conservés : ce sont des jalons qui contextualisent les nouveautés. Ils doivent
être distingués des nouveautés, pas écartés.

## Architecture

Projet **autonome** : aucune dépendance avec Dagster, dbt, FastAPI ni PostGIS.
Il lit et écrit uniquement dans une base Notion « Études », seule mémoire
persistante du projet (aucun fichier d'état local entre deux runs).

```
main.py  (point d'entrée unique, un run hebdomadaire)
  ├─ calcule la date de départ = date_ajout la plus récente dans Notion
  │    (ou aujourd'hui − 10 ans si la base est vide)
  ├─ étape 2 — etape2_recherche_extraction/
  │    recherche_apis.py   OpenAlex + Europe PMC (sans clé)
  │    recherche_web.py    outil web_search d'Anthropic, limité à
  │                        config/domains_whitelist.yaml
  │    extraction.py       1 appel Claude par source → EtudeExtraite (Pydantic)
  │    dedoublonnage.py    doublons internes au run (DOI puis titre ≈ 90 %)
  │    qualification.py    règles Python → priorite (Haute / A examiner /
  │                        Faible), nouveaute
  └─ étape 3 — etape3_integration_notion/
       etat_existant.py / dedoublonnage_existant.py  doublons contre Notion
       verification_url.py  pose url_not_real (ne rejette jamais une étude)
       ecriture.py          création des fiches
```

- `etape1_base_notion/` : création **ponctuelle** de la base, jamais appelée
  par `main.py`. Les listes d'options (`OPTIONS_DOMAINE_SANTE`, etc.) y sont
  définies et réutilisées par `extraction.py` : les modifier à un seul endroit.
- `notion_utils.py` : résout `NOTION_DATABASE_ID` → `data_source_id` (API
  Notion ≥ 2025-09-03 : `data_sources.query`, plus de `databases.query`).
- `verifier_urls_existantes.py` : script ponctuel de revérification des URLs
  des fiches existantes, sans appel Anthropic.
- `analyse_relecture/` : outils d'analyse de la base relue à la main
  (`exporter_base.py` et `recuperer_contenus.py` gratuits,
  `tester_qualification.py` payant, `--estimer` d'abord). Sorties dans
  `analyse_relecture/export/`, ignoré par Git.

## Commandes

```bash
cd veille-bruit-sante
python -m venv .venv          # environnement dédié : ne pas installer en global
.venv\Scripts\activate        # (Windows) — source .venv/bin/activate ailleurs
pip install -r requirements.txt
cp .env.example .env          # ANTHROPIC_API_KEY, NOTION_API_KEY, NOTION_DATABASE_ID

python main.py                               # run complet (étapes 2 + 3)
python verifier_urls_existantes.py           # revérifie les URLs en base
python -m etape1_base_notion.creer_base_notion <id_page_parente>   # une seule fois
```

Pas de tests automatisés pour l'instant. Automatisation :
`.github/workflows/veille-bruit-sante.yml` (lundi 6 h UTC, déclenchement manuel
possible, et à chaque push sur `main` touchant ce dossier).

## Règles de travail

- **Coût** : les appels Anthropic sont payants. Ne pas lancer `main.py` sans
  accord explicite ; ne jamais ajouter d'appel LLM là où une requête HTTP ou
  une règle simple suffit.
- **Ne jamais lire `.env`** (clés API).
- **Prompts datés** : toujours injecter les dates en toutes lettres, jamais de
  formulation relative (« depuis la dernière fois ») — un appel API n'a pas de
  mémoire d'un run à l'autre.
- **Cache de prompt** : `PROMPT_SYSTEME` (extraction.py) doit rester fixe et
  au-dessus de 1024 tokens pour que le cache s'active ; le log
  `cache_read_input_tokens` sert à le vérifier.
- **Deux dédoublonnages distincts** (interne au run / contre Notion) partagent
  les fonctions de normalisation de `dedoublonnage.py` : ne pas les dupliquer.
- **Un échec isolé n'interrompt pas le run** (écriture d'une fiche, URL morte).
- **Rien n'est écarté silencieusement** : toute exclusion (échec, hors
  périmètre, doublon) est journalisée avec le titre et la raison ; un contenu
  trop pauvre est écrit avec `a_verifier` plutôt qu'exclu.
- **Rappel avant précision** : l'utilisateur préfère trier plus de documents
  que manquer un favori potentiel. La `priorite` informe, la case `favori`
  (manuelle) décide.
- Toute décision de conception est consignée dans le
  `docs/etape-N-conception-technique.md` concerné (format « Décision N — …
  **Pourquoi :** … »).

## Points ouverts connus

- Pas encore de run complet réussi de bout en bout (voir README, « Statut »).
- Format exact des résultats `web_search` à confirmer sur un vrai appel.
- Exemples du `PROMPT_SYSTEME` marqués BROUILLON, à relire.
- Pas d'option `--limit` pour tester sur quelques études.
- Colonnes de qualification ajoutées à la base Notion le 24/09/2026. Pour toute
  autre base (test, recréation) : `creer_base_notion --ajouter-qualification
  <data_source_id>`, sinon toutes les écritures échouent.
- Coût de l'extraction : environ 1 à 2 centimes par étude, dont à peu près la
  moitié due à la réflexion (thinking) de Sonnet 5, active par défaut.
- Canal web : toutes les sources d'un run reçoivent le même texte de contexte
  (la synthèse globale de `web_search`), d'où des résumés pauvres.
