"""
views/login.py — Page d'authentification (première page affichée).

Deux onglets :
  · Se connecter  — vérifie username + password hash
  · Créer un compte — hash le mot de passe, crée l'utilisateur

Hashage : passlib[bcrypt] — standard industrie.
Si login OK → stocke user_id et username dans st.session_state.
"""

import logging
import streamlit as st
import bcrypt as _bcrypt_lib
from components.design_tokens import T

logger = logging.getLogger(__name__)


class _bcrypt:
    @staticmethod
    def hash(pwd: str) -> str:
        return _bcrypt_lib.hashpw(pwd.encode("utf-8"), _bcrypt_lib.gensalt()).decode("utf-8")

    @staticmethod
    def verify(pwd: str, hashed: str) -> bool:
        try:
            return _bcrypt_lib.checkpw(pwd.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            logger.exception("bcrypt verify failed")
            return False


def _card(contenu_fn):
    """Wrapper carte centrée."""
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_LG};padding:32px 28px;margin-top:24px">',
            unsafe_allow_html=True,
        )
        contenu_fn()
        st.markdown("</div>", unsafe_allow_html=True)


def _logo():
    _, c, _ = st.columns([1, 2, 1])
    with c:
        st.markdown(
            f'<div style="text-align:center;padding:40px 0 8px">'
            f'<div style="font-size:40px;margin-bottom:8px">💰</div>'
            f'<div style="color:{T.PRIMARY};font-size:26px;font-weight:900;'
            f'letter-spacing:-0.5px">Finance SaaS</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:12px;margin-top:4px;'
            f'text-transform:uppercase;letter-spacing:2px">Beta</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


def _login_tab(db) -> None:
    """Onglet connexion."""
    st.markdown(
        f'<div style="color:{T.TEXT_HIGH};font-weight:700;font-size:16px;'
        f'margin-bottom:20px;text-align:center">Bienvenue 👋</div>',
        unsafe_allow_html=True,
    )

    username = st.text_input(
        "Nom d'utilisateur", placeholder="votre_pseudo",
        key="login_username"
    ).strip().lower()

    password = st.text_input(
        "Mot de passe", type="password",
        placeholder="••••••••",
        key="login_password"
    )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if st.button("Se connecter →", use_container_width=True,
                 type="primary", key="btn_login"):
        if not username or not password:
            st.error("Remplissez tous les champs.")
            return

        try:
            user = db.get_utilisateur(username)
        except Exception:
            st.error("Erreur de connexion — réessayez dans quelques secondes.")
            return

        if user is None:
            st.error("Utilisateur introuvable.")
            return

        pwd_hash = user.get("password_hash") or user.get("password_Hash") or ""
        if not pwd_hash or not _bcrypt.verify(password, pwd_hash):
            st.error("Mot de passe incorrect.")
            return

        # ✅ Login réussi
        st.session_state.user_id   = user.get("id") or user.get("Id")
        st.session_state.username  = user.get("username") or user.get("Username") or username
        st.session_state.logged_in = True
        st.rerun()

    st.markdown(
        f'<div style="color:{T.TEXT_LOW};font-size:11px;text-align:center;margin-top:12px">'
        f'Pas encore de compte ? Allez dans l\'onglet <strong>Créer un compte</strong>.</div>',
        unsafe_allow_html=True,
    )


def _register_tab(db) -> None:
    """Onglet création de compte."""
    st.markdown(
        f'<div style="color:{T.TEXT_HIGH};font-weight:700;font-size:16px;'
        f'margin-bottom:20px;text-align:center">Rejoignez le Beta Test 🚀</div>',
        unsafe_allow_html=True,
    )

    username = st.text_input(
        "Nom d'utilisateur", placeholder="votre_pseudo_unique",
        key="reg_username"
    ).strip().lower()

    password = st.text_input(
        "Mot de passe", type="password",
        placeholder="Minimum 8 caractères",
        key="reg_password"
    )

    password2 = st.text_input(
        "Confirmer le mot de passe", type="password",
        placeholder="••••••••",
        key="reg_password2"
    )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if st.button("Créer mon compte →", use_container_width=True,
                 type="primary", key="btn_register"):
        # Validations
        if not username or not password:
            st.error("Remplissez tous les champs.")
            return
        if len(username) < 3:
            st.error("Nom d'utilisateur : minimum 3 caractères.")
            return
        if len(password) < 8:
            st.error("Mot de passe : minimum 8 caractères.")
            return
        if password != password2:
            st.error("Les mots de passe ne correspondent pas.")
            return

        # Hash + création
        pwd_hash = _bcrypt.hash(password)
        user_id  = db.creer_utilisateur(username, pwd_hash)

        if user_id is None:
            st.error(f"Le nom '{username}' est déjà pris. Choisissez-en un autre.")
            return

        # ✅ Compte créé + connexion auto
        st.session_state.user_id   = user_id
        st.session_state.username  = username
        st.session_state.logged_in = True
        st.success(f"✅ Compte créé ! Bienvenue, {username} 🎉")
        st.rerun()

    st.markdown(
        f'<div style="color:{T.TEXT_LOW};font-size:11px;text-align:center;margin-top:12px">'
        f'Déjà un compte ? Allez dans l\'onglet <strong>Se connecter</strong>.</div>',
        unsafe_allow_html=True,
    )


def render(db) -> None:
    """
    Affiche la page de login/register.
    db : instance DatabaseManager (partagée via @st.cache_resource).

    Cette fonction est appelée depuis app.py si st.session_state.logged_in is False.
    Elle ne retourne rien — elle appelle st.rerun() si le login réussit.
    """
    _logo()

    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_LG};padding:32px 28px;margin-top:24px">',
            unsafe_allow_html=True,
        )

        tab_login, tab_register = st.tabs(["🔐 Se connecter", "✨ Créer un compte"])

        with tab_login:
            _login_tab(db)

        with tab_register:
            _register_tab(db)

        st.markdown("</div>", unsafe_allow_html=True)

    # Pied de page
    _, c2, _ = st.columns([1, 2, 1])
    with c2:
        st.markdown(
            f'<div style="text-align:center;color:{T.TEXT_LOW};font-size:10px;'
            f'margin-top:24px;text-transform:uppercase;letter-spacing:1px">'
            f'Finance SaaS · Beta · Données isolées par utilisateur</div>',
            unsafe_allow_html=True,
        )
