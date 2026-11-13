# Étape 8 — Publication : rendre visibles les alertes d'un département en préprod

*Document de cadrage de l'étape 8 du plan d'automatisation des règles PLU de diagBruit (voir `plan-automatisation-regles-plu-diagbruit.md`). Suite de `etape-7-stockage-diagbruit.md` et `etape-7-conception-technique.md`. La conception technique détaillée est dans `etape-8-conception-technique.md`, qui fait foi pour l'implémentation.*

## Objectif

L'étape 7 crée les alertes dans Strapi **en brouillon** : elles restent invisibles sur le site tant que personne ne les publie dans l'admin Strapi. Pour un département entier (398 alertes pour le 067 hors Eurométropole), la relecture et la publication une par une par l'opérateur ne sont pas tenables.

L'étape 8 publie en une fois, **sur le Strapi de préprod uniquement**, les brouillons créés par l'étape 7 pour un département, afin que les alertes apparaissent sur le front de préprod et puissent être **relues par les partenaires qui ont contribué à l'élaboration des PLU** (par exemple l'ATIP). Cette relecture externe, par des personnes qui connaissent les documents, remplace la relecture interne alerte par alerte.

## Décisions de cadrage (13/11/2026)

- **Préprod seulement.** L'outil refuse de publier en prod. Une publication en prod suppose une relecture : ce sont les retours des partenaires sur la préprod qui la constitueront. La question sera rouverte après ces retours.
- **On publie le brouillon tel qu'il est dans Strapi**, sans renvoyer le contenu de l'export de l'étape 6 : une retouche faite à la main dans l'admin entre l'étape 7 et l'étape 8 est ainsi conservée.
- **On ne republie jamais une alerte déjà publiée** : elle est signalée et laissée telle quelle.
- **Notion et Box ne sont pas touchés** : ils n'ont pas de notion de brouillon ni de préprod.

## ⚠️ Hypothèse technique non vérifiée — à confirmer avant tout envoi complet

**La manière de publier par l'API n'a jamais été testée.** L'outil suppose qu'une requête de mise à jour Strapi portant le paramètre `status=published`, **sans aucun champ modifié**, publie le brouillon existant à l'identique. Cette supposition s'appuie sur un comportement observé par accident le 24/08/2026 (une création sans `status=draft` avait publié l'entrée), mais **pas sur une mise à jour, ni sur une requête sans contenu**.

Tant qu'elle n'est pas confirmée en réel, trois issues sont possibles : la publication fonctionne comme prévu ; Strapi refuse la requête (aucun dégât) ; ou Strapi accepte la requête mais publie autre chose que le brouillon (champs vidés, par exemple) — c'est ce dernier cas qu'il faut absolument écarter.

**Procédure obligatoire au premier usage** (et à refaire si la version de Strapi change — 5.13.0 au 13/11/2026, voir `cms/package.json`) :
1. dry-run sur le département ;
2. publication d'**une seule** alerte (`--ids`) ;
3. vérification **à l'œil**, par l'opérateur, dans l'admin Strapi **et** sur le front de préprod : titre, message, source, référence, label identiques au brouillon ;
4. seulement ensuite, publication du reste.

L'outil compare aussi automatiquement, pour chaque alerte publiée, la version publiée au brouillon, et s'arrête à la première différence. Ce contrôle automatique **ne remplace pas** la vérification à l'œil de l'étape 3 : il ne voit que les champs qu'on lui a demandé de comparer.

## Ce que l'étape suppose en amont et en aval

- **En amont** : l'étape 7 a été exécutée en préprod pour le département, et l'export `etape6_{dept}_export.csv` est celui qui a servi à l'envoi.
- **En aval, hors de ce pipeline** : pour que les partenaires voient les alertes sur une parcelle, il faut aussi que les **géométries** soient chargées dans la base de données de préprod (Dagster, assets `noisezone`, puis dbt). C'est du ressort de l'équipe de développement.

## Point de vigilance transverse : géométries sans alerte publiée

Le front affiche une zone dès que sa géométrie touche la parcelle, même si Strapi n'a aucune alerte **publiée** pour son `alert_slug` : l'encadré apparaît alors **vide** (constaté dans le code le 13/11/2026 : `fastapi/app/utils/db.py`, `query_noisezone_intersecting_features`, et `frontend/.../RegulationPlu.tsx`). Or Dagster charge les géométries depuis un dossier Box (`390359250129`) en parcourant tous ses sous-dossiers. Si les géométries déposées par l'étape 7 se trouvent sous ce dossier et que la base de **prod** est alimentée à partir de lui, les parcelles concernées afficheront en prod des encadrés vides tant que les alertes n'y sont pas publiées. Question posée à l'équipe de développement le 13/11/2026 : comment les géométries Box sont-elles séparées entre préprod et prod ?

## Retour arrière

L'outil ne dépublie pas. Une dépublication se fait à la main dans l'admin Strapi. Le journal de l'étape 8 liste exactement les alertes publiées par l'outil, pour cibler ce retour arrière si nécessaire.
