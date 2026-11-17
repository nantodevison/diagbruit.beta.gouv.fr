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

## Manière de publier — vérifiée le 17/11/2026

Jusqu'au 17/11/2026, la manière de publier par l'API était une **hypothèse** : une requête de mise à jour Strapi portant `status=published`, sans aucun champ modifié, devait publier le brouillon à l'identique — mais rien ne garantissait que Strapi ne publierait pas autre chose (champs vidés, par exemple).

**Constat du 17/11/2026** (Strapi 5.13.0, préprod) : la publication fonctionne comme prévu. Deux alertes du 067 ont été publiées une à une ; la version publiée est identique au brouillon (contrôle automatique et relecture des deux versions), et l'opérateur a vérifié à l'œil le statut dans l'admin Strapi et l'affichage de l'alerte de Hœrdt (marges de recul le long de l'A35) sur le front de préprod. Les 396 autres ont ensuite été publiées.

**À savoir pour choisir l'alerte de test** : le front n'affiche pas le PLU sur une parcelle qui n'a pas de score de bruit (limite connue, suivie par l'équipe de développement). Il faut donc tester une zone proche d'une grande route ou d'une voie ferrée.

**À refaire si la version de Strapi change** (voir `cms/package.json`) : dry-run, publication d'**une seule** alerte (`--ids`), vérification à l'œil dans l'admin et sur le front, puis le reste. L'outil compare aussi automatiquement chaque version publiée au brouillon et s'arrête à la première différence, mais ce contrôle ne voit que les champs qu'on lui a demandé de comparer : il ne remplace pas la vérification à l'œil.

## Ce que l'étape suppose en amont et en aval

- **En amont** : l'étape 7 a été exécutée en préprod pour le département, et l'export `etape6_{dept}_export.csv` est celui qui a servi à l'envoi.
- **En aval, hors de ce pipeline** : pour que les partenaires voient les alertes sur une parcelle, il faut aussi que les **géométries** soient chargées dans la base de données de préprod (Dagster, assets `noisezone`, puis dbt). C'est du ressort de l'équipe de développement.

## Point de vigilance transverse : géométries sans alerte publiée

Le front affiche une zone dès que sa géométrie touche la parcelle, même si Strapi n'a aucune alerte **publiée** pour son `alert_slug` : l'encadré apparaît alors **vide** (constaté dans le code le 13/11/2026 : `fastapi/app/utils/db.py`, `query_noisezone_intersecting_features`, et `frontend/.../RegulationPlu.tsx`). Or Dagster charge les géométries depuis un dossier Box (`390359250129`) en parcourant tous ses sous-dossiers. Si les géométries déposées par l'étape 7 se trouvent sous ce dossier et que la base de **prod** est alimentée à partir de lui, les parcelles concernées afficheront en prod des encadrés vides tant que les alertes n'y sont pas publiées. Question posée à l'équipe de développement le 13/11/2026 : comment les géométries Box sont-elles séparées entre préprod et prod ?

## Retour arrière

L'outil ne dépublie pas. Une dépublication se fait à la main dans l'admin Strapi. Le journal de l'étape 8 liste exactement les alertes publiées par l'outil, pour cibler ce retour arrière si nécessaire.
