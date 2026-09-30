# Guide d'utilisation de la veille bruit & santé

*Pour la personne qui relit la base Notion « Études ». Rédigé le 29/09/2026. Le circuit
technique complet est décrit dans `workflow-veille.md`.*

En une phrase : chaque run cherche les nouvelles publications sur le bruit et la santé,
les résume et les classe par priorité dans Notion ; **ton rôle est de les relire, de cocher
celles qui comptent (`favori`) et de les marquer comme lues (`statut`)**.

## 1. Lancer le run

**Aujourd'hui, le run se lance à la main.** Le déclenchement automatique du lundi (6 h UTC,
via GitHub Actions) n'est actif que lorsque le code se trouve sur la branche `main` : ce
n'est pas encore le cas.

```bash
cd veille-bruit-sante
.venv\Scripts\activate          # environnement Python du projet (voir README)
python main.py
```

- **Ce qu'il fait** : il cherche les publications parues depuis la date du dernier ajout
  dans la base, les résume, les qualifie et crée une fiche par nouvelle étude.
- **Combien il coûte** : environ 1 à 2 centimes par étude trouvée (appels à l'API
  Anthropic).
- **Ce qu'il affiche** : chaque document écarté l'est avec sa raison — `ecarte (hors
  perimetre)`, `doublon … ecarte`, `deja present dans Notion`, `echec`. Rien ne disparaît
  sans trace : en cas de doute sur une étude absente, c'est là qu'il faut regarder.

Une fois le code fusionné dans `main`, le run tournera seul chaque lundi et ce journal sera
visible dans l'onglet *Actions* du dépôt GitHub.

## 2. Relire les nouvelles fiches (après chaque run)

1. Ouvre la vue **« À relire »** (voir section 4) : fiches au `statut` 🆕 Nouveau, triées
   par `priorite`.
2. Commence par **Haute**, puis **A examiner**. Les fiches **Faible** sont rarement des
   favoris, sauf si `a_verifier` est coché (contenu illisible : la priorité ne veut alors
   rien dire).
3. Pour chaque fiche, lis `resume` et `resultat_cle` ; ouvre `doi_url` si tu as besoin de
   la source.
4. Si le document compte : **coche `favori`**. Si tu as le PDF, **dépose-le dans
   `fichier`** (un vrai fichier plutôt qu'un lien copié depuis ton navigateur : ces liens
   expirent).
5. **Passe `statut` à ✅ Lu**, favori ou non.

Tu as déposé des PDF ? Lance ensuite `python -m analyse_relecture.regenerer_resumes` : il
réécrit le résumé de ces fiches à partir du texte intégral (payant : lance d'abord
`--estimer`, gratuit, pour connaître le coût).

### Ajouter un document à la main

Tu peux créer une fiche toi-même (un rapport trouvé par ailleurs, par exemple) : remplis
`titre` et ce que tu connais (auteurs, année, organisme, lien), dépose le PDF dans
`fichier`, puis lance `python -m analyse_relecture.regenerer_resumes` pour obtenir le
résumé et la priorité. Le modèle a pour consigne de ne jamais écarter un document que tu as
retenu : s'il ne traite le bruit qu'en passant, le résumé le dira.

Tu n'as rien d'autre à faire : la case **`ajout_manuel`** est cochée automatiquement (au
début du run, ou en lançant `regenerer_resumes`, qui lit l'auteur de la fiche). Elle
garantit que ta fiche ne décale pas la recherche du run suivant.

## 3. Les colonnes de la base

Le script n'écrit **jamais** dans les colonnes que tu remplis toi-même (`favori`,
`statut`, `fichier`).

### À lire — pour décider

| Colonne | Signification |
|---|---|
| `titre` | Titre de la publication. |
| `resume` | Résumé en 2-3 phrases, en français simple. |
| `resultat_cle` | Le résultat principal, avec son chiffre quand la source en donne un. |
| `priorite` | **Haute** : conclusion claire, source fiable, explications (population, méthode, chiffres) — la plupart des favoris sont là. **A examiner** : tout autre document de source reconnue, quel que soit son type (communiqué, revue narrative…). **Faible** : le reste, souvent faute de contenu lisible. Calculée automatiquement : elle t'informe, elle ne décide pas. |
| `nouveaute` | Voir l'encadré ci-dessous. |
| `a_verifier` | Le contenu n'a pas pu être lu correctement (PDF, page bloquée, page trop courte). Le résumé et la priorité sont peu fiables : jette un œil à la source. |
| `annee` | Année de publication. |
| `revue` / `organisme` | Où c'est publié (revue scientifique) ou qui le publie (OMS, ANSES, AEE…). |
| `doi_url` | Lien vers la source. |

