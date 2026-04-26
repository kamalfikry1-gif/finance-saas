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
#     # Factor 2 — Épargne
#     "epargne_mois":       float,    # épargne réelle ce mois (DH)
#     "taux_epargne":       float,    # epargne_mois / revenus (0–1)
#
#     # Factor 3 — Règle 50/30/20 (only valid if onboarding_done)
#     "pct_besoins":        float,    # actual share (0–1)
#     "pct_envies":         float,    # actual share (0–1)
#     "pct_epargne_split":  float,    # actual share (0–1)
#
#     # Factor 4 — Engagement
#     "streak_jours":       int,
#     "jours_inactif":      int,      # days since last activity
#
#     # State
#     "onboarding_done":    bool,
#     "mois_verts":         int,
#
#     # Optional extras for advice tailoring
#     "categorie_top_dep":  str,      # most expensive category (for advice)
# }


COACH_MESSAGES: List[Dict[str, Any]] = [

    # ═══════════════════════════════════════════════════════════════════════════
    # CRITICAL — these jump above status messages (priority < 10)
    # ═══════════════════════════════════════════════════════════════════════════

    {
        "id":       "factor_reste_a_vivre_negatif",
        "when":     lambda c: c["reste_a_vivre"] < 0,
        "category": "factor",
        "priority": 1,
        "message":  "[À écrire — reste à vivre négatif, urgence]",
        "advice":   "[À écrire — action immédiate]",
    },

    {
        "id":       "behavior_onboarding_pending",
        "when":     lambda c: not c["onboarding_done"],
        "category": "behavior",
        "priority": 2,
        "message":  "[À écrire — onboarding pas fini, conseils limités]",
        "advice":   "[À écrire — termine l'onboarding pour précision]",
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
        "message":  "[À écrire — peu de marge cette fin de mois]",
        "advice":   "[À écrire — réduire {categorie_top_dep}]",
    },

    # Pas d'épargne du tout
    {
        "id":       "factor_epargne_zero",
        "when":     lambda c: c["epargne_mois"] == 0,
        "category": "factor",
        "priority": 5,
        "message":  "[À écrire — aucune épargne ce mois]",
        "advice":   "[À écrire — vise 10% du revenu]",
    },

    # Taux d'épargne trop faible
    {
        "id":       "factor_epargne_faible",
        "when":     lambda c: 0 < c["taux_epargne"] < 0.10,
        "category": "factor",
        "priority": 6,
        "message":  "[À écrire — taux d'épargne sous 10%]",
        "advice":   "[À écrire — augmenter à 10–20%]",
    },

    # 50/30/20 — Besoins trop élevés
    {
        "id":       "factor_503020_besoins_eleves",
        "when":     lambda c: c["onboarding_done"] and c["pct_besoins"] > 0.55,
        "category": "factor",
        "priority": 7,
        "message":  "[À écrire — besoins dépassent 50%]",
        "advice":   "[À écrire — voir où réduire]",
    },

    # 50/30/20 — Envies trop élevées
    {
        "id":       "factor_503020_envies_elevees",
        "when":     lambda c: c["onboarding_done"] and c["pct_envies"] > 0.35,
        "category": "factor",
        "priority": 7,
        "message":  "[À écrire — envies dépassent 30%]",
        "advice":   "[À écrire — refais le point sur tes envies]",
    },

    # 50/30/20 — Épargne split sous 15%
    {
        "id":       "factor_503020_epargne_split_faible",
        "when":     lambda c: c["onboarding_done"] and c["pct_epargne_split"] < 0.15,
        "category": "factor",
        "priority": 7,
        "message":  "[À écrire — épargne sous 20% (cible 50/30/20)]",
        "advice":   "[À écrire — automatise un virement mensuel]",
    },

    # Engagement faible — pas connecté
    {
        "id":       "factor_engagement_inactif",
        "when":     lambda c: c["jours_inactif"] >= 3,
        "category": "factor",
        "priority": 8,
        "message":  "[À écrire — pas connecté depuis {jours_inactif}j]",
        "advice":   "[À écrire — ouvre l'app chaque jour pour suivre]",
    },

    {
        "id":       "factor_engagement_streak_court",
        "when":     lambda c: 0 < c["streak_jours"] < 3 and c["jours_inactif"] == 0,
        "category": "factor",
        "priority": 9,
        "message":  "[À écrire — encourage à tenir le streak]",
        "advice":   "[À écrire — viser 7 jours consécutifs]",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # STATUS-LEVEL — fallback when no specific factor stands out (priority 10)
    # ═══════════════════════════════════════════════════════════════════════════

    {
        "id":       "status_critique",
        "when":     lambda c: c["statut"] == "CRITIQUE",
        "category": "status",
        "priority": 10,
        "message":  "[À écrire — situation critique, panique douce]",
        "advice":   "[À écrire — par où commencer]",
    },
    {
        "id":       "status_faible",
        "when":     lambda c: c["statut"] == "FAIBLE",
        "category": "status",
        "priority": 10,
        "message":  "[À écrire — situation fragile]",
        "advice":   "[À écrire — un cran à passer]",
    },
    {
        "id":       "status_moyen",
        "when":     lambda c: c["statut"] == "MOYEN",
        "category": "status",
        "priority": 10,
        "message":  "[À écrire — moyen, peut mieux faire]",
        "advice":   "[À écrire — quoi améliorer en priorité]",
    },
    {
        "id":       "status_bon",
        "when":     lambda c: c["statut"] == "BON",
        "category": "status",
        "priority": 10,
        "message":  "[À écrire — bon, encouragement]",
        "advice":   "[À écrire — comment atteindre excellent]",
    },
    {
        "id":       "status_excellent",
        "when":     lambda c: c["statut"] == "EXCELLENT",
        "category": "status",
        "priority": 10,
        "message":  "[À écrire — excellent, félicitations]",
        "advice":   "[À écrire — prochain défi]",
    },

    # ═══════════════════════════════════════════════════════════════════════════
    # POSITIVE REINFORCEMENT — only when nothing else needs attention
    # ═══════════════════════════════════════════════════════════════════════════

    {
        "id":       "positive_streak_milestone",
        "when":     lambda c: c["streak_jours"] in (7, 14, 30, 60, 100),
        "category": "positive",
        "priority": 14,
        "message":  "[À écrire — palier streak {streak_jours}j]",
        "advice":   "[À écrire — prochain palier]",
    },
    {
        "id":       "positive_mois_vert_premier",
        "when":     lambda c: c["mois_verts"] == 1 and c["score"] >= 60,
        "category": "positive",
        "priority": 14,
        "message":  "[À écrire — premier mois vert]",
        "advice":   "[À écrire — enchaîne]",
    },
    {
        "id":       "positive_mois_verts_consecutifs",
        "when":     lambda c: c["mois_verts"] >= 3,
        "category": "positive",
        "priority": 13,
        "message":  "[À écrire — {mois_verts} mois verts d'affilée]",
        "advice":   "[À écrire — tu vis sur tes intérêts]",
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
