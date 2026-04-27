"""
views/moi.py — Page profil utilisateur.
Revenus, identité coach, ratios 50/30/20, seuil d'alerte.
"""

import json
import logging
import streamlit as st
from components.design_tokens import T
from components.cards import IDENTITE_LABEL, IDENTITE_DESC
from components.helpers import section as _section, render_page_header
from core.cache import invalider as _invalider_cache

logger = logging.getLogger(__name__)


def render(ctx: dict) -> None:
    audit = ctx["audit"]

    render_page_header("👤", "Paramètres", "Informations personnelles et préférences")

    # ── Section 0 : Profil (name, email, password) ──────────────────────────
    _render_profile_section(audit)

    # ── Section 1 : Revenus ──────────────────────────────────────────────────
    _section("Revenus")

    salaire_str = audit.get_preference("revenu_salaire", "0")
    try:
        salaire_actuel = float(salaire_str)
    except ValueError:
        salaire_actuel = 0.0

    extras_str = audit.get_preference("revenu_extras_json", "[]")
    try:
        extras_list = json.loads(extras_str)
        extras_total = sum(float(e.get("montant", 0)) for e in extras_list if isinstance(e, dict))
    except (ValueError, TypeError, json.JSONDecodeError):
        logger.warning("Could not parse revenu_extras_json")
        extras_total = 0.0

    c1, c2 = st.columns(2)
    with c1:
        nouveau_salaire = st.number_input(
            "Salaire mensuel net (DH)",
            min_value=0.0, max_value=999_999.0,
            value=salaire_actuel, step=100.0,
            format="%.0f",
            key="moi_salaire",
        )
    with c2:
        st.metric("Revenus extras (DH)", f"{extras_total:,.0f}".replace(",", " "),
                  help="Modifiez via la saisie de transactions Revenu")

    if st.button("💾 Sauvegarder les revenus", key="btn_save_revenus", type="primary"):
        total = nouveau_salaire + extras_total
        audit.set_preference("revenu_salaire", str(nouveau_salaire))
        audit.set_preference("revenu_total_attendu", str(total))
        _invalider_cache()
        st.success(f"✅ Salaire mis à jour — Total attendu : {total:,.0f} DH".replace(",", " "))

    # ── Section 2 : Identité Coach ───────────────────────────────────────────
    _section("Identité du Coach")

    identite_courante = audit.get_identite()
    opts = list(IDENTITE_LABEL.keys())

    cols = st.columns(len(opts))
    for i, (k, lbl) in enumerate(IDENTITE_LABEL.items()):
        with cols[i]:
            is_sel = k == identite_courante
            border = f"2px solid {T.PRIMARY}" if is_sel else f"1px solid {T.BORDER}"
            bg     = f"{T.PRIMARY}18" if is_sel else T.BG_CARD
            st.markdown(
                f'<div style="background:{bg};border:{border};'
                f'border-radius:{T.RADIUS_MD};padding:14px;text-align:center;'
                f'margin-bottom:8px">'
                f'<div style="font-size:22px;margin-bottom:6px">{lbl.split()[0]}</div>'
                f'<div style="color:{T.PRIMARY if is_sel else T.TEXT_HIGH};'
                f'font-weight:700;font-size:12px">{lbl.split(" ", 1)[1]}</div>'
                f'<div style="color:{T.TEXT_LOW};font-size:10px;margin-top:4px">'
                f'{IDENTITE_DESC[k]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if not is_sel:
                if st.button(f"Choisir", key=f"id_{k}", use_container_width=True):
                    audit.set_identite(k)
                    _invalider_cache()
                    st.rerun()
            else:
                st.markdown(
                    f'<div style="text-align:center;color:{T.PRIMARY};'
                    f'font-size:11px;font-weight:700">✓ Actif</div>',
                    unsafe_allow_html=True,
                )

    # ── Section 3 : Ratios 50/30/20 ─────────────────────────────────────────
    _section("Règle Budgétaire 50 / 30 / 20")

    needs_pct   = int(audit.get_preference("needs_pct",   "50"))
    wants_pct   = int(audit.get_preference("wants_pct",   "30"))
    savings_pct = int(audit.get_preference("savings_pct", "20"))

    st.markdown(
        f'<p style="color:{T.TEXT_MED};font-size:12px;margin-bottom:12px">'
        f'La somme doit être égale à 100 %. '
        f'Besoins = loyer, alimentation, transport. '
        f'Envies = loisirs, restos. '
        f'Épargne = investissement, remboursements.</p>',
        unsafe_allow_html=True,
    )

    r1, r2, r3 = st.columns(3)
    with r1:
        new_needs = st.number_input(
            "🏠 Besoins (%)", min_value=0, max_value=100,
            value=needs_pct, step=5, key="moi_needs"
        )
    with r2:
        new_wants = st.number_input(
            "🎭 Envies (%)", min_value=0, max_value=100,
            value=wants_pct, step=5, key="moi_wants"
        )
    with r3:
        new_savings = st.number_input(
            "💰 Épargne (%)", min_value=0, max_value=100,
            value=savings_pct, step=5, key="moi_savings"
        )

    total_pct = new_needs + new_wants + new_savings
    if total_pct != 100:
        st.warning(f"⚠️ Total : {total_pct} % — doit être égal à 100 %")
    else:
        # Barre visuelle
        st.markdown(
            f'<div style="display:flex;height:10px;border-radius:{T.RADIUS_PILL};overflow:hidden;margin:10px 0">'
            f'<div style="width:{new_needs}%;background:{T.PRIMARY}"></div>'
            f'<div style="width:{new_wants}%;background:{T.WARNING}"></div>'
            f'<div style="width:{new_savings}%;background:{T.SUCCESS}"></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if st.button("💾 Sauvegarder les ratios", key="btn_save_ratios", type="primary",
                 disabled=(total_pct != 100)):
        audit.set_preference("needs_pct",   str(new_needs))
        audit.set_preference("wants_pct",   str(new_wants))
        audit.set_preference("savings_pct", str(new_savings))
        _invalider_cache()
        st.success("✅ Ratios 50/30/20 mis à jour")

    # ── Section 4 : Seuil d'alerte ───────────────────────────────────────────
    _section("Seuil d'Alerte Dépense")

    seuil_actuel = int(audit.get_preference("seuil_alerte", "80"))
    st.markdown(
        f'<p style="color:{T.TEXT_MED};font-size:12px;margin-bottom:12px">'
        f'Le coach vous alerte quand une catégorie dépasse ce pourcentage de son plafond.</p>',
        unsafe_allow_html=True,
    )
    new_seuil = st.slider(
        "Seuil d'alerte (%)", min_value=50, max_value=100,
        value=seuil_actuel, step=5, key="moi_seuil"
    )
    if st.button("💾 Sauvegarder le seuil", key="btn_save_seuil", type="primary"):
        audit.set_preference("seuil_alerte", str(new_seuil))
        _invalider_cache()
        st.success(f"✅ Seuil d'alerte : {new_seuil} %")

    # ── Compte ───────────────────────────────────────────────────────────────
    _section("Compte")
    st.markdown(
        f'<p style="color:{T.TEXT_MED};font-size:12px;margin-bottom:12px">'
        f'Réinitialise l\'onboarding (revenus + dépenses de départ) '
        f'sans supprimer vos transactions manuelles.</p>',
        unsafe_allow_html=True,
    )
    if st.button("🔄 Refaire l'onboarding", key="moi_restart_ob", type="secondary"):
        try:
            with audit.db.connexion() as conn:
                conn.execute(
                    "DELETE FROM PREFERENCES WHERE user_id = %s AND Cle IN "
                    "('onboarding_done','revenu_salaire','revenu_extras_json',"
                    "'revenu_total_attendu')",
                    (audit.user_id,)
                )
                conn.execute(
                    "DELETE FROM TRANSACTIONS WHERE user_id = %s AND Source = 'ONBOARDING'",
                    (audit.user_id,)
                )
        except Exception:
            pass
        _invalider_cache()
        for k in list(st.session_state.keys()):
            if k.startswith("ob_") or k.startswith("_ob_") or k == "onboarding_budgets":
                del st.session_state[k]
        st.rerun()

    # ── Déconnexion ───────────────────────────────────────────────────────────
    _section("Déconnexion")

    @st.dialog("Confirmer la déconnexion")
    def _logout_dialog():
        st.markdown(
            f'<div style="color:{T.TEXT_MED};font-size:13px;margin-bottom:16px">'
            f'Voulez-vous vraiment vous déconnecter ?<br>'
            f'<span style="color:{T.TEXT_LOW};font-size:11px">'
            f'Vos données sont sauvegardées — vous pourrez vous reconnecter à tout moment.</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🚪 Déconnecter", key="logout_confirm_btn",
                         type="primary", use_container_width=True):
                _invalider_cache()
                st.session_state.clear()
                st.rerun()
        with c2:
            if st.button("Annuler", key="logout_cancel_btn", use_container_width=True):
                st.rerun()

    if st.button("🚪 Se déconnecter", key="moi_logout_btn", type="secondary"):
        _logout_dialog()


# ════════════════════════════════════════════════════════════════════════════
# Section: Profil (Name + Email + Change password)
# ════════════════════════════════════════════════════════════════════════════
def _render_profile_section(audit) -> None:
    _section("Profil")

    profile = audit.db.get_user_profile(audit.user_id)
    username = profile.get("username", "—")

    c1, c2 = st.columns(2)
    with c1:
        nom = st.text_input(
            "Nom complet",
            value=profile.get("nom", ""),
            placeholder="Ex: Kamal Fikry",
            key="moi_nom",
        )
    with c2:
        email = st.text_input(
            "Email",
            value=profile.get("email", ""),
            placeholder="kamal@exemple.ma",
            key="moi_email",
        )

    st.markdown(
        f'<div style="color:{T.TEXT_LOW};font-size:11px;margin-top:-8px;margin-bottom:10px">'
        f"Identifiant de connexion : <b style='color:{T.TEXT_MED}'>{username}</b>"
        f' (non modifiable)</div>',
        unsafe_allow_html=True,
    )

    if st.button("💾 Sauvegarder le profil", key="moi_save_profile", type="primary"):
        ok = audit.db.update_user_profile(audit.user_id, nom, email)
        if ok:
            st.success("✅ Profil mis à jour")
        else:
            st.error("Erreur lors de la sauvegarde — réessaye.")

    # ── Change password ─────────────────────────────────────────────────────
    with st.expander("🔒 Changer mon mot de passe", expanded=False):
        cur_pw = st.text_input(
            "Mot de passe actuel",
            type="password",
            key="moi_pw_current",
        )
        c_a, c_b = st.columns(2)
        with c_a:
            new_pw = st.text_input(
                "Nouveau mot de passe",
                type="password",
                key="moi_pw_new",
                help="Minimum 6 caractères",
            )
        with c_b:
            new_pw2 = st.text_input(
                "Confirmer le nouveau",
                type="password",
                key="moi_pw_new2",
            )

        # Validation feedback
        msgs = []
        if new_pw and len(new_pw) < 6:
            msgs.append("Le nouveau mot de passe doit faire au moins 6 caractères.")
        if new_pw and new_pw2 and new_pw != new_pw2:
            msgs.append("Les deux nouveaux mots de passe ne correspondent pas.")
        for m in msgs:
            st.warning(f"⚠️ {m}")

        valid = (
            cur_pw and new_pw and new_pw2
            and len(new_pw) >= 6
            and new_pw == new_pw2
        )

        if st.button("Changer mon mot de passe", key="moi_pw_change",
                     type="primary", disabled=not valid):
            if not audit.db.verify_password(audit.user_id, cur_pw):
                st.error("❌ Mot de passe actuel incorrect.")
            elif audit.db.set_password(audit.user_id, new_pw):
                st.success("✅ Mot de passe modifié.")
                # Clear the form fields
                for k in ("moi_pw_current", "moi_pw_new", "moi_pw_new2"):
                    st.session_state.pop(k, None)
                st.rerun()
            else:
                st.error("Erreur lors de la mise à jour — réessaye.")
