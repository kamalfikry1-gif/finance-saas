"""
core/coach_messages.py — Coach message library.

Data-driven message table. Each entry has:
    id        — unique identifier
    when      — trigger condition (lambda evaluated against ctx)
    category  — status | factor | behavior | positive
    priority  — lower = shown first (1 = most urgent)
    message   — main text shown to user      ([À écrire])
    advice    — concrete action to suggest    ([À écrire])

Workflow:
    1. Scoring engine builds a `ctx` dict with all signals
    2. select_message(ctx) returns the best-matching factor/behavior message
    3. If no specific issue matches, fall back to the status-level message

Filling in messages later — keep this file as the single source of truth for
all coach copy.
"""

from typing import Any, Dict, List, Optional


# ── Context schema (what scoring engine must provide) ─────────────────────────
#
# ctx = {
#     # Score & status
#     "score":              float,    # 0–100
#     "statut":             str,      # CRITIQUE | FAIBLE | MOYEN | BON | EXCELLENT
#
#     # Factor 1 — Reste à vivre
#     "reste_a_vivre":      float,    # revenus − dépenses − abonnements (DH)
#     "reste_ratio":        float,    # reste_a_vivre / revenus (0–1)
#
#     # Factor 2 — Épargne (ce mois + fonds d'urgence cumulé)
#     "epargne_mois":       float,    # épargne réelle ce mois (DH)
#     "taux_epargne":       float,    # epargne_mois / revenus (0–1)
#     "epargne_libre":      float,    # épargne_totale − allouée (DH)
#     "depense_moy_mois":   float,    # avg monthly expenses (3 derniers mois)
#     "mois_securite":      float,    # epargne_libre / depense_moy_mois
#     "target_mois_secu":   float,    # user-customizable target (default 3.0)
#     "ratio_target":       float,    # mois_securite / target_mois_secu (0–1+)
#
#     # Factor 3 — Règle 50/30/20 (only valid if onboarding_done AND nb_unclassified_cats == 0)
#     "pct_besoins":        float,    # actual share (0–1)
#     "pct_envies":         float,    # actual share (0–1)
#     "pct_epargne_split":  float,    # actual share (0–1)
#     "nb_unclassified_cats": int,    # categories pending Besoin/Envie/Épargne classification
#
#     # Factor 4 — Engagement
#     "streak_jours":       int,
#     "jours_inactif":      int,      # days since last activity
#
#     # State
#     "onboarding_done":         bool,
#     "jours_depuis_inscription": int,
#     "mois_verts":              int,
#     "score_stale":             bool,    # true if jours_inactif >= 5
#
#     # Optional extras for advice tailoring
#     "categorie_top_dep":  str,      # most expensive category (for advice)
# }


# ── Default emergency fund target (months of expenses) ───────────────────────
# User can customize via PREFERENCES["fonds_urgence_target_mois"]
DEFAULT_TARGET_MOIS_SECURITE = 3.0


