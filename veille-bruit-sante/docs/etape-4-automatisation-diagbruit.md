# Étape 4 — Automatisation (GitHub Actions)

*Document de cadrage détaillé de l'étape 4 du plan de veille bruit & santé de diagBruit (voir `plan-veille-bruit-sante-diagbruit.md`). Suite de `etape-3-integration-notion-diagbruit.md`. Dernière étape du plan initial — la suite (écriture effective du fichier de workflow) relève de la conception technique, à mener dans Claude Code.*

**Entrée** : le script des étapes 2 et 3 (recherche, extraction, intégration Notion), une fois fonctionnel.

## Principe

GitHub Actions exécute le script sur une machine temporaire fournie par GitHub, recréée à chaque exécution puis détruite — rien n'y persiste d'une semaine à l'autre. Cette caractéristique est cohérente avec une décision déjà prise à l'étape 2 : la date de la dernière recherche n'est jamais stockée localement par le script, elle est recalculée à chaque run à partir de la base Notion elle-même, seule mémoire persistante du projet.

## Déclenchement

Deux mécanismes, tous deux nécessaires :
- **Planification hebdomadaire** (`schedule`, syntaxe cron) — le déclenchement automatique recherché depuis le départ.
- **Déclenchement manuel** (`workflow_dispatch`) — un bouton "Run workflow" dans l'interface GitHub, pour tester le script à la demande pendant sa mise au point, sans attendre l'échéance hebdomadaire.

Point de vigilance : l'heure d'un cron GitHub Actions est exprimée en UTC, pas en heure française — à convertir au moment d'écrire l'horaire exact (décalage de 1h en hiver, 2h en été).

## Secrets

Deux clés sensibles à fournir au script sans jamais les écrire en clair dans le dépôt : la clé API Anthropic et la clé d'intégration Notion (potentiellement aussi l'identifiant de la base Notion, selon comment le script y accède). Elles sont enregistrées dans les paramètres du dépôt GitHub (`Settings > Secrets and variables > Actions`) et référencées par nom depuis le fichier de workflow, sans jamais apparaître en clair, y compris dans les journaux d'exécution.

## Déroulé d'une exécution

Récupération du code du dépôt, installation de Python et des dépendances du projet, puis exécution du script (étapes 2 et 3 enchaînées). Les échecs isolés éventuels sont visibles directement dans les journaux d'exécution de GitHub Actions, conformément à la politique de gestion des erreurs retenue à l'étape 3.

## Coût

Gratuit pour ce projet : GitHub offre 2000 minutes d'exécution par mois pour un dépôt privé ; un run hebdomadaire de quelques minutes en consomme une fraction négligeable.

## Suite

La rédaction effective du fichier de workflow (`.github/workflows/*.yml`) et son paramétrage précis (horaire exact, nom des secrets, commandes d'installation) sont à mener dans Claude Code, une fois le script des étapes 2 et 3 écrit et testé localement.
