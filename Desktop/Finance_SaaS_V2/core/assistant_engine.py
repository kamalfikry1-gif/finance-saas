"""
core/assistant_engine.py — Moteur de l'Assistant Financier Interactif.

Architecture modulaire :
    DECISION_TREE  — Arbre de décision pur (données, sans Streamlit).
    DATA_RESOLVERS — Table de résolution : data_fn → (ctx, inputs) → résultat.
    AssistantEngine — Orchestrateur : navigation + exécution.

Pour ajouter une nouvelle branche :
    1. Ajouter une entrée dans DECISION_TREE avec un id unique.
    2. L'ajouter dans la liste "children" du nœud parent.
    3. Si feuille : ajouter le resolver dans DATA_RESOLVERS.
    Rien d'autre à toucher — l'UI se génère automatiquement.

Contrat des resolvers :
    Signature  : resolver(ctx: dict, inputs: dict) -> dict
    Champs retournés obligatoires :
        type    : str  — identifiant du renderer UI (voir RENDER_TYPES)
        message : str  — phrase coach contextuelle
    Champs optionnels selon le type :
        data, kpis, alertes, ... (dépend du renderer)
"""

from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES DE TYPES DE RENDU
# Chaque type correspond à un renderer dans views/assistant.py.
# ─────────────────────────────────────────────────────────────────────────────

class RenderType:
    REPARTITION       = "REPARTITION"        # Donut + tableau catégories
    TOP_DEPENSES      = "TOP_DEPENSES"       # Barplot horizontal top N
    EVOLUTION         = "EVOLUTION"          # Multi-bar revenus/dépenses/solde
    TENDANCES_JOURS   = "TENDANCES_JOURS"    # Barplot par jour de semaine
    EPARGNE           = "EPARGNE"            # KPIs + liste objectifs actifs
    ALERTES_BUDGET    = "ALERTES_BUDGET"     # Alertes + budget vs réel
    COMPARAISON       = "COMPARAISON"        # Écart vs habitudes
    PROJECTION        = "PROJECTION"         # KPIs projection fin de mois
    SIM_IMPACT        = "SIM_IMPACT"         # Simulation : impact achat
    SIM_OBJECTIF      = "SIM_OBJECTIF"       # Simulation : objectif épargne
    SIM_CRASH         = "SIM_CRASH"          # Simulation : crash test
    MES_OBJECTIFS     = "MES_OBJECTIFS"      # Suivi objectifs créés
    BURN_RATE         = "BURN_RATE"          # Vitesse de dépense (DH/jour)
    SIM_INTERETS      = "SIM_INTERETS"       # Simulation intérêts composés


# ─────────────────────────────────────────────────────────────────────────────
# ARBRE DE DÉCISION
# Structure : chaque nœud est un dict avec les clés suivantes :
#   id          : identifiant unique (str)
#   label       : texte affiché (avec emoji)
#   description : sous-titre affiché sous le label
#   children    : liste d'ids enfants ([] pour une feuille)
#   data_fn     : clé dans DATA_RESOLVERS (None pour les nœuds intermédiaires)
#   requires_input : True si l'UI doit afficher un formulaire avant d'exécuter
#   input_spec  : dict de specs de formulaire (voir format ci-dessous)
#
# Format input_spec :
#   { "field_key": { "type": "number"|"slider", "label": str,
#                    "default": Any, "min": float, "max": float, "step": float } }
# ─────────────────────────────────────────────────────────────────────────────

