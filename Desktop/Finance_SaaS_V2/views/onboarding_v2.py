"""
views/onboarding_v2.py — New onboarding wizard (4 steps, value-first).

Steps:
    1. Bienvenue + Coach + Revenu  (welcome, default coach BATISSEUR, salaire/extras)
    2. Récurrents déjà payés        (preset list incl. Crédit + Daret + custom rows)
                                     → creates real TRANSACTIONS for current month
    3. Estimation rapide            (4 sliders: logement, vie quotidienne, envies, épargne)
                                     → stored in PREFERENCES.est_* (suggested plafonds later)
    4. Premier objectif + Épargne actuelle + Score reveal
                                     → creates OBJECTIFS row + EPARGNE_HISTO initial cumul
                                     → shows compute_score() result with full breakdown

Mini-académie removed from wizard — concepts taught via core/hints.py contextually.

Old onboarding (3-step, views/onboarding.py) kept as legacy fallback via ?onboarding=v1.
"""

from __future__ import annotations
from datetime import date

import streamlit as st

from components.design_tokens import T
from components.helpers import dh as _dh
from core import badges as _badges
from core.cache import invalider as _invalider_cache
from config import (
    MA_REF_ENTRETIEN_PCT,
    MA_REF_ALIMENTATION_PCT,
    MA_REF_TRANSPORT_PCT,
    MA_REF_ENVIES_PCT,
    MA_REF_EPARGNE_PCT,
)


# ── Session state keys ──────────────────────────────────────────────────────
_STEP_KEY = "ob2_step"   # current step (1–4)
_DATA_KEY = "ob2_data"   # collected wizard data (revenu, estimations)


# ── Recurring expense presets for step 2 ────────────────────────────────────
RECURRENT_PRESETS = [
    {"key": "loyer",     "label": "Loyer / Crédit logement",            "icon": "🏠"},
    {"key": "utilities", "label": "Électricité + Eau (utilities)",      "icon": "⚡"},
    {"key": "internet",  "label": "Internet",                           "icon": "📡"},
    {"key": "telephone", "label": "Téléphone",                          "icon": "📱"},
    {"key": "streaming", "label": "Streaming (Netflix, Spotify…)",      "icon": "📺"},
    {"key": "gym",       "label": "Gym / Sport",                        "icon": "🏋️"},
    {"key": "banque",    "label": "Frais bancaires mensuels",           "icon": "🏦"},
    {"key": "assurance", "label": "Assurance",                          "icon": "🛡️"},
    {"key": "credit",    "label": "Crédit (autre)",                     "icon": "💳"},
    {"key": "daret",     "label": "Daret (montant mensuel)",            "icon": "🔄"},
]

_TOTAL_STEPS = 4


# ── Helpers ─────────────────────────────────────────────────────────────────
def _get_step() -> int:
    return int(st.session_state.get(_STEP_KEY, 1))


def _set_step(n: int) -> None:
    st.session_state[_STEP_KEY] = n
    st.rerun()


def _data() -> dict:
    if _DATA_KEY not in st.session_state:
        st.session_state[_DATA_KEY] = {}
    return st.session_state[_DATA_KEY]


def _first_of_month() -> date:
    today = date.today()
    return date(today.year, today.month, 1)


