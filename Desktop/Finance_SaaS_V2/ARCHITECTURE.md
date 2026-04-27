# ARCHITECTURE — Finance SaaS

> Document rédigé pour le CEO Produit — sans jargon technique inutile.  
> Dernière mise à jour : Avril 2026 (v6 — Scoring v2, Onboarding wizard v2, Tendances, Daret v1.5, Mon compte, Modest Mode prêt, 24 messages coach, badges & hints)

> 📌 **Source de vérité au quotidien** : `CLAUDE.md` (instructions actives + conventions actuelles).
> Ce document est le panorama lisible — il peut accuser un léger retard sur le code détail.

---

## ⚡ Changements clés depuis v5 (avril 2026)

**Stack & déploiement**
- Base : **PostgreSQL hébergé sur Supabase** (plus SQLite — la `db_manager` reste le gardien)
- **15 tables** au lieu de 7 (auth multi-tenant, daret, journal, badges/hints en JSON, etc.)
- Déploiement : **Streamlit Cloud** auto-deploy sur push `main`
- Auth : bcrypt + comptes admin (`UTILISATEURS.is_admin`)

**Brain v2 (scoring + coach)**
- `core/assistant_engine.py:compute_score(audit, mois)` — 5 facteurs / 100 pts :
  - Reste à vivre (25) · Épargne du mois (15) · Fonds d'urgence (20) ·
    Dépenses équilibrées 50/30/20 (25) · Engagement streak (15)
- 5 statuts : CRITIQUE / FAIBLE / MOYEN / BON / EXCELLENT
- Edge cases : reste négatif → cap 40 · first-month grace → 50 · stale data flag (5j+)
- Modèle d'épargne single source of truth : `épargne_totale − allouée objectifs = libre`
- Coach messages : `core/coach_messages.py` (24 entrées priorisées, 100% rédigées)
- Modest Mode prêt à exécuter (spec dans `BACKLOG.md`)

**Nouvelles pages & composants**
- `views/onboarding_v2.py` — wizard 4 étapes (welcome+revenu / récurrents / estimation / objectif+score)
- `views/tendances.py` — KPI strip, cashflow chart, velocity, subscription leakage, top 3
- `views/daret.py` + `views/daret_public.py` — Daret v1.5 (Bloomberg table + invite link `?daret=TOKEN`)
- `components/subcat_picker.py` — quick-pick après transactions épicerie
- `components/hints.py` — `show_hint()` UI dismissible
- `core/badges.py` — `award_badge()` / `has_badge()` via `PREFERENCES.badges_json`
- `core/hints.py` — `mark_hint_seen()` via `PREFERENCES.hints_seen_json`

**Mon compte**
- Profil (nom · email · changement de mot de passe bcrypt)
- Export JSON complet · suppression définitive du compte (type-SUPPRIMER)
- Personnalisation : objectif fonds d'urgence + classification 50/30/20

---

---

## 1. Arborescence du projet

