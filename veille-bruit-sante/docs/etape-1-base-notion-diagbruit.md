# Étape 1 — Base Notion "Études"

*Document de cadrage détaillé de l'étape 1 du plan de veille bruit & santé de diagBruit (voir `plan-veille-bruit-sante-diagbruit.md`).*

**Entrée** : aucune — étape de conception initiale, exécutée une seule fois, hors de la boucle hebdomadaire.

## Principe

Une seule base Notion sert de support à l'ensemble du suivi : une bibliothèque de fiches, une par étude, consultée via des vues filtrées (par exemple "ajoutées cette semaine") plutôt que via un dashboard ou une base séparée. Ce choix a été fait après examen de deux options — une base "digests" séparée (journal narratif hebdomadaire) et une page dashboard native Notion (vues graphiques) — écartées pour l'instant : le besoin exprimé est déjà couvert par une vue filtrée sur la date d'ajout et par la colonne de résumé, sans complexité additionnelle.

## Contrat de données — base "Études"

Noms de colonnes normalisés (minuscules, underscores, sans accents), pour faciliter leur manipulation programmatique par le script des étapes suivantes.

| Colonne | Type Notion | Détail |
|---|---|---|
| `titre` | Titre (obligatoire) | Titre de la publication |
| `auteurs` | Texte | Premier auteur + "et al." si pertinent |
| `annee` | Nombre | Année de publication |
| `revue` | Sélection | Nom de la revue |
| `organisme` | Texte | Organisme(s) producteur(s) de l'étude |
| `doi_url` | URL | DOI en priorité, URL de la source en repli. Clé utilisée pour le dédoublonnage (étapes 2 et 3). |
| `domaine_sante` | Multi-sélection | Cardiovasculaire, Santé mentale, Cognition, Métabolique, Sommeil, Enfant... |
| `source_bruit` | Multi-sélection | Routier, Aérien, Ferroviaire, Industriel |
| `resume` | Texte long | 2-3 phrases rédigées lors de l'extraction (étape 2) |
| `resultat_cle` | Texte | Chiffre ou fait marquant, ex. "+18% mortalité CV pour +10dB" |
| `date_ajout` | Date (auto) | Remplie automatiquement à la création de la fiche |
| `statut` | Sélection | 🆕 Nouveau / ✅ Lu |
| `favori` | Case à cocher | Gérée uniquement par l'utilisateur, jamais par le script |

`statut` est initialisé à "🆕 Nouveau" à la création de chaque fiche (étape 3). `favori` reste à `false` par défaut. Le comptage "nouvelles publications de la semaine" se fait via une vue Notion filtrée sur `date_ajout` — aucun traitement spécifique requis côté script pour ce besoin.

## Prochaine étape

Étape 2 — recherche et extraction hebdomadaire, qui alimente cette base en respectant exactement ce contrat de données.
