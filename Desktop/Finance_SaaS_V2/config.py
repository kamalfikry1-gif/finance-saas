"""
config.py — Configuration centrale de Finance SaaS.

Toutes les constantes, chemins et seuils sont ici.
Les autres modules importent depuis ce fichier — plus de valeurs en dur dispersées.

Usage:
    from config import DB_PATH, SNAPSHOT_TTL, DEVISE
"""

from pathlib import Path

# ==============================================================================
# CHEMINS
# ==============================================================================

# Répertoire racine du projet (dossier contenant config.py)
BASE_DIR: Path = Path(__file__).resolve().parent

# Base de données principale
DB_PATH: str = str(BASE_DIR / "finance_saas.db")

# Fichier de log applicatif (optionnel — utilisé par les modules qui veulent logger sur disque)
LOG_PATH: str = str(BASE_DIR / "finance_saas.log")

# ==============================================================================
# CACHE / PERFORMANCE
# ==============================================================================

# Durée de vie du snapshot en secondes (AuditMiddleware._get_snapshot)
# Le cache est invalidé si nb_transactions change, même avant expiration du TTL.
SNAPSHOT_TTL: int = 300          # 5 minutes

# TTL Streamlit @st.cache_data — rafraîchissement UI minimum
# Les écritures invalident explicitement via core.cache.invalider(), donc
# un TTL long est sûr : on n'attend jamais le TTL pour voir les changements.
STREAMLIT_CACHE_TTL: int = 300   # 5 minutes

# ==============================================================================
# BASE DE DONNÉES — VALEURS PAR DÉFAUT
# ==============================================================================

# Devise affichée dans l'interface
DEVISE: str = "DH"

# Identité coach par défaut si aucune préférence n'est enregistrée
COACH_IDENTITE_DEFAUT: str = "EQUILIBRE"

# Seuil d'alerte budget par défaut (%) — affiché en orange dans l'UI
SEUIL_ALERTE_DEFAUT: float = 80.0

# Ratios 50/30/20 par défaut (correspondent à l'identité EQUILIBRE)
NEEDS_PCT_DEFAUT:   float = 50.0
WANTS_PCT_DEFAUT:   float = 30.0
SAVINGS_PCT_DEFAUT: float = 20.0

# ==============================================================================
# IDENTITÉS DU COACH
# ==============================================================================
# Chaque identité définit ses propres ratios cibles et seuils.
# humeur_seuil_score : score minimum (0–100) pour que le coach soit COOL.

IDENTITES_COACH = {
    "BATISSEUR": {
        "needs_pct":          45.0,
        "wants_pct":          25.0,
        "savings_pct":        30.0,
        "seuil_alerte":       70.0,   # Plus strict — tolérance moindre
        "humeur_seuil_score": 65.0,   # Score élevé requis pour COOL
    },
    "EQUILIBRE": {
        "needs_pct":          50.0,
        "wants_pct":          30.0,
        "savings_pct":        20.0,
        "seuil_alerte":       80.0,
        "humeur_seuil_score": 55.0,
    },
    "STRATEGE": {
        "needs_pct":          50.0,
        "wants_pct":          30.0,
        "savings_pct":        20.0,
        "seuil_alerte":       75.0,
        "humeur_seuil_score": 60.0,
    },
    "LIBERE": {
        "needs_pct":          55.0,
        "wants_pct":          25.0,
        "savings_pct":        20.0,
        "seuil_alerte":       80.0,
        "humeur_seuil_score": 50.0,   # Le plus indulgent
    },
}

# ==============================================================================
# HUMEUR DU COACH
# ==============================================================================

HUMEUR_COOL    = "COOL"
HUMEUR_NEUTRE  = "NEUTRE"
HUMEUR_SERIEUX = "SERIEUX"

# Seuils utilisés dans _calculer_humeur()
HUMEUR_SCORE_SERIEUX:       float = 40.0   # Score < X → toujours SERIEUX
HUMEUR_TAUX_EP_SERIEUX:     float = 5.0    # Taux épargne < X% → SERIEUX
HUMEUR_SAVINGS_SERIEUX:     float = 5.0    # savings_reel_pct < X% → SERIEUX
HUMEUR_SAVINGS_COOL_RATIO:  float = 0.6    # savings_reel >= savings_cible * X → COOL eligible