```
Finance_SaaS_V2/
│
│  ── Fichiers racine (le "coeur" de l'application) ──────────────────────────
│
├── app.py                  ← Point d'entrée. Lance l'app, construit le contexte
│                             et route vers la bonne page. ~80 lignes.
│
├── config.py               ← Toutes les constantes du projet (chemins, couleurs,
│                             seuils, ratios). Si on veut changer une valeur globale,
│                             c'est ici qu'on vient.
│
├── db_manager.py           ← Le gardien de la base de données. Crée les tables,
│                             importe les transactions, gère les objectifs et budgets.
│
├── sqlite_connector.py     ← La "prise électrique" SQLite. Gère les connexions
│                             bas niveau à la base de données.
│
├── logic_sqlite.py         ← Le cerveau métier. Contient toute l'intelligence :
│                             classification des dépenses, calcul du score de santé,
│                             comparaison vs habitudes, projections, crash test.
│
├── audit.py                ← Le chef d'orchestre. Reçoit les données brutes,
│                             appelle la logique, et prépare un "état" propre
│                             pour l'interface. app.py ne parle qu'à lui.
│
├── reset_db.py             ← Outil de maintenance (usage terminal uniquement).
│                             Permet de réinitialiser ou peupler la base de données.
│
├── finance_saas.db         ← La base de données SQLite (fichier binaire).
│                             Contient toutes les transactions, catégories, objectifs.
│
│  ── Dossier core/ (logique pure — zéro Streamlit autorisé) ─────────────────
│
├── core/
│   ├── __init__.py              ← Marqueur de dossier Python (ne pas modifier)
│   │
│   ├── data_input.py            ← Toutes les opérations d'écriture en base :
│   │                              enregistrer_transaction()             — via audit (avec classifier)
│   │                              enregistrer_transaction_categorisee() — bypass classifier,
│   │                                catégorie connue d'avance (onboarding)
│   │                              sauvegarder_budgets()    — écrit les plafonds en BDD
│   │                              sauvegarder_revenus()    — PREFERENCES + transaction IN
│   │                              lister_categories()      — lit les catégories OUT
│   │                              est_onboarding_fait()    — détecte la 1ère utilisation
│   │                              marquer_onboarding_fait() — flag de fin d'onboarding
│   │
│   └── assistant_engine.py      ← Moteur de l'Assistant Financier Interactif.
│                                  3 composants découplés :
│                                  ┌ DECISION_TREE   — arbre de décision pur (données, sans Streamlit)
│                                  │  3 thèmes × N nœuds. Ajouter une branche = 3 lignes.
│                                  ├ DATA_RESOLVERS  — table resolver : data_fn → (ctx,inputs) → dict
│                                  │  Chaque resolver retourne {type, message, ...données}
│                                  └ AssistantEngine — orchestrateur : navigation + exécution
│                                     get_node(), get_children(), is_leaf(),
│                                     breadcrumb(), resolve()
│
│  ── Dossier components/ (briques UI réutilisables) ──────────────────────────
│
├── components/
│   ├── __init__.py         ← Marqueur de dossier Python (ne pas modifier)
│   │
│   ├── design_tokens.py    ← SOURCE DE VÉRITÉ UNIQUE pour le design system.
│   │                         Classe T : toutes les couleurs, tailles, rayons, ombres.
│   │                         Fonction css_variables() : génère le bloc :root{} CSS.
│   │                         ⚠️  Pour changer le thème → modifier ici uniquement.
│   │
│   ├── styles.py           ← Injection CSS globale (inject_css() depuis app.py).
│   │                         Utilise var(--token) partout — aucun hardcode.
│   │                         Dépend de design_tokens.py.
│   │
│   ├── cards.py            ← Composants visuels réutilisables :
│   │                         fs_card() → carte KPI avec barre de couleur
│   │                         alerte_box() → encadré d'alerte coloré
│   │                         cat_row() → ligne de catégorie avec barre de progression
│   │                         + constantes : couleurs catégories, labels identité coach
│   │
│   ├── charts.py           ← Graphiques Plotly réutilisables.
│   │                         _gauge() → jauge circulaire (50/30/20, score santé)
│   │
│   └── sidebar.py          ← La barre latérale complète :
│                             navigation 2 pages (Accueil / Assistant),
│                             sélecteur de mois, sélecteur d'identité du coach,
│                             formulaire de saisie rapide avec autocomplete,
│                             Zone Test (reset données).
│
│  ── Dossier views/ (pages de l'application) ────────────────────────────────
│
└── views/
    ├── __init__.py         ← Marqueur de dossier Python (ne pas modifier)
    │
    ├── onboarding.py       ← Écran de première configuration (affiché 1 seule fois).
    │                         2 étapes : revenus → dépenses du mois en cours par catégorie.
    │                         Étape 1 crée aussi une transaction IN pour le salaire.
    │                         Étape 2 : formulaire par sous-catégorie (catégorie connue →
    │                           bypass classifier via enregistrer_transaction_categorisee).
    │                         Toutes les transactions sont taguées Source=ONBOARDING.
    │
    ├── accueil.py          ← Page "Accueil" : solde hero, 4 KPIs, répartition
    │                         des dépenses par catégorie (expanders cliquables →
    │                         sous-catégories avec barres et montants),
    │                         message du coach, score de santé financière,
    │                         plan 50/30/20, donut.
    │
    └── assistant.py        ← Page "Assistant Financier Interactif" (remplace Coach,
                              Inspecteur et Simulateur). Interface conversationnelle
                              basée sur l'arbre de décision de assistant_engine.py.
                              Navigation : ast_path (chemin), ast_inputs (formulaires),
                              ast_result (cache résultat).
                              12 renderers spécialisés, 1 par RenderType.
                              _RENDERERS dispatch → renderer selon le type retourné.
```