COACH_MESSAGES: List[Dict[str, Any]] = [

    # ═══════════════════════════════════════════════════════════════════════════
    # CRITICAL — these jump above status messages (priority < 10)
    # ═══════════════════════════════════════════════════════════════════════════

    {
        "id":       "factor_reste_a_vivre_negatif",
        "when":     lambda c: c["reste_a_vivre"] < 0,
        "category": "factor",
        "priority": 1,
        "message":  "Tes dépenses dépassent tes revenus ce mois. "
                    "Pas de panique, mais à corriger vite — "
                    "sinon les fins de mois deviennent un cauchemar.",
        "advice":   "Liste tes 3 plus grosses dépenses récentes. "
                    "Une seule à réduire de 200 DH change déjà l'équation.",
    },

    {
        # Only nag during the first month — after that, user has decided
        "id":       "behavior_onboarding_pending_first_month",
        "when":     lambda c: not c["onboarding_done"] and c["jours_depuis_inscription"] < 30,
        "category": "behavior",
        "priority": 2,
        "message":  "L'onboarding n'est pas terminé — sans tes infos de base "
                    "je ne peux pas calculer un score précis.",
        "advice":   "5 minutes pour finir l'onboarding, et le coach "
                    "commence vraiment à t'aider.",
    },

    # Score peut-être obsolète (3–6 jours inactif)
    {
        "id":       "behavior_score_obsolete",
        "when":     lambda c: 3 <= c["jours_inactif"] < 7,
        "category": "behavior",
        "priority": 3,
        "message":  "{jours_inactif}j sans nouvelles dépenses logées — "
                    "ton score est peut-être un peu décalé.",
        "advice":   "Ouvre l'app 1 minute pour rattraper ce que "
                    "tu as dépensé récemment.",
    },

    # Mini-onboarding catch-up offer (>= 7 jours inactif)
    {
        "id":       "behavior_mini_onboarding_offer",
        "when":     lambda c: c["jours_inactif"] >= 7,
        "category": "behavior",
        "priority": 3,
        "message":  "{jours_inactif}j sans te voir — pas grave, "
                    "la vie c'est la vie.",
        "advice":   "On fait un point rapide ? 1 minute pour "
                    "mettre à jour tes dépenses récentes.",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # FACTOR-LEVEL ISSUES — surfaced when a specific lever is weak
    # ═══════════════════════════════════════════════════════════════════════════

    # Reste à vivre faible (mais positif)
    {
        "id":       "factor_reste_a_vivre_faible",
        "when":     lambda c: 0 <= c["reste_ratio"] < 0.10,
        "category": "factor",
        "priority": 5,
        "message":  "Tu termines le mois avec peu de marge — "
                    "ça passe, mais sans filet pour les imprévus.",
        "advice":   "Vise 10% de reste à vivre. Pour ça : "
                    "commence par voir où tu peux gratter sur {categorie_top_dep}.",
    },

    # Pas d'épargne du tout
    {
        "id":       "factor_epargne_zero",
        "when":     lambda c: c["epargne_mois"] == 0,
        "category": "factor",
        "priority": 5,
        "message":  "Pas d'épargne ce mois. C'est OK ponctuellement, "
                    "pas en habitude.",
        "advice":   "100 DH la semaine prochaine. Petit, mais "
                    "c'est l'habitude qui compte.",
    },

    # Taux d'épargne trop faible
    {
        "id":       "factor_epargne_faible",
        "when":     lambda c: 0 < c["taux_epargne"] < 0.10,
        "category": "factor",
        "priority": 6,
        "message":  "Tu épargnes — c'est déjà bien. Sous 10% de tes revenus, "
                    "c'est lent à construire un coussin.",
        "advice":   "Vise 10% minimum. Pour 10 000 DH/mois, c'est 1 000 DH — "
                    "réaliste avec un peu d'ajustement.",
    },

    # 50/30/20 verrouillé — catégories non classifiées (gamification: 1–5 pts par classification)
    {
        "id":       "factor_categories_a_classifier",
        "when":     lambda c: c.get("nb_unclassified_cats", 0) > 0,
        "category": "factor",
        "priority": 6,
        "message":  "{nb_unclassified_cats} catégories ne sont pas classées "
                    "en Besoin / Envie / Épargne — ton score Dépenses équilibrées "
                    "est verrouillé à 0.",
        "advice":   "Va dans Paramètres → Personnalisation → Classification 50/30/20. "
                    "30 secondes pour débloquer 25 pts.",
    },

    # 50/30/20 — Besoins trop élevés
    {
        "id":       "factor_503020_besoins_eleves",
        "when":     lambda c: c["onboarding_done"] and c.get("nb_unclassified_cats", 0) == 0 and c["pct_besoins"] > 0.55,
        "category": "factor",
        "priority": 7,
        "message":  "Tes besoins essentiels prennent {pct_besoins:.0%} "
                    "de tes dépenses — la règle vise 50%.",
        "advice":   "Loyer + factures sont durs à bouger. L'astuce : "
                    "négocier les charges fixes (assurance, internet) "
                    "ou augmenter le revenu.",
    },

    # 50/30/20 — Envies trop élevées
    {
        "id":       "factor_503020_envies_elevees",
        "when":     lambda c: c["onboarding_done"] and c.get("nb_unclassified_cats", 0) == 0 and c["pct_envies"] > 0.35,
        "category": "factor",
        "priority": 7,
        "message":  "Tes envies (loisirs, restos, shopping) sont à "
                    "{pct_envies:.0%} — la règle vise 30%.",
        "advice":   "Pas besoin de tout couper. 1 ou 2 sorties de moins "
                    "ce mois, et l'équilibre revient.",
    },

    # 50/30/20 — Épargne split sous 15%
    {
        "id":       "factor_503020_epargne_split_faible",
        "when":     lambda c: c["onboarding_done"] and c.get("nb_unclassified_cats", 0) == 0 and c["pct_epargne_split"] < 0.15,
        "category": "factor",
        "priority": 7,
        "message":  "Sur ce qui sort, seulement {pct_epargne_split:.0%} "
                    "part en épargne — la règle vise 20%.",
        "advice":   "Automatise : dès la paie, vire 200 DH en épargne "
                    "avant de dépenser. Le seul truc qui marche.",
    },

    # Fonds d'urgence — inexistant (< 17% du target)
    {
        "id":       "factor_fonds_urgence_inexistant",
        "when":     lambda c: c["ratio_target"] < 0.17,
        "category": "factor",
        "priority": 4,
        "message":  "Tu n'as pas encore de fonds d'urgence — c'est le filet "
                    "pour les coups durs (panne voiture, frais médicaux, mois vide).",
        "advice":   "Vise 1 mois de dépenses pour commencer. 200 DH ce mois, "
                    "on bâtit pierre par pierre.",
    },

    # Fonds d'urgence — faible (17%–66% du target, donc 0.5–2 mois si target=3)
    {
        "id":       "factor_fonds_urgence_faible",
        "when":     lambda c: 0.17 <= c["ratio_target"] < 0.66,
        "category": "factor",
        "priority": 6,
        "message":  "{mois_securite:.1f} mois de réserve sur "
                    "{target_mois_secu:.0f} visés — tu progresses, c'est solide.",
        "advice":   "Continue d'épargner régulièrement. Chaque 100 DH "
                    "te rapproche du confort total.",
    },

    # Engagement faible — pas connecté
    {
        "id":       "factor_engagement_inactif",
        "when":     lambda c: c["jours_inactif"] >= 3,
        "category": "factor",
        "priority": 8,
        "message":  "Pas de log depuis {jours_inactif}j — tes données refroidissent "
                    "et mes conseils deviennent moins précis.",
        "advice":   "1 minute par jour pour log tes dépenses. "
                    "Le seul effort qui compte vraiment.",
    },

    {
        "id":       "factor_engagement_streak_court",
        "when":     lambda c: 0 < c["streak_jours"] < 3 and c["jours_inactif"] == 0,
        "category": "factor",
        "priority": 9,
        "message":  "Tu démarres un streak — encore quelques jours et "
                    "l'habitude se construit toute seule.",
        "advice":   "Reviens demain. 7 jours d'affilée et tu débloques "
                    "l'engagement max (15/15).",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # STATUS-LEVEL — fallback when no specific factor stands out (priority 10)
    # ═══════════════════════════════════════════════════════════════════════════

    {
        "id":       "status_critique",
        "when":     lambda c: c["statut"] == "CRITIQUE",
        "category": "status",
        "priority": 10,
        "message":  "On va être direct : ta situation financière est sous tension. "
                    "Pas de panique — c'est exactement le bon moment pour reconstruire, "
                    "pierre par pierre.",
        "advice":   "Commence par UNE chose : identifie ta plus grosse dépense ce mois. "
                    "Est-ce qu'elle est vraiment négociable ?",
    },
    {
        "id":       "status_faible",
        "when":     lambda c: c["statut"] == "FAIBLE",
        "category": "status",
        "priority": 10,
        "message":  "Tu tiens debout, mais la marge est mince. La bonne nouvelle : "
                    "un mois, deux ajustements, et tu passes au cran supérieur. "
                    "C'est faisable.",
        "advice":   "Vise UN changement cette semaine : réduire une catégorie de "
                    "dépense, ou mettre 100 DH de côté. Petit, mais concret.",
    },
    {
        "id":       "status_moyen",
        "when":     lambda c: c["statut"] == "MOYEN",
        "category": "status",
        "priority": 10,
        "message":  "Solide, mais sans filet de sécurité confortable. Le palier "
                    "suivant est à portée — il manque juste un peu de structure.",
        "advice":   "Identifie le facteur le plus faible dans ton score et "
                    "concentre-toi dessus ce mois. Un seul à la fois.",
    },
    {
        "id":       "status_bon",
        "when":     lambda c: c["statut"] == "BON",
        "category": "status",
        "priority": 10,
        "message":  "Belle gestion. Tu as les bons réflexes et de la marge. "
                    "Encore quelques pierres et tu atteins l'excellence.",
        "advice":   "Renforce ton fonds d'urgence si pas encore à 3 mois, ou "
                    "augmente ton taux d'épargne de 5%. Au choix.",
    },
    {
        "id":       "status_excellent",
        "when":     lambda c: c["statut"] == "EXCELLENT",
        "category": "status",
        "priority": 10,
        "message":  "Bravo. Discipline maîtrisée, fondations solides. Maintenant "
                    "le défi devient la croissance — plus la survie.",
        "advice":   "Pense investissement long terme (immobilier, bourse) ou "
                    "objectifs ambitieux. Tu as les bases pour viser plus haut.",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # POSITIVE REINFORCEMENT — only when nothing else needs attention
    # ═══════════════════════════════════════════════════════════════════════════

    {
        "id":       "positive_fonds_urgence_atteint",
        "when":     lambda c: c["ratio_target"] >= 1.0,
        "category": "positive",
        "priority": 12,
        "message":  "Objectif fonds d'urgence atteint — {mois_securite:.1f} mois "
                    "de couverture. Tu peux dormir tranquille.",
        "advice":   "Maintenant, fais bosser cet argent : compte épargne rémunéré, "
                    "ou vise plus loin (6 mois, 12 mois).",
    },
    {
        "id":       "positive_streak_milestone",
        "when":     lambda c: c["streak_jours"] in (7, 14, 30, 60, 100),
        "category": "positive",
        "priority": 14,
        "message":  "Streak de {streak_jours} jours d'affilée — "
                    "tu construis une vraie habitude.",
        "advice":   "Continue. À 30 jours c'est automatique, "
                    "à 100 c'est dans ton ADN.",
    },
    {
        "id":       "positive_mois_vert_premier",
        "when":     lambda c: c["mois_verts"] == 1 and c["score"] >= 60,
        "category": "positive",
        "priority": 14,
        "message":  "Premier mois vert — solde positif et score solide. "
                    "Tu prouves que ça marche.",
        "advice":   "Le 2e mois est plus facile que le 1er. "
                    "Refais pareil le mois prochain.",
    },
    {
        "id":       "positive_mois_verts_consecutifs",
        "when":     lambda c: c["mois_verts"] >= 3,
        "category": "positive",
        "priority": 13,
        "message":  "{mois_verts} mois verts d'affilée — "
                    "tu vis sur tes intérêts financiers.",
        "advice":   "Tu es prêt pour le palier suivant : investissement "
                    "long terme ou objectif ambitieux.",
    },
]


# ── Selector ──────────────────────────────────────────────────────────────────

def select_message(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pick the highest-priority message whose condition matches.

    Always returns a message — the 5 status entries cover the full 0–100 range,
    so at minimum one of them will match.
    """
    matches = [m for m in COACH_MESSAGES if m["when"](ctx)]
    matches.sort(key=lambda m: m["priority"])
    return matches[0]


def render_message(msg: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, str]:
    """
    Substitute {placeholders} in the message/advice with values from ctx.
    Returns {message, advice} as plain strings.
    """
    try:
        text   = msg["message"].format(**ctx)
        advice = msg["advice"].format(**ctx)
    except (KeyError, IndexError):
        text, advice = msg["message"], msg["advice"]
    return {"message": text, "advice": advice}