# ==============================================================================
# DÉTECTION D'ANOMALIES
# ==============================================================================

# Z-score au-delà duquel un montant est considéré suspect
SEUIL_ANOMALIE_SIGMA: float = 3.0

# Plage horaire considérée comme inhabituelle (heure locale, format 24h)
HEURE_INHABITUELLE_MIN: int = 1    # 01h00
HEURE_INHABITUELLE_MAX: int = 5    # 05h59

# ==============================================================================
# VALIDATION DES SAISIES
# ==============================================================================

MOT_CLE_MIN_LEN: int = 2
MOT_CLE_MAX_LEN: int = 100

# ==============================================================================
# ONBOARDING — RÉFÉRENCES MA (% du revenu mensuel)
# ==============================================================================
# Baselines affichés sous chaque slider du step 3 d'onboarding_v2
# ("Moyenne MA pour ce revenu ≈ X DH"). Servent aussi de valeurs initiales.
# Sources : moyennes pragmatiques basées sur observations marché MA —
# à raffiner après la phase beta avec les données réelles utilisateurs.

MA_REF_ENTRETIEN_PCT:    float = 0.05   # entretien maison + voiture
MA_REF_ALIMENTATION_PCT: float = 0.20   # courses, supermarché
MA_REF_TRANSPORT_PCT:    float = 0.10   # carburant, taxi, bus
MA_REF_ENVIES_PCT:       float = 0.10   # loisirs, restos, shopping
MA_REF_EPARGNE_PCT:      float = 0.10   # épargne mensuelle visée

# ==============================================================================
# ANALYSE — PARAMÈTRES PAR DÉFAUT
# ==============================================================================

# Nombre de mois de référence pour la comparaison vs habitudes
NB_MOIS_REF_DEFAUT: int = 3

# Top N dépenses affichées dans l'Inspecteur
TOP_N_DEPENSES: int = 10

# Nombre de mois affichés dans le graphe évolution (Inspecteur)
NB_MOIS_EVOLUTION: int = 6

# ==============================================================================
# SCORE SANTÉ FINANCIÈRE — PONDÉRATION
# ==============================================================================
# Le score est calculé dans MoteurAnalyse.get_score_sante_financiere().
# Ces pondérations sont définies ici pour faciliter l'ajustement.

SCORE_POIDS_EPARGNE:  float = 40.0   # pts max pour le taux d'épargne (LEGACY)
SCORE_POIDS_BUDGET:   float = 40.0   # pts max pour le respect du budget (LEGACY)
SCORE_POIDS_DIVERS:   float = 20.0   # pts max (transactions classifiées, etc.) (LEGACY)

# ── Nouveau scoring v2 (5 facteurs) ─────────────────────────────────────────
# Total 100 pts. Si onboarding pas fait, les 25 pts du 50/30/20 redistribués:
# +15 reste, +5 flow, +5 stock.
SCORE_V2_POIDS_RESTE:          float = 25.0   # reste à vivre post-abonnements
SCORE_V2_POIDS_EPARGNE_FLOW:   float = 15.0   # épargne du mois
SCORE_V2_POIDS_FONDS_URGENCE:  float = 20.0   # cumul vs target_mois_secu
SCORE_V2_POIDS_503020:         float = 25.0   # règle 50/30/20 (si onboarding)
SCORE_V2_POIDS_ENGAGEMENT:     float = 15.0   # streak quotidien

# Cibles (seuils pour atteindre les pts max d'un facteur)
SCORE_V2_RESTE_RATIO_TARGET:   float = 0.30   # 30% reste/revenus = full
SCORE_V2_TAUX_EPARGNE_TARGET:  float = 0.20   # 20% épargne/revenus = full
SCORE_V2_STREAK_DAYS_TARGET:   int   = 7      # 7 jours consécutifs = full
DEFAULT_TARGET_MOIS_SECURITE:  float = 3.0    # 3 mois fonds d'urgence = full

# Caps & flags
SCORE_V2_CAP_RESTE_NEGATIF:    float = 40.0   # reste < 0 → score plafonné à FAIBLE max
SCORE_V2_BASELINE_PREMIER_MOIS: float = 50.0  # nouveaux comptes < 30j sans data
SCORE_V2_STALE_DAYS:           int   = 5      # jours_inactif ≥ ce seuil → score_stale=True

