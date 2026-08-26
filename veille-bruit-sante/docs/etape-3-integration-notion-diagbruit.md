# Étape 3 — Intégration Notion

*Document de cadrage détaillé de l'étape 3 du plan de veille bruit & santé de diagBruit (voir `plan-veille-bruit-sante-diagbruit.md`). Suite de `etape-2-recherche-extraction-diagbruit.md`.*

**Entrée** : la liste des études trouvées à l'étape 2, déjà dédoublonnée en interne (fusion des deux canaux de recherche), au format structuré défini par le contrat de données de l'étape 1 (`titre`, `auteurs`, `annee`, `revue`, `organisme`, `doi_url`, `domaine_sante`, `source_bruit`, `resume`, `resultat_cle`).

## Phase 1 — Récupération de l'état actuel de la base

Un seul appel à l'API Notion, en début de run, récupère l'ensemble des `doi_url` et `titre` déjà présents dans la base "Études". Le dédoublonnage qui suit se fait ensuite en mémoire, côté script, plutôt que par un appel Notion étude par étude — évite d'multiplier les appels réseau pour un gain de fiabilité et de rapidité.

## Phase 2 — Dédoublonnage contre l'existant

Même logique à deux niveaux que le dédoublonnage interne de l'étape 2, réappliquée ici contre l'intégralité de l'historique de la base (pas seulement contre les résultats du run en cours) :
1. **Comparaison stricte par `doi_url`** (normalisé : minuscules, sans préfixe `https://doi.org/`).
2. **Comparaison de secours par titre** (normalisé : minuscules, ponctuation retirée, comparaison de similarité) pour les études sans DOI des deux côtés.

Une étude reconnue comme déjà présente est écartée silencieusement de la suite du traitement — ce n'est pas une erreur, c'est le fonctionnement normal attendu d'un run hebdomadaire.

## Phase 3 — Écriture des nouvelles fiches

Pour chaque étude non dupliquée, création d'une page dans la base Notion "Études" :
- les champs extraits à l'étape 2 sont mappés directement, sans transformation (mêmes noms de colonnes des deux côtés, par construction) ;
- `statut` est initialisé à "🆕 Nouveau" ;
- `favori` est initialisé à `false` ;
- `date_ajout` est renseigné automatiquement par Notion à la création de la page.

## Gestion des erreurs

Politique reprise du projet d'automatisation des règles PLU, pour rester cohérent avec les habitudes déjà en place sur diagBruit : **un échec isolé ne bloque jamais l'ensemble du run**. L'écriture d'une fiche fait l'objet de quelques tentatives avec délai progressif avant d'être considérée en échec ; si elle échoue malgré tout, le script passe à l'étude suivante plutôt que d'interrompre tout le traitement — important pour un script qui s'exécute chaque semaine sans supervision.

Contrairement au projet PLU, il n'y a pas ici de fichier de sortie dédié aux erreurs (`*_erreurs.csv`) : l'architecture de ce projet n'a pas de dossier de sortie fichiers, seule la base Notion fait office de destination. Les échecs sont donc simplement journalisés (`print`/log standard), consultables directement dans les journaux d'exécution de GitHub Actions (étape 4) — suffisant vu le faible volume attendu par run (quelques études par semaine).

## Prochaine étape

Étape 4 — automatisation : planification de l'exécution hebdomadaire du script (étapes 2 et 3) via GitHub Actions, et gestion des secrets (clés API Anthropic et Notion).
