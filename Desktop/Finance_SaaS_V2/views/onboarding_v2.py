"""
views/onboarding_v2.py — New onboarding wizard (5 steps, value-first).

Steps:
    1. Bienvenue          — welcome screen, default coach (BATISSEUR)
    2. Revenus            — 1 question (salaire + extras)
    3. Estimation rapide  — 3 sliders (logement, vie quotidienne, épargne)
    4. Mini-académie      — 3 cards + quiz (placeholder, full content in Commit 2)
    5. Premier objectif   — choose + reveal score (placeholder, full content in Commit 2)

Old onboarding (3 steps) kept in views/onboarding.py as legacy fallback.
Access via ?onboarding=v1 query param for testing.
"""

from __future__ import annotations
import streamlit as st

from components.design_tokens import T
from components.helpers import dh as _dh
from core import badges as _badges
from core.cache import invalider as _invalider_cache


# ── Session state keys ──────────────────────────────────────────────────────
_STEP_KEY = "ob2_step"   # current step (1–5)
_DATA_KEY = "ob2_data"   # collected wizard data


def _get_step() -> int:
    return int(st.session_state.get(_STEP_KEY, 1))


def _set_step(n: int) -> None:
    st.session_state[_STEP_KEY] = n
    st.rerun()


def _data() -> dict:
    if _DATA_KEY not in st.session_state:
        st.session_state[_DATA_KEY] = {}
    return st.session_state[_DATA_KEY]


# ── Progress bar ────────────────────────────────────────────────────────────
def _progress(step: int, total: int = 5) -> None:
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