---

## 2. Le Modèle de Données (Schéma de la Base de Données)

La base est **PostgreSQL hébergée sur Supabase** (depuis v6 — auparavant SQLite local).
Elle contient **15 tables**, toutes scopées par `user_id` sauf les référentiels partagés
(`CATEGORIES`, `DICO_MATCHING`, `REFERENTIEL`).

> Détails colonnes par colonne : voir directement `db_manager.py:initialiser_schema()`
> et `_ensure_*` (auto-migrations idempotentes au boot).

### Table TRANSACTIONS — la table centrale
Chaque ligne = une transaction financière.

| Colonne | Type | Signification |
|---|---|---|
| `ID_Unique` | Texte | Identifiant unique de la transaction |
| `Date_Saisie` | Date | Date d'enregistrement — format ISO `YYYY-MM-DD HH:MM:SS` |
| `Date_Valeur` | Date | Date réelle de la transaction — format ISO `YYYY-MM-DD` (utilisé pour tous les filtres par mois) |
| `Libelle` | Texte | Description brute (ex: "MARJANE CITE YACOUB") |
| `Montant` | Nombre | Montant signé : **positif** si IN, **négatif** si OUT. Le solde = `SUM(Montant)`. |
| `Sens` | Texte | `IN` = argent reçu, `OUT` = argent dépensé |
| `Categorie` | Texte | Catégorie attribuée (ex: "Vie Quotidienne") |
| `Sous_Categorie` | Texte | Sous-catégorie (ex: "Courses maison") |
| `Statut` | Texte | État de classification (voir Dictionnaire ci-dessous) |
| `Source` | Texte | Origine : `SAISIE` (manuel), `IMPORT` (fichier), `ONBOARDING` (saisie initiale) |

### Table CATEGORIES — le référentiel
La liste des catégories et sous-catégories connues. Sert de dictionnaire de base
pour la classification automatique.

### Table DICO_MATCHING — le dictionnaire de classification
Associe un mot-clé à une catégorie.  
Exemple : le mot-clé "MARJANE" → Catégorie "Alimentation", Sous-catégorie "Supermarché".