def _progress(step: int, total: int = _TOTAL_STEPS) -> None:
    pct = int(step / total * 100)
    st.markdown(
        f'<div style="margin-bottom:24px">'
        f'  <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px">'
        f'    <span style="color:{T.TEXT_LOW};font-size:11px;font-weight:700;'
        f'      text-transform:uppercase;letter-spacing:1.5px">Étape {step} / {total}</span>'
        f'    <span style="color:{T.PRIMARY};font-size:11px;font-weight:700">{pct}%</span>'
        f'  </div>'
        f'  <div style="height:4px;background:{T.BG_INPUT};border-radius:99px;overflow:hidden">'
        f'    <div style="width:{pct}%;height:100%;background:{T.PRIMARY};'
        f'      transition:width 0.3s ease"></div>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════════════════
# STEP 1 — Bienvenue + Coach + Revenu
# ════════════════════════════════════════════════════════════════════════════
def _step1_welcome_revenu(audit) -> None:
    d = _data()

    # Welcome banner
    st.markdown(
        f'<div style="text-align:center;padding:18px 0 10px">'
        f'  <div style="font-size:38px;margin-bottom:8px">👋</div>'
        f'  <div style="color:{T.TEXT_HIGH};font-size:22px;font-weight:700;margin-bottom:6px">'
        f'    Bienvenue sur Finance SaaS</div>'
        f'  <div style="color:{T.TEXT_MED};font-size:13px;line-height:1.5;max-width:460px;margin:0 auto">'
        f'    On configure ton compte en 4 étapes rapides. Ensuite, ton coach prend le relais.'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Coach card (default BATISSEUR)
    st.markdown(
        f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
        f'border-radius:{T.RADIUS_MD};padding:14px 16px;margin:14px 0;'
        f'display:flex;gap:12px;align-items:center">'
        f'  <div style="width:42px;height:42px;border-radius:50%;'
        f'    background:linear-gradient(135deg,{T.PRIMARY},{T.PURPLE});'
        f'    display:grid;place-items:center;color:#0a1020;font-weight:700;font-size:16px">B</div>'
        f'  <div style="flex:1">'
        f'    <div style="color:{T.TEXT_HIGH};font-weight:700;font-size:13px">Coach BATISSEUR</div>'
        f'    <div style="color:{T.TEXT_LOW};font-size:11px;margin-top:1px">'
        f'      Coach par défaut · Modifiable plus tard'
        f'    </div>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Revenu inputs
    st.markdown(
        f'<div style="color:{T.TEXT_HIGH};font-size:14px;font-weight:600;margin:18px 0 8px">'
        f'💰 Tes revenus mensuels</div>',
        unsafe_allow_html=True,
    )

    salaire = st.number_input(
        "Salaire mensuel (DH)",
        min_value=0.0, step=500.0,
        value=float(d.get("salaire", 0)),
        format="%.0f",
        key="ob2_salaire",
    )
    extras = st.number_input(
        "Autres revenus (freelance, location…) — optionnel",
        min_value=0.0, step=200.0,
        value=float(d.get("extras", 0)),
        format="%.0f",
        key="ob2_extras",
    )

    total = salaire + extras
    if total > 0:
        st.markdown(
            f'<div style="background:{T.SUCCESS_GLO};border-left:3px solid {T.SUCCESS};'
            f'padding:10px 14px;border-radius:{T.RADIUS_SM};margin:14px 0">'
            f'  <span style="color:{T.SUCCESS};font-size:12px;font-weight:600">Total mensuel: </span>'
            f'  <span style="color:{T.TEXT_HIGH};font-size:14px;font-weight:700">{_dh(total)} DH</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if st.button("Suivant →", type="primary", use_container_width=True,
                 key="ob2_s1_next", disabled=(total <= 0)):
        d["salaire"]      = salaire
        d["extras"]       = extras
        d["revenu_total"] = total
        audit.db.set_preference("coach_identite", "BATISSEUR", audit.user_id)
        _badges.award_badge(audit, "premier_pas",         "Premier pas",         "🎉")
        _badges.award_badge(audit, "revenus_configures",  "Revenus configurés",  "💰")
        _set_step(2)


# ════════════════════════════════════════════════════════════════════════════
# STEP 2 — Récurrents déjà payés ce mois
# ════════════════════════════════════════════════════════════════════════════
def _init_recurrents_state() -> None:
    if "ob2_recurrents" not in st.session_state:
        st.session_state.ob2_recurrents = {
            p["key"]: {"checked": False, "amount": 0.0, "date": _first_of_month()}
            for p in RECURRENT_PRESETS
        }
    if "ob2_customs" not in st.session_state:
        st.session_state.ob2_customs = []


def _step2_recurrents(audit) -> None:
    _init_recurrents_state()

    st.markdown(
        f'<div style="margin-bottom:14px">'
        f'  <div style="color:{T.TEXT_HIGH};font-size:20px;font-weight:700;margin-bottom:6px">'
        f'    🔄 Tes dépenses récurrentes ce mois</div>'
        f'  <div style="color:{T.TEXT_MED};font-size:13px;line-height:1.5">'
        f"    Coche ce que tu as déjà payé depuis le 1<sup>er</sup> du mois."
        f'    Ces dépenses seront ajoutées automatiquement à ton historique.'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Preset rows
    for preset in RECURRENT_PRESETS:
        key   = preset["key"]
        state = st.session_state.ob2_recurrents[key]

        c1, c2, c3 = st.columns([3, 2, 1.5])
        with c1:
            state["checked"] = st.checkbox(
                f"{preset['icon']}  {preset['label']}",
                value=state["checked"],
                key=f"ob2_rec_chk_{key}",
            )
        with c2:
            if state["checked"]:
                state["amount"] = st.number_input(
                    f"Montant {key}",
                    min_value=0.0, step=50.0,
                    value=float(state["amount"]),
                    format="%.0f",
                    key=f"ob2_rec_amt_{key}",
                    label_visibility="collapsed",
                    placeholder="DH",
                )
        with c3:
            if state["checked"]:
                state["date"] = st.date_input(
                    f"Date {key}",
                    value=state["date"],
                    key=f"ob2_rec_date_{key}",
                    label_visibility="collapsed",
                )

    # Custom rows
    st.markdown(
        f'<div style="border-top:1px solid {T.BORDER};margin:18px 0 10px"></div>',
        unsafe_allow_html=True,
    )

    for i, custom in enumerate(st.session_state.ob2_customs):
        c1, c2, c3, c4 = st.columns([3, 2, 1.3, 0.5])
        with c1:
            custom["label"] = st.text_input(
                f"Libellé custom {i}",
                value=custom["label"],
                key=f"ob2_custom_lbl_{i}",
                placeholder="Ex: Cours d'arabe",
                label_visibility="collapsed",
            )
        with c2:
            custom["amount"] = st.number_input(
                f"Montant custom {i}",
                min_value=0.0, step=50.0,
                value=float(custom["amount"]),
                format="%.0f",
                key=f"ob2_custom_amt_{i}",
                label_visibility="collapsed",
            )
        with c3:
            custom["date"] = st.date_input(
                f"Date custom {i}",
                value=custom["date"],
                key=f"ob2_custom_date_{i}",
                label_visibility="collapsed",
            )
        with c4:
            if st.button("✕", key=f"ob2_custom_del_{i}",
                         help="Supprimer cette ligne"):
                st.session_state.ob2_customs.pop(i)
                st.rerun()

    if st.button("➕ Ajouter une autre dépense récurrente",
                 key="ob2_add_custom", use_container_width=True):
        st.session_state.ob2_customs.append({
            "label":  "",
            "amount": 0.0,
            "date":   _first_of_month(),
        })
        st.rerun()

    # Total
    total_preset = sum(
        r["amount"] for r in st.session_state.ob2_recurrents.values() if r["checked"]
    )
    total_custom = sum(
        c["amount"] for c in st.session_state.ob2_customs if c["label"].strip()
    )
    total = total_preset + total_custom

    if total > 0:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_MD};padding:12px 16px;margin:14px 0;'
            f'display:flex;justify-content:space-between;align-items:center">'
            f'  <span style="color:{T.TEXT_LOW};font-size:11px;font-weight:700;'
            f'    text-transform:uppercase;letter-spacing:1px">Total déclaré</span>'
            f'  <span style="color:{T.WARNING};font-size:16px;font-weight:900">'
            f'    {_dh(total)} DH</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Navigation
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("← Retour", key="ob2_s2_back", use_container_width=True):
            _set_step(1)
    with c2:
        # "Suivant" always enabled — user might genuinely have nothing to declare
        if st.button("Suivant →", type="primary", use_container_width=True,
                     key="ob2_s2_next"):
            count = _create_recurrent_transactions(audit)
            _data()["nb_recurrents"] = count
            _badges.award_badge(audit, "recurrents_logged",
                                "Récurrents enregistrés", "🔄")
            _set_step(3)


def _create_recurrent_transactions(audit) -> int:
    """Create real TRANSACTIONS for each checked preset + non-empty custom row."""
    count = 0

    # Presets
    for key, item in st.session_state.ob2_recurrents.items():
        if not item["checked"] or item["amount"] <= 0:
            continue
        preset = next(p for p in RECURRENT_PRESETS if p["key"] == key)
        try:
            res = audit.recevoir(
                preset["label"],
                float(item["amount"]),
                "OUT",
                item["date"],
                forcer=True,
                source="ONBOARDING_RECURRENT",
            )
            if res.get("action") == "OK":
                count += 1
        except Exception:
            pass  # silent skip — onboarding shouldn't crash on one bad row

    # Customs
    for custom in st.session_state.ob2_customs:
        if not custom["label"].strip() or custom["amount"] <= 0:
            continue
        try:
            res = audit.recevoir(
                custom["label"].strip(),
                float(custom["amount"]),
                "OUT",
                custom["date"],
                forcer=True,
                source="ONBOARDING_RECURRENT",
            )
            if res.get("action") == "OK":
                count += 1
        except Exception:
            pass

    return count


# ── Donut renderer for step 3 — live visual feedback ───────────────────────
def _render_estimation_donut(
    entretien: float, alimentation: float, transport: float,
    envies: float, epargne: float, reste: float, revenu: float,
) -> None:
    """Plotly donut that takes shape as user moves the sliders."""
    if revenu <= 0:
        return

    import plotly.graph_objects as go

    labels = ["🔧 Entretien", "🛒 Alimentation", "🚗 Transport",
              "🎁 Envies", "💰 Épargne", "🆓 Reste"]
    values = [entretien, alimentation, transport, envies, epargne, reste]
    colors = [T.WARNING, T.PRIMARY, T.BLUE, T.PURPLE, T.SUCCESS, T.TEXT_MUTED]

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.65,
        marker=dict(colors=colors, line=dict(color=T.BG_PAGE, width=2)),
        textinfo="none",
        hovertemplate="%{label}<br>%{value:,.0f} DH<br>%{percent}<extra></extra>",
        sort=False,
    )])

    fig.update_layout(
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="middle", y=0.5,
            xanchor="left",   x=1.05,
            font=dict(color=T.TEXT_MED, size=11),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor=T.BG_PAGE,
        plot_bgcolor=T.BG_PAGE,
        margin=dict(t=10, b=10, l=10, r=10),
        height=240,
        annotations=[
            dict(
                text=f"<b style='color:{T.TEXT_HIGH};font-size:18px'>"
                     f"{_dh(revenu)} DH</b><br>"
                     f"<span style='color:{T.TEXT_LOW};font-size:11px'>revenu mensuel</span>",
                x=0.5, y=0.5,
                showarrow=False,
                font=dict(color=T.TEXT_HIGH),
            )
        ],
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ════════════════════════════════════════════════════════════════════════════
# STEP 3 — Estimation rapide (4 sliders incl. Envies)
# ════════════════════════════════════════════════════════════════════════════
def _step3_estimation(audit) -> None:
    d = _data()
    revenu = float(d.get("revenu_total", 0))

    st.markdown(
        f'<div style="margin-bottom:18px">'
        f'  <div style="color:{T.TEXT_HIGH};font-size:20px;font-weight:700;margin-bottom:6px">'
        f'    📊 Estimation rapide</div>'
        f'  <div style="color:{T.TEXT_MED};font-size:13px;line-height:1.5">'
        f"    Combien penses-tu dépenser dans chaque catégorie ce mois-ci&nbsp;?"
        f'    Pas besoin d\'être précis — ça sert juste de baseline.'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    slider_max = int(revenu)

    def _ref(pct: float) -> None:
        if revenu <= 0:
            return
        st.markdown(
            f'<div style="color:{T.TEXT_LOW};font-size:11px;'
            f'margin-top:-6px;margin-bottom:14px">'
            f'Moyenne MA pour ce revenu ≈ {int(revenu * pct)} DH'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Note: Logement (loyer/crédit) déjà capté en step 2 (récurrents) — pas redondant ici.
    entretien = st.slider(
        "🔧 Entretien (maison + voiture)",
        min_value=0, max_value=slider_max,
        value=int(d.get("est_entretien", revenu * MA_REF_ENTRETIEN_PCT)),
        step=50, format="%d DH", key="ob2_entretien",
    )
    _ref(MA_REF_ENTRETIEN_PCT)

    alimentation = st.slider(
        "🛒 Alimentation / Courses",
        min_value=0, max_value=slider_max,
        value=int(d.get("est_alimentation", revenu * MA_REF_ALIMENTATION_PCT)),
        step=100, format="%d DH", key="ob2_alimentation",
    )
    _ref(MA_REF_ALIMENTATION_PCT)

    transport = st.slider(
        "🚗 Transport (carburant, taxi, bus)",
        min_value=0, max_value=slider_max,
        value=int(d.get("est_transport", revenu * MA_REF_TRANSPORT_PCT)),
        step=50, format="%d DH", key="ob2_transport",
    )
    _ref(MA_REF_TRANSPORT_PCT)

    envies = st.slider(
        "🎁 Envies (loisirs, restos, shopping)",
        min_value=0, max_value=slider_max,
        value=int(d.get("est_envies", revenu * MA_REF_ENVIES_PCT)),
        step=100, format="%d DH", key="ob2_envies",
    )
    _ref(MA_REF_ENVIES_PCT)

    epargne = st.slider(
        "💰 Épargne mensuelle visée",
        min_value=0, max_value=slider_max,
        value=int(d.get("est_epargne", revenu * MA_REF_EPARGNE_PCT)),
        step=100, format="%d DH", key="ob2_epargne",
    )
    _ref(MA_REF_EPARGNE_PCT)

    reste = revenu - entretien - alimentation - transport - envies - epargne
    reste_color = T.SUCCESS if reste >= 0 else T.DANGER
    reste_lbl   = "Marge" if reste >= 0 else "Dépassement"

    # Live donut — takes shape as the user moves sliders
    _render_estimation_donut(
        entretien, alimentation, transport, envies, epargne, max(0.0, reste), revenu
    )

    st.markdown(
        f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
        f'border-radius:{T.RADIUS_MD};padding:14px 16px;margin:14px 0">'
        f'  <div style="display:flex;justify-content:space-between">'
        f'    <span style="color:{T.TEXT_LOW};font-size:11px;font-weight:700;'
        f'      text-transform:uppercase;letter-spacing:1px">{reste_lbl}</span>'
        f'    <span style="color:{reste_color};font-size:14px;font-weight:700">{_dh(reste)} DH</span>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("← Retour", key="ob2_s3_back", use_container_width=True):
            _set_step(2)
    with c2:
        if st.button("Suivant →", type="primary", use_container_width=True,
                     key="ob2_s3_next"):
            d["est_entretien"]    = entretien
            d["est_alimentation"] = alimentation
            d["est_transport"]    = transport
            d["est_envies"]       = envies
            d["est_epargne"]      = epargne
            _badges.award_badge(audit, "profil_depenses", "Profil dépenses", "📊")
            _set_step(4)


# ════════════════════════════════════════════════════════════════════════════
# STEP 4 — Premier objectif + Épargne actuelle + Reveal score
# ════════════════════════════════════════════════════════════════════════════
def _step4_objectif_score(audit) -> None:
    d = _data()
    reveal = bool(st.session_state.get("ob2_reveal", False))

    if not reveal:
        _step4_form(audit, d)
    else:
        _step4_reveal(audit, d)


def _step4_form(audit, d: dict) -> None:
    """Step 4 — first-half: collect objectif + épargne actuelle."""
    from datetime import date as _date, timedelta

    st.markdown(
        f'<div style="margin-bottom:18px">'
        f'  <div style="color:{T.TEXT_HIGH};font-size:20px;font-weight:700;margin-bottom:6px">'
        f'    🎯 Ton premier objectif</div>'
        f'  <div style="color:{T.TEXT_MED};font-size:13px;line-height:1.5">'
        f'    Définis ce que tu veux atteindre. On te révèlera ton score juste après.'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Objectif inputs
    obj_nom = st.text_input(
        "Nom de l'objectif",
        value=d.get("obj_nom", ""),
        placeholder="Ex: Voyage à Istanbul, PC, Mariage…",
        key="ob2_obj_nom",
    )
    c_a, c_b = st.columns(2)
    with c_a:
        obj_montant = st.number_input(
            "Montant cible (DH)",
            min_value=0.0, step=500.0,
            value=float(d.get("obj_montant", 0)),
            format="%.0f",
            key="ob2_obj_montant",
        )
    with c_b:
        default_date = _date.today() + timedelta(days=365)
        obj_date = st.date_input(
            "Date cible",
            value=d.get("obj_date", default_date),
            min_value=_date.today(),
            key="ob2_obj_date",
        )

    # Épargne actuelle
    st.markdown(
        f'<div style="border-top:1px solid {T.BORDER};margin:20px 0 14px;padding-top:14px">'
        f'  <div style="color:{T.TEXT_HIGH};font-size:14px;font-weight:600;margin-bottom:4px">'
        f'    💼 Épargne actuelle</div>'
        f'  <div style="color:{T.TEXT_LOW};font-size:12px">'
        f'    Combien as-tu déjà mis de côté à ce jour ? Ce sera ton point de départ.'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    epargne_actuelle = st.number_input(
        "Épargne déjà accumulée (DH)",
        min_value=0.0, step=500.0,
        value=float(d.get("epargne_actuelle", 0)),
        format="%.0f",
        key="ob2_epargne_actuelle",
    )

    # Validation feedback — tell the user WHY the button is disabled
    obj_valid = bool(obj_nom.strip()) and obj_montant > 0
    if not obj_valid:
        missing = []
        if not obj_nom.strip(): missing.append("**nom de l'objectif**")
        if obj_montant <= 0:    missing.append("**montant cible**")
        st.markdown(
            f'<div style="background:{T.WARNING_GLO};border-left:3px solid {T.WARNING};'
            f'padding:10px 14px;border-radius:{T.RADIUS_SM};margin:14px 0">'
            f'  <span style="color:{T.WARNING};font-size:12px;font-weight:600">⚠️ Champ requis : </span>'
            f'  <span style="color:{T.TEXT_HIGH};font-size:12px">'
            f"    {' et '.join(missing)} pour calculer ton score."
            f'  </span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("← Retour", key="ob2_s4_back", use_container_width=True):
            _set_step(3)
    with c2:
        if st.button("Calculer mon score →", type="primary",
                     use_container_width=True, key="ob2_s4_calc",
                     disabled=not obj_valid):
            d["obj_nom"]          = obj_nom.strip()
            d["obj_montant"]      = obj_montant
            d["obj_date"]         = obj_date
            d["epargne_actuelle"] = epargne_actuelle
            _persist_objectif_and_epargne(audit, d)
            st.session_state["ob2_reveal"] = True
            st.rerun()

    # Skip option — proceed to score reveal without objectif/épargne
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    if st.button("Passer cette étape — je le ferai plus tard",
                 key="ob2_s4_skip", use_container_width=True, type="secondary"):
        # Don't persist objectif/épargne — go straight to the reveal
        st.session_state["ob2_reveal"]      = True
        st.session_state["ob2_skipped_obj"] = True
        st.rerun()


def _persist_objectif_and_epargne(audit, d: dict) -> None:
    """Save objectif + initial épargne BEFORE compute_score so the score reflects them."""
    # Objectif
    try:
        audit.db.creer_objectif(
            d["obj_nom"], float(d["obj_montant"]),
            d["obj_date"].isoformat(), audit.user_id,
        )
    except Exception:
        pass

    # Épargne actuelle as initial EPARGNE_HISTO entry
    if d.get("epargne_actuelle", 0) > 0:
        try:
            from datetime import datetime as _dt
            now = _dt.now()
            mois = f"{now.month:02d}/{now.year}"
            audit.db.sauvegarder_epargne_mois(
                audit.user_id, mois, float(d["epargne_actuelle"])
            )
        except Exception:
            pass


def _step4_reveal(audit, d: dict) -> None:
    """Step 4 — second-half: reveal the initial score with breakdown."""
    from core.assistant_engine import compute_score
    from core.coach_messages import select_message, render_message

    # Import locally to avoid circular imports
    from views.accueil import _statut_color, _STATUT_FR

    # Compute score with all collected data persisted
    try:
        from datetime import datetime as _dt
        now = _dt.now()
        mois = f"{now.month:02d}/{now.year}"
        ctx = compute_score(audit, mois)
    except Exception as e:
        st.error(f"Erreur de calcul du score: {e}")
        if st.button("Continuer quand même →", type="primary",
                     use_container_width=True, key="ob2_skip_reveal"):
            _finalize(audit)
        return

    score_val = float(ctx.get("score", 0))
    statut    = ctx.get("statut", "MOYEN")
    color     = _statut_color(statut)
    statut_fr = _STATUT_FR.get(statut, statut)

    msg_raw = select_message(ctx)
    msg     = render_message(msg_raw, ctx)

    # Big score reveal card
    st.markdown(
        f'<div style="text-align:center;padding:20px 0 10px">'
        f'  <div style="font-size:40px;margin-bottom:8px">🎉</div>'
        f'  <div style="color:{T.TEXT_HIGH};font-size:18px;font-weight:600;margin-bottom:18px">'
        f'    Configuration terminée — voici ton score de départ</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
        f'border-radius:{T.RADIUS_XL};padding:30px 24px;text-align:center;margin-bottom:14px">'
        f'  <div style="color:{color};font-size:64px;font-weight:700;line-height:1;'
        f'    letter-spacing:-0.02em;font-variant-numeric:tabular-nums">{score_val:.0f}'
        f'    <span style="font-size:20px;font-weight:400;color:{T.TEXT_LOW};margin-left:4px">/100</span>'
        f'  </div>'
        f'  <div style="color:{color};font-size:13px;font-weight:700;letter-spacing:0.15em;'
        f'    text-transform:uppercase;margin-top:10px">{statut_fr}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Coach message
    st.markdown(
        f'<div style="background:{T.PRIMARY_GLO};border-left:3px solid {T.PRIMARY};'
        f'border-radius:{T.RADIUS_MD};padding:14px 18px;margin:14px 0">'
        f'  <div style="color:{T.TEXT_HIGH};font-size:13px;line-height:1.55;margin-bottom:6px">'
        f'    {msg["message"]}</div>'
        f'  <div style="color:{T.TEXT_MED};font-size:12px;line-height:1.55">'
        f'    💡 {msg["advice"]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Factor breakdown
    details = ctx.get("details_score", {})
    st.markdown(
        f'<div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:1.5px;margin:18px 0 8px">'
        f'Détail des 5 facteurs</div>',
        unsafe_allow_html=True,
    )

    rows = [
        ("Reste à vivre",       details.get("pts_reste",      0), 25),
        ("Épargne du mois",     details.get("pts_ep_flow",    0), 15),
        ("Fonds d'urgence",     details.get("pts_fonds",      0), 20),
        ("Dépenses équilibrées", details.get("pts_503020",    0), 25),
        ("Engagement",          details.get("pts_engagement", 0), 15),
    ]
    rows_html = ""
    for label, pts, max_pts in rows:
        pct = (pts / max_pts * 100) if max_pts > 0 else 0
        bar_color = T.SUCCESS if pct >= 70 else T.PRIMARY if pct >= 40 else T.WARNING if pct >= 20 else T.DANGER
        rows_html += (
            f'<div style="margin-bottom:10px">'
            f'  <div style="display:flex;justify-content:space-between;margin-bottom:4px">'
            f'    <span style="color:{T.TEXT_MED};font-size:12px">{label}</span>'
            f'    <span style="color:{T.TEXT_HIGH};font-size:12px;font-weight:600;'
            f'      font-variant-numeric:tabular-nums">{pts:.1f}/{max_pts}</span>'
            f'  </div>'
            f'  <div style="height:4px;background:{T.BG_INPUT};border-radius:99px;overflow:hidden">'
            f'    <div style="width:{pct:.1f}%;height:100%;background:{bar_color};'
            f'      border-radius:99px"></div>'
            f'  </div>'
            f'</div>'
        )

    st.markdown(
        f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
        f'border-radius:{T.RADIUS_MD};padding:16px 18px">'
        f'  {rows_html}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Final CTA
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    if st.button("Découvrir l'app →", type="primary",
                 use_container_width=True, key="ob2_finish"):
        _finalize(audit)


# ════════════════════════════════════════════════════════════════════════════
# Finalize
# ════════════════════════════════════════════════════════════════════════════
def _finalize(audit) -> None:
    """Mark onboarding done, persist remaining estimations, jump to Accueil."""
    d = _data()

    # Persist core data to PREFERENCES (revenu, estimations)
    audit.db.set_preference("onboarding_done",       "1",                              audit.user_id)
    audit.db.set_preference("revenu_salaire",        str(d.get("salaire", 0)),         audit.user_id)
    audit.db.set_preference("revenu_total_attendu",  str(d.get("revenu_total", 0)),    audit.user_id)
    audit.db.set_preference("est_entretien",         str(d.get("est_entretien", 0)),    audit.user_id)
    audit.db.set_preference("est_alimentation",      str(d.get("est_alimentation", 0)), audit.user_id)
    audit.db.set_preference("est_transport",         str(d.get("est_transport", 0)),    audit.user_id)
    audit.db.set_preference("est_envies",            str(d.get("est_envies", 0)),       audit.user_id)
    audit.db.set_preference("est_epargne",           str(d.get("est_epargne", 0)),      audit.user_id)

    _badges.award_badge(audit, "premier_objectif", "Premier objectif fixé", "🎯")

    _invalider_cache()
    for key in (_STEP_KEY, _DATA_KEY, "ob2_reveal", "ob2_recurrents", "ob2_customs"):
        st.session_state.pop(key, None)
    st.session_state.page = "Accueil"
    st.success("✅ Bienvenue ! Bonne navigation 🚀")
    st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# Entry point (called from app.py)
# ════════════════════════════════════════════════════════════════════════════
def render(audit) -> None:
    """Main wizard render — routes to current step."""
    step = _get_step()
    _progress(step, total=_TOTAL_STEPS)

    if   step == 1: _step1_welcome_revenu(audit)
    elif step == 2: _step2_recurrents(audit)
    elif step == 3: _step3_estimation(audit)
    elif step == 4: _step4_objectif_score(audit)
    else:
        st.error(f"Étape inconnue: {step}")
        if st.button("Recommencer"):
            _set_step(1)
