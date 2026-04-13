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
STREAMLIT_CACHE_TTL: int = 60    # 1 minute

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

SCORE_POIDS_EPARGNE:  float = 40.0   # pts max pour le taux d'épargne
SCORE_POIDS_BUDGET:   float = 40.0   # pts max pour le respect du budget
SCORE_POIDS_DIVERS:   float = 20.0   # pts max (transactions classifiées, etc.)

# Niveaux de score (bornes inférieures)
SCORE_NIVEAU_EXCELLENT: float = 80.0
SCORE_NIVEAU_BON:       float = 60.0
SCORE_NIVEAU_MOYEN:     float = 40.0
# En dessous de MOYEN → niveau "FAIBLE"

# ==============================================================================
# INTERFACE (app.py)
# ==============================================================================

# Titre de l'application
APP_TITLE: str = "Finance SaaS"
APP_ICON:  str = "💰"

# Couleurs thème sombre (reprises dans le CSS injecté par app.py)
COLOR_BG:       str = "#0f0f23"
COLOR_CARD:     str = "#1a1a4a"
COLOR_ACCENT:   str = "#6366f1"
COLOR_SUCCESS:  str = "#10b981"
COLOR_WARNING:  str = "#f59e0b"
COLOR_DANGER:   str = "#ef4444"
COLOR_TEXT:     str = "#f1f5f9"
COLOR_MUTED:    str = "#94a3b8"

# Seuil score pour colorier la jauge (app.py)
SCORE_SEUIL_ORANGE: float = 50.0
