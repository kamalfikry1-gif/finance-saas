"""
APP.PY — Finance SaaS · Entry Point (PostgreSQL + Auth)
=========================================================
Rôle unique : initialiser l'app, gérer l'auth, router vers la bonne page.
"""

import streamlit as st
from datetime import datetime
from typing import Dict

from db_manager import DatabaseManager
from audit import AuditMiddleware
from config import APP_TITLE, APP_ICON

from components.styles import inject_css
from components.sidebar import render as render_sidebar
from components.topbar import render as _render_topbar
from components.design_tokens import T
from core import cache as ui_cache

import views.accueil   as page_accueil
import views.admin     as page_admin
import views.assistant as page_assistant
import views.onboarding    as page_onboarding
import views.onboarding_v2 as page_onboarding_v2
import views.login      as page_login
import views.moi        as page_moi
import views.historique as page_historique
import views.journal    as page_journal
import views.plafond    as page_plafond
import views.objectif   as page_objectif
import views.epargne    as page_epargne
import views.tendances  as page_tendances
import views.daret      as page_daret

from core.data_input import est_onboarding_fait
from core.streak import actualiser_streak, actualiser_mois_verts, get_streak_data


# ─────────────────────────────────────────────────────────────────────────────
# 1. CONFIG PAGE
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# 2. DB SINGLETON (partagé, sans user_id)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def get_db() -> DatabaseManager:
    """
    DatabaseManager partagé entre tous les utilisateurs.
    La DATABASE_URL vient de .streamlit/secrets.toml.
    """
    url = st.secrets["DATABASE_URL"]
    db  = DatabaseManager(url)
    db.initialiser_schema()
    return db

db = get_db()
inject_css()

# ─────────────────────────────────────────────────────────────────────────────
# 3. SESSION STATE — AUTH
# ─────────────────────────────────────────────────────────────────────────────

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "username" not in st.session_state:
    st.session_state.username = None
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# ─────────────────────────────────────────────────────────────────────────────
# 4. LOGIN GATE — si non connecté → page login uniquement
# ─────────────────────────────────────────────────────────────────────────────

if not st.session_state.logged_in:
    page_login.render(db)
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# 5. AUDIT — instance par utilisateur (stockée en session_state)
# ─────────────────────────────────────────────────────────────────────────────

user_id = st.session_state.user_id

if "audit" not in st.session_state or st.session_state.get("_audit_user_id") != user_id:
    st.session_state.audit         = AuditMiddleware(db, user_id)
    st.session_state._audit_user_id = user_id

audit = st.session_state.audit

# ─────────────────────────────────────────────────────────────────────────────
# 5b. STREAK — update once per session (not on every rerun)
# ─────────────────────────────────────────────────────────────────────────────

if st.session_state.get("_admin_checked_for") != user_id:
    try:
        st.session_state.is_admin = db.is_admin(user_id)
    except Exception:
        st.session_state.is_admin = False
    st.session_state._admin_checked_for = user_id

if "streak_updated" not in st.session_state:
    try:
        actualiser_streak(db, user_id)
        actualiser_mois_verts(db, audit, user_id)
    except Exception:
        pass  # Never block the app over streak math
    st.session_state.streak_updated = True

# ─────────────────────────────────────────────────────────────────────────────
# 6. SESSION STATE — NAVIGATION & UI
# ─────────────────────────────────────────────────────────────────────────────

_VALID_PAGES = {"Accueil", "Assistant", "Moi", "Historique", "Journal", "Plafond", "Objectif", "Epargne", "Daret", "Admin"}
if st.session_state.get("page") not in _VALID_PAGES:
    st.session_state.page = "Accueil"
if "ast_path"    not in st.session_state: st.session_state.ast_path    = []
if "ast_inputs"  not in st.session_state: st.session_state.ast_inputs  = {}
if "ast_result"  not in st.session_state: st.session_state.ast_result  = None
if "saisie_sens" not in st.session_state: st.session_state.saisie_sens = "OUT"
if "saisie_ctr"  not in st.session_state: st.session_state.saisie_ctr  = 0
if "saisie_confirmer" not in st.session_state: st.session_state.saisie_confirmer = None
if "hist_edit_id" not in st.session_state: st.session_state.hist_edit_id = None
if "hist_del_id"  not in st.session_state: st.session_state.hist_del_id  = None
if "j_del_id"     not in st.session_state: st.session_state.j_del_id     = None
if "oe_update_id" not in st.session_state: st.session_state.oe_update_id = None
if "plafond_changes" not in st.session_state: st.session_state.plafond_changes = {}

# ─────────────────────────────────────────────────────────────────────────────
# 7. ONBOARDING
# ─────────────────────────────────────────────────────────────────────────────

if not est_onboarding_fait(audit):
    # New v2 wizard by default; legacy v1 still accessible via ?onboarding=v1
    use_v1 = st.query_params.get("onboarding") == "v1"
    if use_v1:
        page_onboarding.render(audit)
    else:
        page_onboarding_v2.render(audit)
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# 8. SIDEBAR → retourne le mois sélectionné
# ─────────────────────────────────────────────────────────────────────────────

mois_sel = render_sidebar(audit)

# ─────────────────────────────────────────────────────────────────────────────
# 9. CHARGEMENT DONNÉES (cache UI centralisé — voir core/cache.py)
# ─────────────────────────────────────────────────────────────────────────────

identite_active = audit.get_identite()
state           = ui_cache.get_state(audit, mois_sel, identite_active, user_id)
_MOIS_FR = {
    "January": "Janvier", "February": "Février", "March": "Mars",
    "April": "Avril", "May": "Mai", "June": "Juin",
    "July": "Juillet", "August": "Août", "September": "Septembre",
    "October": "Octobre", "November": "Novembre", "December": "Décembre",
}
_mois_raw = datetime.strptime(mois_sel, "%m/%Y").strftime("%B %Y").capitalize()
_parts    = _mois_raw.split(" ")
mois_lbl  = f"{_MOIS_FR.get(_parts[0], _parts[0])} {_parts[1]}" if len(_parts) == 2 else _mois_raw