# 5 niveaux (bornes inférieures)
SCORE_NIVEAU_EXCELLENT: float = 80.0
SCORE_NIVEAU_BON:       float = 60.0
SCORE_NIVEAU_MOYEN:     float = 40.0
SCORE_NIVEAU_FAIBLE:    float = 20.0
# En dessous de FAIBLE → niveau "CRITIQUE"


# ==============================================================================
# RÈGLE 50/30/20 — MAPPING DÉFAUT DES CATÉGORIES
# ==============================================================================
# Mapping par défaut: catégorie → type (Besoin / Envie / Épargne).
# L'utilisateur peut override individuellement (à venir: champ Type_503020 dans CATEGORIES).

CAT_TYPE_BESOIN  = "BESOIN"
CAT_TYPE_ENVIE   = "ENVIE"
CAT_TYPE_EPARGNE = "EPARGNE"

# Mapping conservateur — tout ce qui est essentiel/contraint = Besoin
DEFAULT_503020_MAPPING: dict = {
    # ── BESOINS (50% cible) ── ce que tu DOIS payer pour vivre
    "Loyer":              CAT_TYPE_BESOIN,
    "Charges":            CAT_TYPE_BESOIN,
    "Eau":                CAT_TYPE_BESOIN,
    "Électricité":        CAT_TYPE_BESOIN,
    "Internet":           CAT_TYPE_BESOIN,
    "Téléphone":          CAT_TYPE_BESOIN,
    "Télécom & Internet": CAT_TYPE_BESOIN,
    "Alimentation":       CAT_TYPE_BESOIN,
    "Courses":            CAT_TYPE_BESOIN,
    "Vie Quotidienne":    CAT_TYPE_BESOIN,
    "Transport":          CAT_TYPE_BESOIN,
    "Carburant":          CAT_TYPE_BESOIN,
    "Assurance":          CAT_TYPE_BESOIN,
    "Santé":              CAT_TYPE_BESOIN,
    "Pharmacie":          CAT_TYPE_BESOIN,
    "Médecin":            CAT_TYPE_BESOIN,
    "Éducation":          CAT_TYPE_BESOIN,
    "Crédit":             CAT_TYPE_BESOIN,
    "Remboursement":      CAT_TYPE_BESOIN,
    "Abonnements":        CAT_TYPE_BESOIN,  # subscriptions essentiels (déjà nécessaires)

    # ── ENVIES (30% cible) ── plaisir, optionnel
    "Restaurant":         CAT_TYPE_ENVIE,
    "Café":               CAT_TYPE_ENVIE,
    "Loisirs":            CAT_TYPE_ENVIE,
    "Sortie":             CAT_TYPE_ENVIE,
    "Voyage":             CAT_TYPE_ENVIE,
    "Vacances":           CAT_TYPE_ENVIE,
    "Shopping":           CAT_TYPE_ENVIE,
    "Vêtements":          CAT_TYPE_ENVIE,
    "Mode":               CAT_TYPE_ENVIE,
    "Beauté":             CAT_TYPE_ENVIE,
    "Cadeaux":            CAT_TYPE_ENVIE,
    "Divers":             CAT_TYPE_ENVIE,  # par défaut "envie" si non classé
    "Hobby":              CAT_TYPE_ENVIE,
    "Sport":              CAT_TYPE_ENVIE,
    "Streaming":          CAT_TYPE_ENVIE,  # Netflix/Spotify = envie
    "Jeux":               CAT_TYPE_ENVIE,

    # ── ÉPARGNE (20% cible) ── argent qui sort vers le futur
    "Épargne":            CAT_TYPE_EPARGNE,
    "Investissement":     CAT_TYPE_EPARGNE,
    "Daret":              CAT_TYPE_EPARGNE,
    "Objectif":           CAT_TYPE_EPARGNE,
}

# ==============================================================================
# INTERFACE (app.py)
# ==============================================================================

# Titre de l'application
APP_TITLE: str = "Finance SaaS"
APP_ICON:  str = "💰"

# Seuil score pour colorier la jauge (accueil.py)
# Les couleurs de l'UI vivent dans components/design_tokens.py (classe T).
SCORE_SEUIL_ORANGE: float = 50.0