DECISION_TREE: Dict[str, Dict[str, Any]] = {

    # ── Racine ────────────────────────────────────────────────────────────────
    "root": {
        "id":          "root",
        "label":       "Bonjour 👋 Je suis ton assistant financier.",
        "description": "Que veux-tu explorer aujourd'hui ?",
        "children":    ["A", "B", "C"],
        "data_fn":     None,
        "requires_input": False,
        "input_spec":  {},
    },

    # ── Thème A : Analyse & Inspecteur ───────────────────────────────────────
    "A": {
        "id":          "A",
        "label":       "🔍 Analyser mes dépenses",
        "description": "Inspection chirurgicale de tes dépenses passées.",
        "children":    ["A1", "A2", "A3", "A4", "A5"],
        "data_fn":     None,
        "requires_input": False,
        "input_spec":  {},
    },
    "A1": {
        "id":          "A1",
        "label":       "📊 Répartition du mois",
        "description": "Comment se répartissent mes dépenses ce mois-ci ?",
        "children":    [],
        "data_fn":     "repartition_mois",
        "requires_input": False,
        "input_spec":  {},
    },
    "A2": {
        "id":          "A2",
        "label":       "🏆 Top dépenses",
        "description": "Quelles sont mes plus grosses dépenses ?",
        "children":    [],
        "data_fn":     "top_depenses",
        "requires_input": False,
        "input_spec":  {},
    },
    "A3": {
        "id":          "A3",
        "label":       "📈 Évolution mensuelle",
        "description": "Comment évoluent mes revenus et dépenses mois par mois ?",
        "children":    [],
        "data_fn":     "evolution_mensuelle",
        "requires_input": False,
        "input_spec":  {},
    },
    "A4": {
        "id":          "A4",
        "label":       "📅 Habitudes par jour",
        "description": "Quel jour de la semaine je dépense le plus ?",
        "children":    [],
        "data_fn":     "tendances_jours",
        "requires_input": False,
        "input_spec":  {},
    },
    "A5": {
        "id":          "A5",
        "label":       "🔥 Burn Rate",
        "description": "À quelle vitesse tu brûles ton budget ce mois-ci ?",
        "children":    [],
        "data_fn":     "burn_rate",
        "requires_input": False,
        "input_spec":  {},
    },

    # ── Thème B : Budget & Objectifs ─────────────────────────────────────────
    "B": {
        "id":          "B",
        "label":       "🎯 Budget & Objectifs",
        "description": "Suivi de l'épargne, des plafonds et des projections.",
        "children":    ["B1", "B2", "B3", "B4"],
        "data_fn":     None,
        "requires_input": False,
        "input_spec":  {},
    },
    "B1": {
        "id":          "B1",
        "label":       "💰 Mon épargne",
        "description": "Où en est mon épargne et mes objectifs actifs ?",
        "children":    [],
        "data_fn":     "epargne_objectifs",
        "requires_input": False,
        "input_spec":  {},
    },
    "B2": {
        "id":          "B2",
        "label":       "🚨 Plafonds & Alertes",
        "description": "Ai-je dépassé des plafonds budgétaires ce mois-ci ?",
        "children":    [],
        "data_fn":     "alertes_budget",
        "requires_input": False,
        "input_spec":  {},
    },
    "B3": {
        "id":          "B3",
        "label":       "🔄 Vs mes habitudes",
        "description": "Est-ce que je dépense plus ou moins que d'habitude ?",
        "children":    [],
        "data_fn":     "comparaison_habitudes",
        "requires_input": False,
        "input_spec":  {},
    },
    "B4": {
        "id":          "B4",
        "label":       "🔭 Projection fin de mois",
        "description": "À ce rythme, où en serai-je à la fin du mois ?",
        "children":    [],
        "data_fn":     "projection_mois",
        "requires_input": False,
        "input_spec":  {},
    },

    # ── Thème C : Simulateur ─────────────────────────────────────────────────
    "C": {
        "id":          "C",
        "label":       "🔮 Simuler un scénario",
        "description": "Joue avec les chiffres — explore les scénarios « Et si ? ».",
        "children":    ["C1", "C2", "C3", "C4", "C5"],
        "data_fn":     None,
        "requires_input": False,
        "input_spec":  {},
    },
    "C1": {
        "id":          "C1",
        "label":       "🛒 Et si je fais un gros achat ?",
        "description": "Mesure l'impact d'un projet sur ton épargne.",
        "children":    [],
        "data_fn":     "sim_impact_projet",
        "requires_input": True,
        "input_spec":  {
            "montant_projet": {
                "type": "number", "label": "Montant du projet (DH)",
                "default": 15000.0, "min": 100.0, "max": 500_000.0, "step": 500.0,
            },
            "mois_cibles": {
                "type": "slider", "label": "Horizon de remboursement (mois)",
                "default": 12, "min": 1, "max": 36, "step": 1,
            },
        },
    },
    "C2": {
        "id":          "C2",
        "label":       "🎯 Effort pour un objectif",
        "description": "Combien dois-je mettre de côté chaque mois pour atteindre un objectif ?",
        "children":    [],
        "data_fn":     "sim_objectif_epargne",
        "requires_input": True,
        "input_spec":  {
            "cible_dh": {
                "type": "number", "label": "Montant cible (DH)",
                "default": 50000.0, "min": 100.0, "max": 1_000_000.0, "step": 1000.0,
            },
            "nb_mois": {
                "type": "slider", "label": "Délai (mois)",
                "default": 24, "min": 1, "max": 60, "step": 1,
            },
        },
    },
    "C3": {
        "id":          "C3",
        "label":       "💥 Crash test",
        "description": "Combien de mois pourrais-je tenir sans aucun revenu ?",
        "children":    [],
        "data_fn":     "sim_crash_test",
        "requires_input": True,
        "input_spec":  {
            "nb_mois_sans_revenu": {
                "type": "slider", "label": "Mois sans revenus à simuler",
                "default": 3, "min": 1, "max": 12, "step": 1,
            },
        },
    },
    "C4": {
        "id":          "C4",
        "label":       "📋 Mes objectifs sauvegardés",
        "description": "Suivi de progression de tous mes objectifs créés.",
        "children":    [],
        "data_fn":     "mes_objectifs",
        "requires_input": False,
        "input_spec":  {},
    },
    "C5": {
        "id":          "C5",
        "label":       "📈 Magie des intérêts composés",
        "description": "Combien vaut mon épargne si je l'investis à long terme ?",
        "children":    [],
        "data_fn":     "sim_interets_composes",
        "requires_input": True,
        "input_spec":  {
            "capital_initial": {
                "type": "number", "label": "Capital initial (DH)",
                "default": 10000.0, "min": 0.0, "max": 500_000.0, "step": 1000.0,
            },
            "versement_mensuel": {
                "type": "number", "label": "Versement mensuel (DH)",
                "default": 500.0, "min": 0.0, "max": 50_000.0, "step": 100.0,
            },
            "taux_annuel": {
                "type": "slider", "label": "Taux annuel (%)",
                "default": 5, "min": 1, "max": 20, "step": 1,
            },
            "annees": {
                "type": "slider", "label": "Horizon (années)",
                "default": 10, "min": 1, "max": 30, "step": 1,
            },
        },
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# RESOLVERS DE DONNÉES
# Chaque resolver reçoit ctx (dict app.py) + inputs (dict form) et retourne
# un dict standardisé que le renderer UI sait afficher.
# ─────────────────────────────────────────────────────────────────────────────

from components.helpers import dh as _dh


def _resolve_burn_rate(ctx: Dict, inputs: Dict) -> Dict:
    """Calcule le burn rate (DH/jour) et la projection de fin de mois."""
    import calendar
    from datetime import datetime

    depenses   = abs(ctx["bilan"].get("depenses", 0))
    revenus    = ctx["bilan"].get("revenus", 0)
    mois_sel   = ctx.get("mois_sel", "")
    mois_lbl   = ctx.get("mois_lbl", "")

    try:
        m, y = int(mois_sel.split("/")[0]), int(mois_sel.split("/")[1])
    except (ValueError, IndexError):
        m, y = datetime.now().month, datetime.now().year

    now          = datetime.now()
    jours_total  = calendar.monthrange(y, m)[1]
    # Si c'est le mois courant, utiliser le jour d'aujourd'hui, sinon fin du mois
    if now.year == y and now.month == m:
        jours_ecoules = max(now.day, 1)
    else:
        jours_ecoules = jours_total

    jours_restants = jours_total - jours_ecoules
    burn           = depenses / jours_ecoules if jours_ecoules > 0 else 0
    projection     = burn * jours_total

    # Date estimée d'épuisement du solde
    solde       = ctx["bilan"].get("solde", 0)
    date_epuis  = None
    if burn > 0 and solde > 0:
        jours_avant_epuis = solde / burn
        from datetime import timedelta
        date_epuis = (
            datetime(y, m, jours_ecoules) + timedelta(days=jours_avant_epuis)
        ).strftime("%d/%m/%Y")

    # Message coach
    if burn == 0:
        message = "Aucune dépense enregistrée ce mois."
    elif projection > revenus:
        message = (
            f"⚠️ Tu brûles **{burn:,.0f} DH/jour**. "
            f"Projection fin de mois : **{projection:,.0f} DH**, soit "
            f"**{projection - revenus:,.0f} DH de plus** que tes revenus !"
        )
    else:
        message = (
            f"Tu dépenses **{burn:,.0f} DH/jour** en moyenne "
            f"({jours_ecoules}j écoulés sur {jours_total}j). "
            f"Projection fin de mois : **{projection:,.0f} DH**."
        )

    return {
        "type":            RenderType.BURN_RATE,
        "depenses":        depenses,
        "revenus":         revenus,
        "burn_rate":       burn,
        "jours_ecoules":   jours_ecoules,
        "jours_total":     jours_total,
        "jours_restants":  jours_restants,
        "projection":      projection,
        "date_epuis":      date_epuis,
        "solde":           solde,
        "mois_lbl":        mois_lbl,
        "message":         message,
    }


def _resolve_sim_interets(ctx: Dict, inputs: Dict) -> Dict:
    """Simulation intérêts composés — 100% calcul, zéro DB."""
    capital_i  = float(inputs.get("capital_initial", 10000))
    versement  = float(inputs.get("versement_mensuel", 500))
    taux_a     = float(inputs.get("taux_annuel", 5)) / 100
    annees     = int(inputs.get("annees", 10))
    nb_mois    = annees * 12
    taux_m     = taux_a / 12

    # Projection mois par mois
    series = []
    capital_avec = capital_i
    capital_sans = capital_i
    for m in range(1, nb_mois + 1):
        capital_avec = capital_avec * (1 + taux_m) + versement
        capital_sans = capital_sans + versement
        if m % 12 == 0:
            series.append({
                "annee":        m // 12,
                "avec_interets": round(capital_avec, 2),
                "sans_interets": round(capital_sans, 2),
                "interets_gen":  round(capital_avec - capital_sans, 2),
            })

    total_investi = capital_i + versement * nb_mois
    interets_gen  = capital_avec - total_investi
    multiplicateur = capital_avec / total_investi if total_investi > 0 else 1

    # Message coach
    if versement > 0:
        message = (
            f"Si tu investis **{versement:,.0f} DH/mois** à **{taux_a*100:.0f}%/an** "
            f"pendant **{annees} ans**, tu obtiens **{capital_avec:,.0f} DH** "
            f"contre {total_investi:,.0f} DH investi — "
            f"soit **{interets_gen:,.0f} DH d'intérêts générés** (×{multiplicateur:.1f})."
        )
    else:
        message = (
            f"Avec **{capital_i:,.0f} DH** placés à **{taux_a*100:.0f}%/an** "
            f"pendant **{annees} ans**, ton capital atteint **{capital_avec:,.0f} DH** "
            f"(+{interets_gen:,.0f} DH d'intérêts)."
        )

    return {
        "type":           RenderType.SIM_INTERETS,
        "series":         series,
        "capital_final":  round(capital_avec, 2),
        "total_investi":  round(total_investi, 2),
        "interets_gen":   round(interets_gen, 2),
        "multiplicateur": round(multiplicateur, 2),
        "inputs":         inputs,
        "message":        message,
    }


DATA_RESOLVERS: Dict[str, Any] = {

    # ── A1 : Répartition du mois ──────────────────────────────────────────────
    "repartition_mois": lambda ctx, inputs: {
        "type":    RenderType.REPARTITION,
        "rept":    ctx.get("rept", []),
        "mois_lbl": ctx.get("mois_lbl", ""),
        "message": (
            f"Voici comment se répartissent tes {_dh(ctx['bilan']['depenses'])} "
            f"de dépenses ce mois-ci."
        ) if ctx.get("rept") else "Aucune dépense enregistrée ce mois.",
    },

    # ── A2 : Top dépenses ────────────────────────────────────────────────────
    "top_depenses": lambda ctx, inputs: (
        lambda res: {
            "type":    RenderType.TOP_DEPENSES,
            "data":    res.get("resultat", []),
            "mois_lbl": ctx.get("mois_lbl", ""),
            "message": (
                f"Voici tes {len(res.get('resultat', []))} plus grosses dépenses ce mois."
            ) if res.get("resultat") else "Aucune dépense à afficher.",
        }
    )(ctx["_q"]("grosses_depenses", mois=ctx["mois_sel"],
                 top_n=inputs.get("top_n", 10))),

    # ── A3 : Évolution mensuelle ─────────────────────────────────────────────
    "evolution_mensuelle": lambda ctx, inputs: (
        lambda res: {
            "type":    RenderType.EVOLUTION,
            "data":    res.get("resultat", []),
            "message": (
                "Voici l'évolution de tes revenus, dépenses et solde mois par mois."
            ) if res.get("resultat") else
                "Pas encore assez d'historique — reviens le mois prochain.",
        }
    )(ctx["_q"]("evolution_mensuelle")),

    # ── A4 : Tendances par jour ───────────────────────────────────────────────
    "tendances_jours": lambda ctx, inputs: (
        lambda res: {
            "type":    RenderType.TENDANCES_JOURS,
            "data":    res.get("resultat", []),
            "mois_lbl": ctx.get("mois_lbl", ""),
            "message": (
                "Analyse de tes habitudes de dépenses par jour de la semaine."
            ) if res.get("resultat") else
                "Pas encore assez de données pour ce mois.",
        }
    )(ctx["_q"]("tendances_jours", mois=ctx["mois_sel"])),

    # ── B1 : Épargne & objectifs ──────────────────────────────────────────────
    "epargne_objectifs": lambda ctx, inputs: {
        "type":      RenderType.EPARGNE,
        "cumul":     ctx["bilan"].get("epargne_cumul", 0),
        "objectifs": ctx["audit"].get_objectifs("EN_COURS"),
        "message": (
            f"Épargne cumulée : {_dh(ctx['bilan'].get('epargne_cumul', 0))}. "
            + (f"{len(ctx['audit'].get_objectifs('EN_COURS'))} objectif(s) actif(s)."
               if ctx["audit"].get_objectifs("EN_COURS")
               else "Aucun objectif actif pour l'instant.")
        ),
    },

    # ── B2 : Alertes & budget vs réel ────────────────────────────────────────
    "alertes_budget": lambda ctx, inputs: (
        lambda bvr: {
            "type":    RenderType.ALERTES_BUDGET,
            "alertes": ctx.get("alertes", []),
            "bvr":     bvr.get("resultat", []),
            "badges":  ctx.get("badges", {}),
            "mois_lbl": ctx.get("mois_lbl", ""),
            "message": (
                f"🚨 {len(ctx.get('alertes', []))} alerte(s) active(s) ce mois."
                if ctx.get("alertes")
                else "✅ Aucun plafond dépassé ce mois — bonne gestion !"
            ),
        }
    )(ctx["_q"]("budget_vs_reel", mois=ctx["mois_sel"])),

    # ── B3 : Comparaison vs habitudes ─────────────────────────────────────────
    "comparaison_habitudes": lambda ctx, inputs: (
        lambda res: {
            "type":    RenderType.COMPARAISON,
            "data":    res.get("resultat", []),
            "mois_lbl": ctx.get("mois_lbl", ""),
            "message": (
                "Comparaison de tes dépenses ce mois vs la moyenne des 3 derniers mois."
            ) if res.get("resultat") else
                "Pas encore assez d'historique pour comparer.",
        }
    )(ctx["_q"]("comparaison_habitudes",
                 mois=ctx["mois_sel"],
                 nb_mois_ref=inputs.get("nb_mois_ref", 3))),

    # ── B4 : Projection fin de mois ───────────────────────────────────────────
    "projection_mois": lambda ctx, inputs: (
        lambda charges: {
            "type":    RenderType.PROJECTION,
            "proj":    ctx.get("proj", {}),
            "bilan":   ctx.get("bilan", {}),
            "charges": charges.get("resultat", []),
            "mois_lbl": ctx.get("mois_lbl", ""),
            "message": (
                f"À ce rythme, tu dépenseras "
                f"{_dh(ctx['proj'].get('projection_fin_mois', 0))} ce mois "
                f"({ctx['proj'].get('pct_mois_ecoule', 0):.0f}% du mois écoulé)."
            ) if ctx.get("proj") else "Projection indisponible.",
        }
    )(ctx["_q"]("charges_fixes", nb_mois_min=2)),

    # ── C1 : Simulation impact projet ─────────────────────────────────────────
    "sim_impact_projet": lambda ctx, inputs: (
        lambda res: {
            "type":    RenderType.SIM_IMPACT,
            "data":    res.get("resultat", {}),
            "inputs":  inputs,
            "message": (
                f"Simulation d'un achat de {_dh(inputs.get('montant_projet', 0))} "
                f"sur {inputs.get('mois_cibles', 12)} mois."
            ),
        }
    )(ctx["_q"]("impact_projet",
                 montant_projet=inputs.get("montant_projet", 15000.0),
                 mois_cibles=int(inputs.get("mois_cibles", 12)))),

    # ── C2 : Simulation objectif épargne ──────────────────────────────────────
    "sim_objectif_epargne": lambda ctx, inputs: (
        lambda res: {
            "type":    RenderType.SIM_OBJECTIF,
            "data":    res.get("resultat", {}),
            "inputs":  inputs,
            "audit":   ctx["audit"],
            "message": (
                f"Pour épargner {_dh(inputs.get('cible_dh', 0))} "
                f"en {inputs.get('nb_mois', 24)} mois."
            ),
        }
    )(ctx["_q"]("objectif_epargne",
                 cible_dh=inputs.get("cible_dh", 50000.0),
                 nb_mois=int(inputs.get("nb_mois", 24)))),

    # ── C3 : Crash test ──────────────────────────────────────────────────────
    "sim_crash_test": lambda ctx, inputs: (
        lambda res: {
            "type":    RenderType.SIM_CRASH,
            "data":    res.get("resultat", {}),
            "inputs":  inputs,
            "message": (
                f"Simulation de {inputs.get('nb_mois_sans_revenu', 3)} mois "
                f"sans aucun revenu."
            ),
        }
    )(ctx["_q"]("crash_test",
                 nb_mois_sans_revenu=int(inputs.get("nb_mois_sans_revenu", 3)))),

    # ── C4 : Mes objectifs ────────────────────────────────────────────────────
    "mes_objectifs": lambda ctx, inputs: {
        "type":      RenderType.MES_OBJECTIFS,
        "objectifs": ctx["audit"].get_objectifs(),
        "audit":     ctx["audit"],
        "message": (
            f"{len(ctx['audit'].get_objectifs('EN_COURS'))} objectif(s) en cours."
            if ctx["audit"].get_objectifs("EN_COURS")
            else "Aucun objectif actif. Crée-en un via la simulation C2."
        ),
    },

    # ── A5 : Burn Rate ────────────────────────────────────────────────────────
    "burn_rate": _resolve_burn_rate,

    # ── C5 : Intérêts composés ────────────────────────────────────────────────
    "sim_interets_composes": _resolve_sim_interets,
}


# ─────────────────────────────────────────────────────────────────────────────
# ASSISTANT ENGINE — ORCHESTRATEUR
# ─────────────────────────────────────────────────────────────────────────────

class AssistantEngine:
    """
    Orchestre la navigation dans l'arbre et l'exécution des resolvers.

    Usage :
        engine = AssistantEngine()
        node   = engine.get_node("A1")
        result = engine.resolve("A1", ctx, inputs={})
    """

    def __init__(self, tree: Dict = None, resolvers: Dict = None):
        self._tree      = tree      or DECISION_TREE
        self._resolvers = resolvers or DATA_RESOLVERS
        self._parent_map = self._build_parent_map()

    # ── Navigation ────────────────────────────────────────────────────────────

    def get_node(self, node_id: str) -> Dict[str, Any]:
        """Retourne le nœud ou raise KeyError."""
        return self._tree[node_id]

    def get_children(self, node_id: str) -> List[Dict[str, Any]]:
        """Retourne la liste des nœuds enfants."""
        ids = self._tree.get(node_id, {}).get("children", [])
        return [self._tree[cid] for cid in ids if cid in self._tree]

    def get_parent_id(self, node_id: str) -> Optional[str]:
        """Retourne l'id du parent, ou None pour la racine."""
        return self._parent_map.get(node_id)

    def is_leaf(self, node_id: str) -> bool:
        return not bool(self._tree.get(node_id, {}).get("children"))

    def breadcrumb(self, path: List[str]) -> List[Dict[str, str]]:
        """
        Retourne la liste de {id, label} pour afficher le fil d'Ariane.
        path = ["A", "A1"] → [{"id":"root","label":"Accueil"},
                               {"id":"A","label":"🔍 Analyser"},
                               {"id":"A1","label":"📊 Répartition"}]
        """
        crumbs = [{"id": "root", "label": "Accueil"}]
        for nid in path:
            if nid in self._tree:
                crumbs.append({
                    "id":    nid,
                    "label": self._tree[nid]["label"],
                })
        return crumbs

    # ── Exécution ─────────────────────────────────────────────────────────────

    def resolve(
        self,
        node_id: str,
        ctx:     Dict[str, Any],
        inputs:  Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Exécute le resolver du nœud feuille et retourne le résultat.

        Retourne {"error": str} si le nœud n'a pas de resolver
        ou si une exception est levée.
        """
        inputs = inputs or {}
        node   = self._tree.get(node_id)
        if not node:
            return {"type": "ERROR", "message": f"Nœud '{node_id}' inconnu."}

        fn_key = node.get("data_fn")
        if not fn_key:
            return {"type": "ERROR", "message": f"'{node_id}' n'est pas une feuille."}

        resolver = self._resolvers.get(fn_key)
        if not resolver:
            return {"type": "ERROR", "message": f"Resolver '{fn_key}' introuvable."}

        try:
            return resolver(ctx, inputs)
        except Exception as exc:
            return {
                "type":    "ERROR",
                "message": f"Erreur lors de l'exécution de '{fn_key}' : {exc}",
            }

    # ── Helpers privés ────────────────────────────────────────────────────────

    def _build_parent_map(self) -> Dict[str, str]:
        """Construit un index enfant → parent depuis l'arbre."""
        mapping: Dict[str, str] = {}
        for nid, node in self._tree.items():
            for child_id in node.get("children", []):
                mapping[child_id] = nid
        return mapping


# ═══════════════════════════════════════════════════════════════════════════════
# COACH SCORING ENGINE (v2 — 5 facteurs, ctx pour core/coach_messages.py)
# ═══════════════════════════════════════════════════════════════════════════════

from datetime import date as _date, datetime as _dt
from config import (
    SCORE_V2_POIDS_RESTE,
    SCORE_V2_POIDS_EPARGNE_FLOW,
    SCORE_V2_POIDS_FONDS_URGENCE,
    SCORE_V2_POIDS_503020,
    SCORE_V2_POIDS_ENGAGEMENT,
    SCORE_V2_RESTE_RATIO_TARGET,
    SCORE_V2_TAUX_EPARGNE_TARGET,
    SCORE_V2_STREAK_DAYS_TARGET,
    SCORE_V2_CAP_RESTE_NEGATIF,
    SCORE_V2_BASELINE_PREMIER_MOIS,
    SCORE_V2_STALE_DAYS,
    DEFAULT_TARGET_MOIS_SECURITE,
    DEFAULT_503020_MAPPING,
    CAT_TYPE_BESOIN, CAT_TYPE_ENVIE, CAT_TYPE_EPARGNE,
    SCORE_NIVEAU_EXCELLENT, SCORE_NIVEAU_BON,
    SCORE_NIVEAU_MOYEN, SCORE_NIVEAU_FAIBLE,
)


def _statut_from_score(score: float) -> str:
    if score >= SCORE_NIVEAU_EXCELLENT: return "EXCELLENT"
    if score >= SCORE_NIVEAU_BON:       return "BON"
    if score >= SCORE_NIVEAU_MOYEN:     return "MOYEN"
    if score >= SCORE_NIVEAU_FAIBLE:    return "FAIBLE"
    return "CRITIQUE"


def _jours_depuis_iso(iso_date_str: Optional[str]) -> int:
    """Days since an ISO date string (YYYY-MM-DD). Returns 999 if invalid/None."""
    if not iso_date_str:
        return 999
    try:
        d = _dt.strptime(iso_date_str, "%Y-%m-%d").date()
        return (_date.today() - d).days
    except Exception:
        return 999


def _load_503020_overrides(audit) -> dict:
    """User-defined per-category 50/30/20 overrides from PREFERENCES."""
    import json
    raw = audit.db.get_preference("cat_503020_overrides_json", audit.user_id, "{}")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _compute_503020_split(audit, mois: str) -> tuple:
    """
    Compute (pct_besoins, pct_envies, pct_epargne_split, nb_unclassified, top_dep_cat).

    Algo:
      - For each category in this month's spending:
        - User override (PREFERENCES.cat_503020_overrides_json) takes precedence
        - Else fall back to DEFAULT_503020_MAPPING
        - Else: count as unclassified (do NOT include in pct calc)
      - Pct computed only over classified amounts.
    """
    try:
        repart = audit.moteur.get_repartition_par_categorie(mois)
    except Exception:
        return (0.0, 0.0, 0.0, 0, "")

    if repart.empty:
        return (0.0, 0.0, 0.0, 0, "")

    overrides = _load_503020_overrides(audit)
    sums = {CAT_TYPE_BESOIN: 0.0, CAT_TYPE_ENVIE: 0.0, CAT_TYPE_EPARGNE: 0.0}
    nb_unclassified = 0

    for _, row in repart.iterrows():
        cat = row.get("Categorie") or ""
        amt = float(row.get("Total_DH") or 0)
        # Override wins over default mapping
        cat_type = overrides.get(cat) or DEFAULT_503020_MAPPING.get(cat)
        if cat_type is None or cat_type not in sums:
            nb_unclassified += 1
            continue
        sums[cat_type] += amt

    total_classified = sum(sums.values())
    if total_classified <= 0:
        return (0.0, 0.0, 0.0, nb_unclassified,
                str(repart.iloc[0]["Categorie"]) if not repart.empty else "")

    return (
        sums[CAT_TYPE_BESOIN]  / total_classified,
        sums[CAT_TYPE_ENVIE]   / total_classified,
        sums[CAT_TYPE_EPARGNE] / total_classified,
        nb_unclassified,
        str(repart.iloc[0]["Categorie"]),
    )


def compute_score(audit, mois: Optional[str] = None) -> Dict[str, Any]:
    """
    Coach scoring engine v2 — returns the full ctx for core.coach_messages.

    5 factors (100 pts total):
      1. Reste à vivre   (25 pts) — post-abonnements ratio
      2. Épargne du mois (15 pts) — flow
      3. Fonds d'urgence (20 pts) — stock vs target_mois_secu
      4. Règle 50/30/20  (25 pts) — only if onboarding done AND no unclassified cats
      5. Engagement      (15 pts) — daily streak

    Edge cases applied:
      - Reste négatif → score capped at SCORE_V2_CAP_RESTE_NEGATIF (40 = FAIBLE max)
      - Compte < 30j sans data → SCORE_V2_BASELINE_PREMIER_MOIS (50)
      - Onboarding pas fait → 25 pts du 50/30/20 redistribués (+15 reste, +5 flow, +5 stock)
      - jours_inactif ≥ SCORE_V2_STALE_DAYS → score_stale = True (UI flag, pas pénalité)
    """
    user_id = audit.user_id
    db      = audit.db
    moteur  = audit.moteur

    if mois is None:
        now = _dt.now()
        mois = f"{now.month:02d}/{now.year}"

    # ── Pull raw data via existing helpers ────────────────────────────────────
    try:
        bilan = moteur.get_bilan_mensuel(mois)
        revenus  = float(getattr(bilan, "revenus", 0) or 0)
        depenses = float(getattr(bilan, "depenses", 0) or 0)
    except Exception:
        revenus, depenses = 0.0, 0.0

    # Abonnements (charges fixes auto-détectées, ≥ 2 mois)
    try:
        cf = moteur.get_charges_fixes(nb_mois_min=2)
        abonnements = float(cf["Montant_Moyen"].sum()) if not cf.empty else 0.0
    except Exception:
        abonnements = 0.0

    # Épargne du mois
    try:
        ep_rec = db.get_epargne_mois(user_id, mois)
        epargne_mois = float(ep_rec.get("Montant_Reel", 0) or 0) if ep_rec else 0.0
    except Exception:
        epargne_mois = 0.0

    # Épargne libre (totale - allouée aux objectifs)
    try:
        epargne_total = db.get_cumul_epargne(user_id)
    except Exception:
        epargne_total = 0.0
    try:
        goals = db.get_objectifs(user_id)
        epargne_allouee = sum(
            float(g.get("montant_actuel") or g.get("Montant_Actuel") or 0) for g in goals
        )
    except Exception:
        epargne_allouee = 0.0
    epargne_libre = max(0.0, epargne_total - epargne_allouee)

    # Dépense moyenne 3 mois (pour fonds d'urgence)
    try:
        depense_moy = float(moteur._depenses_mensuelles_moyennes(nb_mois=3))
    except Exception:
        depense_moy = depenses if depenses > 0 else 1.0

    # Engagement
    streak_jours = int(db.get_preference("streak_jours", user_id, "0") or 0)
    streak_last  = db.get_preference("streak_last_active", user_id, None)
    jours_inactif = _jours_depuis_iso(streak_last) if streak_last else 0

    # Onboarding & inscription
    onboarding_done = (db.get_preference("onboarding_done", user_id, "0") or "0") in ("1", "True", "true")
    date_inscription = db.get_user_date_creation(user_id)
    jours_depuis_inscription = (
        (_date.today() - date_inscription).days if date_inscription else 999
    )

    # Mois verts
    mois_verts = int(db.get_preference("mois_verts", user_id, "0") or 0)

    # Target fonds d'urgence (customizable per user)
    target_mois_secu = float(
        db.get_preference("fonds_urgence_target_mois", user_id, str(DEFAULT_TARGET_MOIS_SECURITE))
        or DEFAULT_TARGET_MOIS_SECURITE
    )

    # 50/30/20 split + unclassified count
    pct_besoins, pct_envies, pct_epargne_split, nb_unclassified, cat_top = (
        _compute_503020_split(audit, mois)
    )

    # ── Derived ratios ────────────────────────────────────────────────────────
    reste_a_vivre = revenus - depenses - abonnements
    reste_ratio   = (reste_a_vivre / revenus) if revenus > 0 else 0.0
    taux_epargne  = (epargne_mois / revenus) if revenus > 0 else 0.0
    mois_securite = (epargne_libre / depense_moy) if depense_moy > 0 else 0.0
    ratio_target  = (mois_securite / target_mois_secu) if target_mois_secu > 0 else 0.0

    # ── Compute factor points ────────────────────────────────────────────────
    pts_reste = min(
        SCORE_V2_POIDS_RESTE,
        max(0.0, reste_ratio / SCORE_V2_RESTE_RATIO_TARGET * SCORE_V2_POIDS_RESTE),
    )
    pts_ep_flow = min(
        SCORE_V2_POIDS_EPARGNE_FLOW,
        max(0.0, taux_epargne / SCORE_V2_TAUX_EPARGNE_TARGET * SCORE_V2_POIDS_EPARGNE_FLOW),
    )
    pts_fonds = min(
        SCORE_V2_POIDS_FONDS_URGENCE,
        max(0.0, ratio_target * SCORE_V2_POIDS_FONDS_URGENCE),
    )

    # 50/30/20 — locked at 0 if unclassified or onboarding not done
    if onboarding_done and nb_unclassified == 0 and (pct_besoins + pct_envies + pct_epargne_split) > 0:
        # Distance from ideal (0.50 / 0.30 / 0.20). Max ~2.0 (way off), 0 = perfect.
        dist = (
            abs(pct_besoins - 0.50) +
            abs(pct_envies  - 0.30) +
            abs(pct_epargne_split - 0.20)
        )
        pts_503020 = max(0.0, SCORE_V2_POIDS_503020 * (1 - dist / 2))
    else:
        pts_503020 = 0.0
        # Redistribute 25 pts if onboarding NOT done (independent of unclassified state)
        if not onboarding_done:
            pts_reste   = min(SCORE_V2_POIDS_RESTE + 15, pts_reste + 15)
            pts_ep_flow = min(SCORE_V2_POIDS_EPARGNE_FLOW + 5, pts_ep_flow + 5)
            pts_fonds   = min(SCORE_V2_POIDS_FONDS_URGENCE + 5, pts_fonds + 5)

    # Engagement — first-week grace: new users get full marks until they have
    # had 7 days to build a real streak. After day 7, normal calculation kicks in.
    if jours_depuis_inscription < 7:
        pts_engagement = SCORE_V2_POIDS_ENGAGEMENT
    else:
        pts_engagement = min(
            SCORE_V2_POIDS_ENGAGEMENT,
            max(0.0, streak_jours / SCORE_V2_STREAK_DAYS_TARGET * SCORE_V2_POIDS_ENGAGEMENT),
        )

    # ── Total + edge cases ───────────────────────────────────────────────────
    score = pts_reste + pts_ep_flow + pts_fonds + pts_503020 + pts_engagement

    # First-month grace: nouveau compte sans data réelle → baseline 50
    if jours_depuis_inscription < 30 and revenus < 100 and depenses < 100:
        score = SCORE_V2_BASELINE_PREMIER_MOIS

    # Reste à vivre négatif → cap au max FAIBLE (40)
    if reste_a_vivre < 0:
        score = min(score, SCORE_V2_CAP_RESTE_NEGATIF)

    score = round(min(100.0, max(0.0, score)), 1)
    statut = _statut_from_score(score)
    score_stale = jours_inactif >= SCORE_V2_STALE_DAYS

    return {
        # Score & status
        "score":   score,
        "statut":  statut,
        "score_stale": score_stale,

        # Factor 1
        "reste_a_vivre": round(reste_a_vivre, 2),
        "reste_ratio":   round(reste_ratio, 4),

        # Factor 2 + 3
        "epargne_mois":     round(epargne_mois, 2),
        "taux_epargne":     round(taux_epargne, 4),
        "epargne_libre":    round(epargne_libre, 2),
        "depense_moy_mois": round(depense_moy, 2),
        "mois_securite":    round(mois_securite, 2),
        "target_mois_secu": target_mois_secu,
        "ratio_target":     round(ratio_target, 4),

        # Factor 4
        "pct_besoins":          round(pct_besoins, 4),
        "pct_envies":           round(pct_envies, 4),
        "pct_epargne_split":    round(pct_epargne_split, 4),
        "nb_unclassified_cats": nb_unclassified,

        # Factor 5
        "streak_jours":  streak_jours,
        "jours_inactif": jours_inactif,

        # State
        "onboarding_done":          onboarding_done,
        "jours_depuis_inscription": jours_depuis_inscription,
        "mois_verts":               mois_verts,

        # Advice tailoring
        "categorie_top_dep": cat_top,

        # Internal breakdown (for debug / UI)
        "details_score": {
            "pts_reste":      round(pts_reste, 1),
            "pts_ep_flow":    round(pts_ep_flow, 1),
            "pts_fonds":      round(pts_fonds, 1),
            "pts_503020":     round(pts_503020, 1),
            "pts_engagement": round(pts_engagement, 1),
        },
    }