ctx: Dict = {
    "audit":          audit,
    "user_id":        user_id,
    "username":       st.session_state.username,
    "mois_sel":       mois_sel,
    "mois_lbl":       mois_lbl,
    "identite_active": identite_active,
    "bilan":          state["bilan"],
    "humeur":         state["humeur_coach"],
    "message":        state["message_coach"],
    "score":          state["score_sante"],
    "badges":         state["badges_5030_20"],
    "alertes":        state["alertes"],
    "rept":           state["repartition"],
    "proj":           state["projection"],
    "_q":             lambda demande, **kw: ui_cache.query(audit, demande, user_id, **kw),
    "streak":         get_streak_data(db, user_id),
}

# ─────────────────────────────────────────────────────────────────────────────
# 10. TOPBAR — persistent strip above every page
# ─────────────────────────────────────────────────────────────────────────────

_render_topbar(ctx)

# Subcat picker — appears after a grocery transaction, then auto-clears
from components.subcat_picker import render_picker as _render_subcat_picker
_render_subcat_picker(audit)

# ─────────────────────────────────────────────────────────────────────────────
# 11. FAB COACH DIALOG — defined here, triggered after page render
# ─────────────────────────────────────────────────────────────────────────────

@st.dialog("Coach")
def _fab_coach_dialog(ctx: dict) -> None:
    _humeur   = ctx["humeur"]
    _identite = ctx["identite_active"]
    _message  = ctx["message"]
    _score_v  = float(ctx["score"].get("score", 0) or 0)
    _niveau   = {"EXCELLENT": "Excellent", "BON": "Bon",
                 "MOYEN": "Moyen", "CRITIQUE": "Critique"}.get(
        ctx["score"].get("niveau", ""), ""
    )
    _mc = (T.SUCCESS if _humeur == "COOL" else T.DANGER if _humeur == "SERIEUX" else T.WARNING)
    _init = (_identite or "E")[:1].upper()
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">'
        f'<div style="width:42px;height:42px;border-radius:50%;'
        f'background:linear-gradient(135deg,{T.PRIMARY},{T.PURPLE});'
        f'display:flex;align-items:center;justify-content:center;'
        f'color:#0a1020;font-weight:800;font-size:17px">{_init}</div>'
        f'<div><div style="color:{T.TEXT_HIGH};font-weight:700;font-size:14px">'
        f'Coach {_identite}</div>'
        f'<div style="color:{T.TEXT_LOW};font-size:11px">Assistant financier</div></div>'
        f'<span style="margin-left:auto;background:{_mc}20;color:{_mc};'
        f'font-size:10px;font-weight:700;padding:3px 10px;border-radius:99px;'
        f'letter-spacing:1px;text-transform:uppercase">{_humeur}</span>'
        f'</div>'
        f'<div style="color:{T.TEXT_HIGH};font-size:13px;line-height:1.6;'
        f'margin-bottom:14px">{_message}</div>'
        f'<div style="background:{T.BG_CARD_ALT};border-radius:{T.RADIUS_MD};'
        f'padding:10px 14px;display:flex;align-items:baseline;gap:6px;margin-bottom:4px">'
        f'<span style="color:{_mc};font-size:30px;font-weight:900">{_score_v:.0f}</span>'
        f'<span style="color:{T.TEXT_LOW};font-size:12px">/100 · {_niveau}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if st.button("🤖 Parler au Coach →", use_container_width=True, type="primary"):
        st.session_state.page = "Assistant"
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# 12. ROUTEUR DE PAGES
# ─────────────────────────────────────────────────────────────────────────────

page = st.session_state.page

if   page == "Accueil":    page_accueil.render(ctx)
elif page == "Assistant":  page_assistant.render(ctx)
elif page == "Moi":        page_moi.render(ctx)
elif page == "Historique": page_historique.render(ctx)
elif page == "Journal":    page_journal.render(ctx)
elif page == "Plafond":    page_plafond.render(ctx)
elif page == "Objectif":   page_objectif.render(ctx)
elif page == "Epargne":    page_epargne.render(ctx)
elif page == "Tendances":  page_tendances.render(ctx)
elif page == "Daret":      page_daret.render(ctx)
elif page == "Admin":      page_admin.render(ctx)

# ─────────────────────────────────────────────────────────────────────────────
# 13. FAB COACH — fixed bottom-right circle, every page
# ─────────────────────────────────────────────────────────────────────────────

_fab_humeur   = ctx.get("humeur", "NEUTRE")
_fab_identite = ctx.get("identite_active", "EQUILIBRE")
_fab_letter   = (_fab_identite or "E")[:1].upper()
_fab_bg       = (T.SUCCESS if _fab_humeur == "COOL"
                 else T.DANGER if _fab_humeur == "SERIEUX" else T.WARNING)

st.markdown(
    f'<style>'
    f'.element-container:has(.fab-anchor) + .element-container {{'
    f'  background:{_fab_bg} !important;'
    f'}}'
    f'.element-container:has(.fab-anchor) + .element-container button {{'
    f'  background:{_fab_bg} !important;'
    f'  background-image:none !important;'
    f'  box-shadow:0 6px 28px {_fab_bg}55 !important;'
    f'}}'
    f'</style>'
    f'<div class="fab-anchor"></div>',
    unsafe_allow_html=True,
)
if st.button(_fab_letter, key="fab_coach_open", type="primary"):
    _fab_coach_dialog(ctx)
