# Workflow de la veille bruit & santé

*Validé le 25/09/2026. Décrit le circuit complet d'un document, du scan hebdomadaire
jusqu'à sa mise à disposition. Les étapes en pointillés sont décidées mais pas encore
codées (voir `FEUILLE_DE_ROUTE.md` à la racine du dépôt).*

```mermaid
flowchart TD
    GA["⏰ Lancement hebdomadaire<br/>GitHub Actions, lundi 6 h UTC"] --> DATE["Date de départ<br/>= dernière date_ajout dans Notion"]
    DATE --> RECH{{"Recherche de documents"}}
    RECH --> WEB["Recherche web<br/>web_search, domaines de la liste blanche"]
    RECH --> API["API scientifiques<br/>OpenAlex, Europe PMC"]
    WEB --> EXTR["Extraction par le LLM<br/>1 appel par document"]
    API --> EXTR

    EXTR -->|échec| LOG1["📝 Journal : échec + titre"]
    EXTR --> PERI{"Dans le périmètre ?"}
    PERI -->|"non : hors Europe, bruit professionnel,<br/>protocole sans résultat…"| LOG2["📝 Journal : écarté + raison"]
    PERI -->|"contenu insuffisant"| AVERIF["Mention « à vérifier »"]
    PERI -->|oui| DEDUP{"Doublon ?<br/>dans le run, puis contre Notion"}
    AVERIF --> DEDUP
    DEDUP -->|oui| LOG3["📝 Journal : doublon"]
    DEDUP -->|non| QUALIF["Qualification automatique<br/>priorité Haute / À examiner / Faible<br/>nouveauté, reprise_de"]
    QUALIF --> URL["Vérification de l'URL<br/>url_not_real"]
    URL --> NOTION[("Base Notion « Études »<br/>statut 🆕 Nouveau")]

    NOTION --> TRI["👤 Relecture manuelle<br/>tri par priorité"]
    TRI -->|"coché favori"| FAV["⭐ Favori"]
    TRI -->|"non coché"| LU["✅ Lu, conservé en base"]
    FAV --> FICHIER["👤 Ajout du texte intégral<br/>colonne fichier, si trouvé"]
    FICHIER --> REGEN["Régénération du résumé<br/>à partir du texte intégral"]
    FAV --> ART["📄 Mise à disposition<br/>via artefact de synthèse"]
    REGEN --> ART

    classDef aFaire stroke-dasharray: 5 5
    class FICHIER,REGEN,ART aFaire
```

## Principes

- **Rien n'est écarté silencieusement.** Un document ne quitte le circuit qu'à trois
  endroits (échec d'extraction, hors périmètre, doublon), et chacun est inscrit dans le
  journal du run GitHub Actions avec le titre et la raison. Un contenu trop pauvre pour
  être jugé n'est pas exclu : il est écrit avec la mention « à vérifier ».
- **La priorité informe, la case `favori` décide.** La priorité (Haute / À examiner /
  Faible) est calculée automatiquement pour ordonner la relecture ; seule la case
  `favori`, cochée à la main, traduit le choix de l'utilisateur.
- **Rappel avant précision.** Mieux vaut plus de documents à trier à la main que manquer
  un favori potentiel.
- **La fiche Notion reste la source unique.** Le résumé régénéré à partir du texte
  intégral remplace celui de la fiche ; l'artefact de synthèse s'appuie sur les fiches.