# ── Step 1: Bienvenue ───────────────────────────────────────────────────────
def _step1_bienvenue(audit) -> None:
    st.markdown(
        f'<div style="text-align:center;padding:30px 0 20px">'
        f'  <div style="font-size:48px;margin-bottom:12px">👋</div>'
        f'  <div style="color:{T.TEXT_HIGH};font-size:24px;font-weight:700;margin-bottom:10px">'
        f'    Bienvenue sur Finance SaaS</div>'
        f'  <div style="color:{T.TEXT_MED};font-size:14px;line-height:1.6;max-width:480px;margin:0 auto">'
        f'    On va configurer ton compte en 5 étapes rapides. À la fin, tu sauras '
        f'    exactement où tu en es financièrement, et ton coach commencera à te conseiller.'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Default coach card (BATISSEUR — choice deferred until coach sprint)
    st.markdown(
        f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
        f'border-radius:{T.RADIUS_MD};padding:18px 20px;margin:20px 0;'
        f'display:flex;gap:14px;align-items:center">'
        f'  <div style="width:46px;height:46px;border-radius:50%;'
        f'    background:linear-gradient(135deg,{T.PRIMARY},{T.PURPLE});'
        f'    display:grid;place-items:center;color:#0a1020;font-weight:700;font-size:18px">B</div>'
        f'  <div style="flex:1">'
        f'    <div style="color:{T.TEXT_HIGH};font-weight:700;font-size:14px">Coach BATISSEUR</div>'
        f'    <div style="color:{T.TEXT_LOW};font-size:11px;margin-top:2px">'
        f'      Ton coach par défaut · Tu pourras changer plus tard dans Paramètres'
        f'    </div>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if st.button("Commencer →", type="primary", use_container_width=True, key="ob2_start"):
        audit.db.set_preference("coach_identite", "BATISSEUR", audit.user_id)
        _badges.award_badge(audit, "premier_pas", "Premier pas", "🎉")
        _set_step(2)


# ── Step 2: Revenus ─────────────────────────────────────────────────────────
def _step2_revenus(audit) -> None:
    d = _data()
    st.markdown(
        f'<div style="margin-bottom:18px">'
        f'  <div style="color:{T.TEXT_HIGH};font-size:20px;font-weight:700;margin-bottom:6px">'
        f'    💰 Tes revenus</div>'
        f'  <div style="color:{T.TEXT_MED};font-size:13px">'
        f'    Combien gagnes-tu par mois en moyenne ?'
        f'  </div>'
        f'</div>',
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
        "Autres revenus mensuels (freelance, location, etc.) — optionnel",
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

    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("← Retour", key="ob2_s2_back", use_container_width=True):
            _set_step(1)
    with c2:
        if st.button("Suivant →", type="primary", use_container_width=True,
                     key="ob2_s2_next", disabled=(total <= 0)):
            d["salaire"]      = salaire
            d["extras"]       = extras
            d["revenu_total"] = total
            _badges.award_badge(audit, "revenus_configures", "Revenus configurés", "💰")
            _set_step(3)


# ── Step 3: Estimation rapide ───────────────────────────────────────────────
def _step3_estimation(audit) -> None:
    d = _data()
    revenu = float(d.get("revenu_total", 0))

    st.markdown(
        f'<div style="margin-bottom:18px">'
        f'  <div style="color:{T.TEXT_HIGH};font-size:20px;font-weight:700;margin-bottom:6px">'
        f'    📊 Estimation rapide</div>'
        f'  <div style="color:{T.TEXT_MED};font-size:13px">'
        f"    Pas besoin d'être précis — tu raffineras avec tes vraies dépenses ensuite."
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    max_log = int(max(revenu * 0.8, 5000))
    max_vie = int(max(revenu * 0.6, 4000))
    max_ep  = int(max(revenu * 0.5, 2000))

    logement = st.slider(
        "🏠 Logement (loyer/crédit + charges)",
        min_value=0, max_value=max_log,
        value=int(d.get("est_logement", revenu * 0.30)),
        step=100, format="%d DH", key="ob2_logement",
    )
    vie = st.slider(
        "🍽️ Vie quotidienne (alimentation, transport)",
        min_value=0, max_value=max_vie,
        value=int(d.get("est_vie", revenu * 0.25)),
        step=100, format="%d DH", key="ob2_vie",
    )
    epargne = st.slider(
        "💰 Épargne mensuelle visée",
        min_value=0, max_value=max_ep,
        value=int(d.get("est_epargne", revenu * 0.10)),
        step=100, format="%d DH", key="ob2_epargne",
    )

    reste = revenu - logement - vie - epargne
    reste_color = T.SUCCESS if reste > 0 else T.DANGER
    st.markdown(
        f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
        f'border-radius:{T.RADIUS_MD};padding:14px 16px;margin:18px 0">'
        f'  <div style="display:flex;justify-content:space-between">'
        f'    <span style="color:{T.TEXT_LOW};font-size:11px;font-weight:700;'
        f'      text-transform:uppercase;letter-spacing:1px">Reste pour autres dépenses</span>'
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
        if st.button("Suivant →", type="primary", use_container_width=True, key="ob2_s3_next"):
            d["est_logement"] = logement
            d["est_vie"]      = vie
            d["est_epargne"]  = epargne
            _badges.award_badge(audit, "profil_depenses", "Profil dépenses", "📊")
            _set_step(4)


# ── Step 4: Mini-académie (placeholder for Commit 2) ────────────────────────
def _step4_academie(audit) -> None:
    st.markdown(
        f'<div style="margin-bottom:18px">'
        f'  <div style="color:{T.TEXT_HIGH};font-size:20px;font-weight:700;margin-bottom:6px">'
        f'    🎓 Mini-académie</div>'
        f'  <div style="color:{T.TEXT_MED};font-size:13px">'
        f'    3 concepts clés en 60 secondes.'
        f'  </div>'
        f'</div>'
        f'<div style="background:{T.BG_CARD};border:1px dashed {T.BORDER};'
        f'border-radius:{T.RADIUS_MD};padding:30px 20px;text-align:center;margin:14px 0">'
        f'  <div style="color:{T.TEXT_LOW};font-size:13px">'
        f'    📚 Cartes éducatives + quiz (à venir au prochain commit)'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("← Retour", key="ob2_s4_back", use_container_width=True):
            _set_step(3)
    with c2:
        if st.button("Suivant →", type="primary", use_container_width=True, key="ob2_s4_next"):
            _badges.award_badge(audit, "academie_finance", "Diplômé Finance 101", "🎓")
            _set_step(5)


# ── Step 5: Premier objectif + reveal (placeholder for Commit 2) ────────────
def _step5_objectif(audit) -> None:
    st.markdown(
        f'<div style="margin-bottom:18px">'
        f'  <div style="color:{T.TEXT_HIGH};font-size:20px;font-weight:700;margin-bottom:6px">'
        f'    🎯 Ton premier objectif</div>'
        f'  <div style="color:{T.TEXT_MED};font-size:13px">'
        f'    On va te révéler ton score de départ après ça.'
        f'  </div>'
        f'</div>'
        f'<div style="background:{T.BG_CARD};border:1px dashed {T.BORDER};'
        f'border-radius:{T.RADIUS_MD};padding:30px 20px;text-align:center;margin:14px 0">'
        f'  <div style="color:{T.TEXT_LOW};font-size:13px">'
        f'    🎯 Premier objectif + reveal score (à venir au prochain commit)'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("← Retour", key="ob2_s5_back", use_container_width=True):
            _set_step(4)
    with c2:
        if st.button("Découvrir l'app →", type="primary",
                     use_container_width=True, key="ob2_finish"):
            _finalize(audit)


# ── Finalize: persist + cleanup + reroute ───────────────────────────────────
def _finalize(audit) -> None:
    """Mark onboarding done, persist data, award final badges, jump to Accueil."""
    d = _data()

    # Persist core data to PREFERENCES
    audit.db.set_preference("onboarding_done",       "1",                              audit.user_id)
    audit.db.set_preference("revenu_salaire",        str(d.get("salaire", 0)),         audit.user_id)
    audit.db.set_preference("revenu_total_attendu",  str(d.get("revenu_total", 0)),    audit.user_id)
    audit.db.set_preference("est_logement",          str(d.get("est_logement", 0)),    audit.user_id)
    audit.db.set_preference("est_vie",               str(d.get("est_vie", 0)),         audit.user_id)
    audit.db.set_preference("est_epargne",           str(d.get("est_epargne", 0)),     audit.user_id)

    _badges.award_badge(audit, "premier_objectif", "Premier objectif fixé", "🎯")

    _invalider_cache()
    for key in (_STEP_KEY, _DATA_KEY):
        st.session_state.pop(key, None)
    st.session_state.page = "Accueil"
    st.success("✅ Configuration terminée — bienvenue !")
    st.rerun()


# ── Entry point (called from app.py) ────────────────────────────────────────
def render(audit) -> None:
    """Main wizard render — routes to current step."""
    step = _get_step()
    _progress(step, total=5)

    if   step == 1: _step1_bienvenue(audit)
    elif step == 2: _step2_revenus(audit)
    elif step == 3: _step3_estimation(audit)
    elif step == 4: _step4_academie(audit)
    elif step == 5: _step5_objectif(audit)
    else:
        st.error(f"Étape inconnue: {step}")
        if st.button("Recommencer"):
            _set_step(1)
