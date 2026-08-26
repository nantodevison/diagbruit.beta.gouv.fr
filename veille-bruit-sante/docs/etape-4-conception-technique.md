# Étape 4 — Conception technique : automatisation (GitHub Actions)

*Document de cadrage technique, faisant suite à `etape-4-automatisation-diagbruit.md` et à `etape-3-conception-technique.md`. Dernière étape du plan initial.*

## Décision 1 — Un seul fichier de workflow, filtré sur `veille-bruit-sante/`

`.github/workflows/veille-bruit-sante.yml`, avec un filtre `paths` restreint au dossier du projet, sur le même principe que les workflows de déploiement existants (`.github/workflows/deploy-*.yml`, filtrés par composant, voir `CLAUDE.md` racine) — même si ici il ne s'agit pas d'un déploiement mais d'une exécution planifiée.

```yaml
name: Veille bruit & santé

on:
  schedule:
    - cron: "0 6 * * 1"    # lundi 08h heure de Paris (UTC+2 en été) — voir "Point de vigilance horaire"
  workflow_dispatch: {}
  push:
    branches: [main]
    paths:
      - "veille-bruit-sante/**"
      - ".github/workflows/veille-bruit-sante.yml"

jobs:
  veille:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: veille-bruit-sante
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - run: pip install -r requirements.txt

      - run: python main.py
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          NOTION_API_KEY: ${{ secrets.NOTION_API_KEY }}
          NOTION_DATABASE_ID: ${{ secrets.NOTION_DATABASE_ID }}
```

**Pourquoi un déclencheur `push` en plus des deux prévus par `etape-4-automatisation-diagbruit.md` :** utile en phase de mise au point pour vérifier que le workflow lui-même (pas seulement le script) s'exécute sans erreur de syntaxe ou de dépendance dès qu'on modifie `veille-bruit-sante/`, sans attendre l'échéance hebdomadaire ni déclencher manuellement à chaque fois. Il ne se substitue pas à `workflow_dispatch`, gardé pour les tests ciblés une fois le projet stabilisé.

## Point de vigilance horaire

Le cron GitHub Actions s'exprime en UTC. `0 6 * * 1` (lundi 6h UTC) correspond à 8h heure de Paris en été (UTC+2) et 7h en hiver (UTC+1) — décalage à accepter (GitHub Actions ne propose pas de cron en heure locale) plutôt qu'à corriger : une variation d'une heure sur l'horaire d'un run hebdomadaire de veille n'a aucune conséquence pratique. Horaire choisi (lundi matin) arbitraire à ce stade, à ajuster librement selon l'usage réel.

## Décision 2 — Secrets : trois clés, jamais commitées

| Secret GitHub | Origine | Utilisé par |
|---|---|---|
| `ANTHROPIC_API_KEY` | Console Anthropic | `web_search` et extraction structurée (étape 2) |
| `NOTION_API_KEY` | Intégration interne Notion (`notion.so/my-integrations`) | Lecture/écriture de la base "Études" (étape 3) |
| `NOTION_DATABASE_ID` | URL de la base "Études" une fois créée (Décision 4, `etape-1-conception-technique.md`) | Étape 3, et le script ponctuel de setup |

Enregistrés dans `Settings > Secrets and variables > Actions` du dépôt, référencés par nom (`${{ secrets.NOM }}`) dans le workflow — jamais affichés en clair dans les journaux d'exécution, y compris en cas d'erreur (GitHub masque automatiquement toute valeur de secret qui apparaîtrait dans une sortie). `veille-bruit-sante/.env.example` documente ces trois variables pour l'exécution locale (`.env` réel exclu du dépôt via `.gitignore`), sans valeur réelle.

**Pourquoi `NOTION_DATABASE_ID` en secret plutôt qu'en clair dans le code :** pas une donnée sensible en soi, mais un identifiant propre à l'environnement (base de test vs base réelle) — le traiter comme les clés API évite de le committer en dur et permet de pointer le workflow vers une base différente sans modifier le code, simplement en changeant le secret.

## Décision 3 — Déroulé d'exécution : conforme au cadrage, rien d'additionnel

`actions/checkout` puis `actions/setup-python` puis `pip install -r requirements.txt` puis `python main.py` — aucune étape de build, de test automatisé ou de linting n'est ajoutée à ce stade : ce projet n'a pas de suite de tests (POC de veille, pas de composant produit, voir posture de `etape-1-conception-technique.md`), contrairement au pipeline CI du produit (`.github/workflows/ci.yml`, qui fait tourner `pytest` sur `fastapi/`). À reconsidérer seulement si le projet est un jour repris comme composant produit à part entière.

## Décision 4 — Échec du run : visible, jamais silencieux

Un `print`/log d'erreur (étapes 2 et 3, voir leurs documents de conception technique respectifs) apparaît dans les journaux d'exécution du run GitHub Actions, consultable dans l'onglet `Actions` du dépôt. Si `main.py` lève une exception non rattrapée (cas non prévu, hors des échecs isolés déjà gérés), le run se termine en échec et GitHub Actions envoie une notification par email aux personnes ayant accès au dépôt (comportement par défaut, aucune configuration additionnelle requise) — suffisant pour un run hebdomadaire à faible enjeu, pas besoin d'une intégration Slack ou équivalente à ce stade.

## Ce qu'il reste à faire, hors du périmètre de conception

- Créer l'intégration Notion (`notion.so/my-integrations`) et la partager avec la base "Études" (Décision 4, `etape-1-conception-technique.md`).
- Générer la clé API Anthropic et enregistrer les trois secrets dans les paramètres du dépôt GitHub.
- Écrire effectivement `main.py` et les modules des étapes 2 et 3, les tester en local (`python main.py`, avec `.env`) avant le premier run planifié.

## Prochaine étape

Aucune — dernière étape du plan de conception. La suite est l'écriture du code lui-même, module par module, dans Claude Code.
