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
from core import cache as ui_cache

import views.accueil   as page_accueil
import views.admin     as page_admin
import views.assistant as page_assistant
import views.onboarding as page_onboarding
import views.login      as page_login
import views.moi        as page_moi
import views.historique as page_historique
import views.journal    as page_journal
import views.plafond    as page_plafond
import views.objectif   as page_objectif
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
    st.session_state.is_admin = db.is_admin(user_id)
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

_VALID_PAGES = {"Accueil", "Assistant", "Moi", "Historique", "Journal", "Plafond", "Objectif", "Daret", "Admin"}
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
    page_onboarding.render(audit)
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
mois_lbl        = datetime.strptime(mois_sel, "%m/%Y").strftime("%B %Y").capitalize()

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
# 10. BOUTON DÉCONNEXION (sidebar bas)
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.divider()
    from components.design_tokens import T as _T
    st.markdown(
        f"<div style='color:{_T.TEXT_MED};font-size:11px;margin-bottom:4px'>"
        f"Connecté : <strong>{st.session_state.username}</strong></div>",
        unsafe_allow_html=True,
    )
    if st.button("🚪 Déconnexion", use_container_width=True, key="btn_logout"):
        ui_cache.invalider()
        st.session_state.clear()
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# 11. ROUTEUR DE PAGES
# ─────────────────────────────────────────────────────────────────────────────

page = st.session_state.page

if   page == "Accueil":    page_accueil.render(ctx)
elif page == "Assistant":  page_assistant.render(ctx)
elif page == "Moi":        page_moi.render(ctx)
elif page == "Historique": page_historique.render(ctx)
elif page == "Journal":    page_journal.render(ctx)
elif page == "Plafond":    page_plafond.render(ctx)
elif page == "Objectif":   page_objectif.render(ctx)
elif page == "Daret":      page_daret.render(ctx)
elif page == "Admin":      page_admin.render(ctx)
