# Étape 7 — Stockage : insertion automatisée dans Strapi et Notion

*Document de cadrage initial — phase de planification, pas d'implémentation à ce stade. Suite de `etape-6-mise-en-forme-diagbruit.md` et `etape-6-conception-technique.md`. Version issue des échanges du 21/08/2026.*

## Objectif

Automatiser, à partir des livrables de l'étape 6 (`etape6_{dept}_export.csv`, complété par l'opérateur via `outil_validation.html` — `alert_slug_propose` porte désormais la valeur finale — et `etape6_{dept}_geometries/`), les deux actions aujourd'hui faites à la main par la partie métier (voir `etape-6-mise-en-forme-diagbruit.md`, "Rappel du circuit métier actuel") :

1. créer (ou mettre à jour) l'entrée Strapi (préprod) portant le message d'une zone et son `alert_slug` ;
2. créer (ou mettre à jour) l'entrée Notion correspondante (base "Données réglementaires locales (PLU, PPBE, …)"), avec le même `alert_slug` et la géométrie en pièce jointe.

**Ce que cette étape ne change pas** : la partie développement continue de relier les deux (Strapi/Notion) pour les mettre à disposition de diagBruit — voir `etape-6-mise-en-forme-diagbruit.md`, point 3 du circuit. L'ingestion directe dans le pipeline Dagster/PostGIS reste hors scope, pour la même raison qu'à l'étape 6 (pipeline à usage interne à l'équipe de développement, pas le circuit qu'emprunte la partie métier).

## Ce qui est déjà su (repris de l'étape 6)

- Structure de la base Notion (`Territoire`, `Description`, `alert_slug`, `data`) — voir `etape-6-mise-en-forme-diagbruit.md`, "Structure réelle de la base Notion".
- Format de l'`alert_slug` (`alert-{Territoire sans espaces ni accents}-{terme métier}`), désormais saisi par l'opérateur dans `outil_validation.html`.
- Strapi n'y gère que le **texte** des préconisations (le champ message) — les géométries vivent entièrement dans PostGIS côté produit, et dans Notion côté circuit métier actuel.

## Points ouverts, à trancher avant une conception technique détaillée

Cette étape était explicitement écartée à l'étape 6 (voir `etape-6-mise-en-forme-diagbruit.md`, "Écarté de cette étape") faute de visibilité sur deux points, toujours ouverts :

1. **Schéma Strapi** — nom exact du content-type et de ses champs (message, `alert_slug`, éventuels champs obligatoires supplémentaires), et disponibilité d'un jeton d'API préprod avec droit d'écriture.
2. **Accès Notion** — un jeton d'intégration Notion partagé avec la base "Données réglementaires locales" (une intégration doit être explicitement partagée base par base ou page par page, un jeton seul ne suffit pas), et l'identifiant de cette base.

Trois points supplémentaires, apparus en préparant ce cadrage :

3. **Contenu de la colonne Notion `Description`** — "résumé libre, à usage interne Notion, distinct du message final" (voir `etape-6-mise-en-forme-diagbruit.md`). Rien dans le pipeline actuel ne produit ce texte : `etape6_{dept}_export.csv` n'a ni colonne dédiée, ni équivalent proche (`message_strapi` est le message final, pas un résumé interne). À trancher : laisser vide, dériver automatiquement (ex. premiers mots de `message_synthese`), ou ajouter une saisie manuelle supplémentaire (nouvelle colonne à l'étape 6, dans `outil_validation.html` ou son export) ?
4. **Pièce jointe géométrie côté Notion** — l'API Notion n'accepte pas un fichier local arbitraire pour une propriété "Fichier & média" : soit passer par l'API d'upload de fichiers de Notion (disponible depuis 2024, à vérifier si l'intégration y a accès), soit héberger les `.geojson` sur une URL publiquement accessible et les référencer en fichier externe. À trancher selon ce que l'intégration Notion disponible permet réellement.
5. **Idempotence** — si l'étape 7 est relancée pour un département déjà partiellement inséré (ex. après correction d'un message à l'étape 5), faut-il rechercher une entrée existante par `alert_slug` (Strapi et Notion permettent tous deux un filtre sur une propriété) et la mettre à jour plutôt que dupliquer, ou tenir un fichier de suivi local des lignes déjà insérées ? Une re-insertion silencieuse créerait des doublons dans deux systèmes utilisés par toute l'équipe métier.

**Point de vigilance transverse** : contrairement aux étapes précédentes, celle-ci écrit dans des systèmes partagés, visibles par d'autres personnes que l'opérateur du POC (CMS préprod, base Notion collective) — jamais anodin comme un fichier `output/` local. Un mode d'aperçu (afficher ce qui serait créé/mis à jour sans appeler les API, cf. les points 1-2 ci-dessus une fois résolus) sera nécessaire avant tout envoi réel, quelle que soit l'architecture retenue.

## Architecture provisoire envisagée (non implémentée, à confirmer une fois les points ci-dessus tranchés)

```
poc-urbanisme-plu/
└── etape7_stockage/            # à créer une fois les points ouverts tranchés
    ├── __init__.py
    ├── client_strapi.py        # aide partagée : créer/mettre à jour une entrée par alert_slug
    ├── client_notion.py        # aide partagée : créer/mettre à jour une page par alert_slug
    └── inserer.py              # phase unique : lit etape6_{dept}_export.csv + etape6_{dept}_geometries/,
                                 # appelle les deux clients, un mode --dry-run par défaut
```

Sur le modèle des étapes précédentes : lit les livrables de l'étape 6, un échec isolé sur une ligne ne bloque jamais les autres (tracé dans `etape7_{dept}_erreurs.csv`), le tout dans le même dossier `poc-urbanisme-plu/` autonome (voir `etape-1-conception-technique.md`, "Posture").

## Prochaine étape

Obtenir les éléments listés dans "Points ouverts" ci-dessus (accès Strapi et Notion, décision sur `Description`, stratégie de pièce jointe, idempotence) avant de rédiger une conception technique détaillée (`etape-7-conception-technique.md`) puis d'implémenter.