### Table PREFERENCES — la configuration utilisateur
Stocke les réglages (identité du coach choisie, devise, seuil d'alerte, ratios 50/30/20).

### Table OBJECTIFS — les objectifs d'épargne
Chaque ligne = un objectif créé par l'utilisateur (ex: "Vacances Portugal", 10 000 DH pour août 2026).

### Table BUDGETS_MENSUELS — les plafonds par catégorie
Permet de définir un budget max par sous-catégorie (ex: "Restaurants : 500 DH/mois").

### Table AUDIT_LOG — la traçabilité
Enregistre toutes les actions importantes (import, modification, validation).  
Créée automatiquement au premier lancement de l'application.

---

## 3. Le Data Flow — Cycle de vie de la donnée

> Comment une dépense saisie à la main devient un graphique dans le Dashboard.

```
Étape 1 — SAISIE (sidebar.py)
    L'utilisateur tape "MARJANE" + 350 DH + "Dépense"
    └── Le formulaire appelle audit.recevoir()

Étape 2 — RÉCEPTION & VALIDATION (audit.py)
    AuditMiddleware.recevoir() vérifie :
    - Le montant est-il suspect ? (trop élevé vs. habitudes → demande confirmation)
    - Est-ce un doublon ? (même libellé + même montant récent → bloque)
    └── Si OK, envoie à la couche logique

Étape 3 — CLASSIFICATION (logic_sqlite.py)
    ClassificationEngine cherche la catégorie en 5 niveaux :
    1. Règle exacte dans DICO_MATCHING
    2. Correspondance floue (fuzzy matching — tolère les fautes)
    3. Règle partielle (mot-clé dans le libellé)
    4. Historique (même libellé classifié avant ?)
    5. Échec → statut A_CLASSIFIER (à faire manuellement)
    └── Résultat : Catégorie = "Alimentation", Sous-catégorie = "Supermarché", Score = 95%

Étape 4 — PERSISTANCE (db_manager.py)
    La transaction est écrite dans la table TRANSACTIONS avec son statut et sa catégorie.
    └── La donnée est maintenant "en base"

Étape 5 — CALCUL (logic_sqlite.py + audit.py)
    Quand l'interface demande les données du mois :
    - MoteurAnalyse.get_bilan_mensuel() → somme des IN et OUT du mois
    - MoteurAnalyse.get_score_sante_financiere() → note sur 100
    - AuditMiddleware.get_ui_state() → assemble tout dans un dict propre

Étape 6 — AFFICHAGE (app.py → views/accueil.py)
    app.py récupère le dict "ctx" et l'envoie à la page concernée.
    La page lit ctx["bilan"]["solde"] et l'affiche en grand dans le Hero.
    └── L'utilisateur voit son solde mis à jour
```

---

## 4. Dictionnaire de l'Application

| Terme | Définition |
|---|---|
| **Statut A_CLASSIFIER** | Une transaction qui a été importée ou saisie mais dont la catégorie n'a pas encore été déterminée. Elle attend d'être traitée (manuellement ou automatiquement). |
| **Statut VALIDE** | Une transaction correctement catégorisée, qui entre dans tous les calculs et graphiques. |
| **Sens IN** | Transaction entrante = argent reçu (salaire, remboursement, vente). |
| **Sens OUT** | Transaction sortante = argent dépensé (loyer, courses, abonnement). |
| **Solde net** | Revenus du mois – Dépenses du mois. Un solde positif = tu as gagné plus que tu n'as dépensé. |
| **Reste à Vivre** | Argent disponible après avoir soustrait les charges fixes et l'épargne prévue. C'est ce qu'il reste pour les dépenses variables (loisirs, restaurants, etc.). |
| **Plan 50/30/20** | Règle budgétaire standard : 50% du revenu pour les besoins (loyer, courses), 30% pour les envies (loisirs, restaurants), 20% pour l'épargne. Les ratios varient selon l'identité du coach. |
| **Score Santé Financière** | Note de 0 à 100 calculée sur 3 critères : taux d'épargne (40 pts), respect du budget (40 pts), qualité de la classification (20 pts). |
| **Taux d'épargne** | Pourcentage du revenu mis de côté ce mois-ci. Exemple : 2 000 DH épargnés sur 10 000 DH de revenus = 20%. |
| **Identité du Coach** | Personnalité du coach financier choisie par l'utilisateur. Bâtisseur (épargne max), Équilibré (50/30/20 standard), Stratège (orienté objectif), Libéré (chasse le gaspillage). |
| **Humeur du Coach** | État émotionnel calculé automatiquement selon le score de santé : COOL (vert), NEUTRE (orange), SERIEUX (rouge). |
| **Snapshot** | Photo instantanée de l'état financier à un moment donné. Évite de recalculer tout depuis la base à chaque rechargement de page. |
| **Fuzzy Matching** | Technique de correspondance floue. Permet de reconnaître "CARRFOUR" même si mal orthographié, en le rapprochant de "CARREFOUR" dans le dictionnaire. |
| **Crash Test** | Simulation : "Combien de mois pourrais-je tenir financièrement si je perdais tous mes revenus demain ?" Basé sur les dépenses moyennes des 3 derniers mois vs. l'épargne cumulée. |
| **Charges fixes** | Dépenses qui reviennent chaque mois avec un montant stable (loyer, abonnements, EDF). Détectées automatiquement par l'app. |
| **ctx (contexte)** | Dictionnaire Python passé à chaque page contenant toutes les données du mois sélectionné : bilan, score, alertes, projections. Évite de recalculer les mêmes choses pour chaque page. |
| **AuditMiddleware** | Le chef d'orchestre de l'application. Toute demande de données passe par lui — il valide, calcule, et retourne un résultat propre à l'interface. |
| **Onboarding** | Écran de bienvenue en **2 étapes** affiché une seule fois. Étape 1 : salaire + extras → sauvegardés dans PREFERENCES ET créés en transaction IN. Étape 2 : montants par sous-catégorie pour le mois en cours → catégorie déjà connue, pas de classifier. Toutes les transactions reçoivent `Source=ONBOARDING`. Une fois validé, `onboarding_done = 1` dans PREFERENCES. |
| **Source ONBOARDING** | Valeur spéciale de la colonne `Source` dans TRANSACTIONS. Les transactions taguées ONBOARDING comptent dans le solde, les KPIs et les budgets (données réelles du mois), mais sont exclues des graphiques d'évolution mensuelle et des tendances par jour de semaine pour ne pas créer de pics artificiels liés à la saisie groupée initiale. |
| **Plafond permanent** | Budget défini dans la table CATEGORIES — s'applique à tous les mois sauf si overridé par un plafond mensuel. |
| **Plafond mensuel** | Budget défini dans BUDGETS_MENSUELS pour un mois spécifique. Prioritaire sur le plafond permanent. Utile pour les mois exceptionnels (fêtes, vacances). |
| **core/data_input** | Module Python (sans interface) qui centralise toute la logique d'écriture. En isolant les écritures ici, on peut les tester et les réutiliser sans toucher à l'UI. |
| **enregistrer_transaction_categorisee** | Variante de l'enregistrement qui bypasse le Trieur (classifier). Utilisée quand la catégorie et sous-catégorie sont déjà connues (onboarding). Évite la classification en "Divers" par défaut. |
| **Montant signé** | Convention de stockage : les montants OUT sont stockés **négatifs** en base, les IN **positifs**. Le solde mensuel = `SUM(Montant)`. Les affichages utilisent `ABS()` pour montrer des valeurs positives à l'écran. |
| **Zone Test** | Section cachée en bas de la sidebar (🛠️) permettant de réinitialiser toutes les données (TRANSACTIONS + PREFERENCES onboarding + plafonds CATEGORIES) pour repartir de zéro. Usage test uniquement. |
| **Assistant Financier Interactif** | Vue unique qui remplace Coach, Inspecteur et Simulateur. Interface conversationnelle pilotée par un arbre de décision modulaire. Ajouter une nouvelle fonctionnalité = 3 étapes : 1 nœud dans DECISION_TREE, 1 resolver dans DATA_RESOLVERS, 1 renderer dans _RENDERERS. Zéro touche à l'UI existante. |
| **DECISION_TREE** | Dictionnaire Python dans assistant_engine.py. Chaque clé = un nœud (id, label, description, children, data_fn, requires_input, input_spec). Données pures — zéro Streamlit. |
| **DATA_RESOLVERS** | Table de fonctions dans assistant_engine.py. Chaque fonction reçoit (ctx, inputs) et retourne un dict standardisé {type, message, ...données}. Peut être testé indépendamment de l'UI. |
| **RenderType** | Constantes qui lient un resolver à son renderer UI. Ex : RenderType.BURN_RATE → _render_burn_rate() dans views/assistant.py. |
| **Design Tokens** | Fichier components/design_tokens.py — source unique de toutes les valeurs visuelles (couleurs, tailles, rayons, ombres). Pour changer le thème de l'app entière : modifier T.PRIMARY dans ce fichier uniquement. |
| **Burn Rate** | Vitesse de dépense quotidienne = dépenses à ce jour ÷ jours écoulés. Permet de projeter les dépenses de fin de mois et d'alerter si on va dépasser les revenus. |
| **Intérêts composés** | Simulation C5 : Capital Final = Capital × (1 + taux/12)^mois + versement × ((1+taux/12)^mois - 1) / (taux/12). 100% calcul Python, zéro base de données. |