> **`nouveaute` : que veut dire cette case ?**
> Elle est cochée quand le document a été **publié pendant la période cherchée par le
> run**, c'est-à-dire récemment. Elle est décochée pour un document plus ancien que le run
> a retrouvé (souvent un texte de référence : lignes directrices OMS, avis ANSES…) ou dont
> l'année est inconnue.
> - Elle ne dit **pas** que le document apporte un angle nouveau à la thématique : aucune
>   colonne ne le dit aujourd'hui.
> - Elle n'est **pas** redondante avec `statut` : `statut` suit **ta** lecture (lu ou
>   non), `nouveaute` décrit **l'âge du document**. Un texte de 2009 retrouvé cette
>   semaine sera 🆕 Nouveau (pas encore lu) mais sans `nouveaute`.
> - Pour les fiches créées lors du premier run (août 2026, recherche sur 10 ans), la case
>   est cochée pour toute publication parue depuis 2016.

### À remplir par toi

| Colonne | Signification |
|---|---|
| `favori` | Ton choix : ce document compte. Les favoris alimenteront l'artefact de synthèse. |
| `statut` | 🆕 Nouveau (pas encore relu) → ✅ Lu. |
| `fichier` | Le texte intégral (PDF déposé de préférence), qui sert à régénérer le résumé. |

### Techniques — tu peux les masquer dans tes vues

| Colonne | Signification |
|---|---|
| `type_document` | Étude originale, méta-analyse ou revue systématique, revue narrative ou éditorial, rapport institutionnel, communiqué ou page d'information. Sert au calcul de la priorité. |
| `sens_conclusion` | Effet démontré, absence d'effet, non concluant, pas de conclusion propre. Sert au calcul de la priorité. |
| `elements_probants` | Ce qui étaye la conclusion : population, méthode, chiffres. Vide = rien de probant dans le contenu lu. |
| `reprise_de` | Pour un communiqué ou un commentaire : la publication d'origine qu'il relaie. Utile pour retrouver l'étude source. |
| `domaine_sante` / `source_bruit` | Catégories (cardiovasculaire, sommeil… / routier, aérien…). Pratiques pour filtrer. Sur les fiches d'août 2026, ce sont des libellés libres, pas encore harmonisés. |
| `url_source` | D'où vient le lien : API scientifique (fiable), recherche web, ou proposé par le modèle (à vérifier). Vide sur les fiches d'août 2026. |
| `url_not_real` | Le lien semble mort ou renvoie vers la page d'accueil du site. |
| `auteurs` | Premier auteur (et « et al. »). |
| `date_ajout` | Date de création de la fiche (automatique). Le run suivant cherche à partir de la plus récente, **fiches ajoutées à la main exceptées**. |
| `ajout_manuel` | Fiche créée à la main dans Notion, et non par le run. Cochée automatiquement (Notion enregistre qui a créé chaque fiche). Ces fiches sont ignorées pour calculer la date de départ du run suivant, et leur provenance est considérée comme reconnue pour la priorité, puisque tu les as choisies. |

## 4. Les vues Notion à créer une fois

Dans Notion, sur la base « Études » : **+ Ajouter une vue** → Tableau, puis réglage des
filtres, du tri et des colonnes affichées (menu `···` → *Propriétés*).

| Vue | Filtre | Tri | Colonnes affichées |
|---|---|---|---|
| **À relire** | `statut` = 🆕 Nouveau | `priorite` (Haute → Faible) | les colonnes « À lire » et « À remplir » |
| **À vérifier** | `a_verifier` coché | `date_ajout` décroissante | `titre`, `doi_url`, `fichier`, `resume` |
| **Favoris** | `favori` coché | `annee` décroissante | `titre`, `resume`, `resultat_cle`, `nouveaute`, `revue`/`organisme` |

Astuce : pour trier `priorite` dans l'ordre Haute → A examiner → Faible, range les options
dans cet ordre dans les réglages de la colonne, puis trie par cette colonne.

## 5. Et ensuite

Les favoris serviront à une **synthèse** (artefact) destinée à faciliter la compréhension
des publications importantes — en cours de conception, voir `FEUILLE_DE_ROUTE.md` à la
racine du dépôt.
