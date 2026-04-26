"""
components/topbar.py — Navigation topbar across all pages.

Layout (left → right):
    💸 Dépense  |  💰 Revenu  |  👤 Moi  |  📋 Historique  |  [spacer]  |  Mois (→ Historique)  |  Année
"""

from datetime import date as _date
import streamlit as st
from components.design_tokens import T

_MOIS_FR = {
    "January": "Janvier", "February": "Février", "March": "Mars",
    "April": "Avril", "May": "Mai", "June": "Juin",
    "July": "Juillet", "August": "Août", "September": "Septembre",
    "October": "Octobre", "November": "Novembre", "December": "Décembre",
}


def render(ctx: dict) -> None:
    mois_lbl = ctx.get("mois_lbl", "")
    parts    = mois_lbl.split(" ")
    mois_en  = parts[0].capitalize() if parts else ""
    mois_fr  = _MOIS_FR.get(mois_en, mois_en)
    annee    = parts[1] if len(parts) > 1 else ""

    c_sb, c_home, c_dep, c_rev, c_moi, c_hist, c_space, c_mois, c_annee = st.columns(
        [0.5, 0.6, 1.6, 1.4, 0.9, 1.3, 1.0, 1.1, 0.8], gap="small"
    )

    with c_sb:
        sb_exp = st.session_state.get("sb_expanded", True)
        if st.button("☰" if not sb_exp else "✕", key="tb_sb_toggle",
                     use_container_width=True):
            st.session_state.sb_expanded = not sb_exp
            st.rerun()

    with c_home:
        if st.button("🏠", key="tb_home", use_container_width=True):
            st.session_state.page = "Accueil"
            st.rerun()

    with c_dep:
        with st.popover("💸 Dépense", use_container_width=True):
            _form_transaction(ctx, sens="OUT")

    with c_rev:
        with st.popover("💰 Revenu", use_container_width=True):
            _form_transaction(ctx, sens="IN")

    with c_moi:
        if st.button("👤 Moi", key="tb_moi", use_container_width=True):
            st.session_state.page = "Moi"
            st.rerun()

    with c_hist:
        if st.button("📋 Historique", key="tb_hist", use_container_width=True):
            st.session_state.page = "Historique"
            st.rerun()

    with c_space:
        pass

    with c_mois:
        # Clickable — leads to month data (Historique)
        if st.button(f"{mois_fr} ›", key="tb_mois_btn", use_container_width=True):
            st.session_state.page = "Historique"
            st.rerun()

    with c_annee:
        st.markdown(
            f'<div style="display:flex;align-items:center;justify-content:center;'
            f'height:100%;color:{T.TEXT_LOW};font-size:12px;font-weight:500">'
            f'{annee}</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f'<div style="border-bottom:1px solid {T.BORDER};margin-bottom:18px"></div>',
        unsafe_allow_html=True,
    )


def _form_transaction(ctx: dict, sens: str) -> None:
    """Mini inline form for a quick expense or income entry."""
    from core.cache import invalider as _invalider_cache

    audit  = ctx["audit"]
    label  = "dépense" if sens == "OUT" else "revenu"
    icon   = "💸" if sens == "OUT" else "💰"
    k_pfix = "dep" if sens == "OUT" else "rev"
    k      = st.session_state.get(f"tb_{k_pfix}_ctr", 0)

    st.markdown(
        f'<div style="color:{T.TEXT_HIGH};font-size:13px;font-weight:700;'
        f'margin-bottom:10px">{icon} Nouvelle {label}</div>',
        unsafe_allow_html=True,
    )

    libelle = st.text_input(
        "Libellé", placeholder="ex: Carrefour, Loyer…" if sens == "OUT" else "ex: Salaire, Freelance…",
        key=f"tb_{k_pfix}_lib_{k}",
    )
    montant = st.number_input(
        "Montant (DH)", min_value=0.0, step=10.0 if sens == "OUT" else 100.0,
        value=None, placeholder="0",
        format="%.0f", key=f"tb_{k_pfix}_mnt_{k}",
    )
    jour = st.date_input("Date", value=_date.today(), key=f"tb_{k_pfix}_date_{k}")

    if st.button("Enregistrer ↵", key=f"tb_{k_pfix}_save_{k}", type="primary",
                 use_container_width=True):
        if not (libelle or "").strip():
            st.warning("Libellé requis.")
        elif not montant or montant <= 0:
            st.warning("Montant > 0 DH requis.")
        else:
            try:
                res = audit.recevoir(libelle.strip(), float(montant), sens, jour)
                if res.get("action") == "OK":
                    st.session_state[f"tb_{k_pfix}_ctr"] = k + 1
                    _invalider_cache()
                    st.toast(f"✅ {libelle.strip()} — {montant:,.0f} DH")
                    st.rerun()
                elif res.get("action") == "CONFIRMER":
                    st.warning(res.get("message", "Doublon possible — confirmez."))
                    if st.button("Confirmer quand même", key=f"tb_{k_pfix}_force_{k}"):
                        audit.recevoir(libelle.strip(), float(montant), sens, jour, forcer=True)
                        st.session_state[f"tb_{k_pfix}_ctr"] = k + 1
                        _invalider_cache()
                        st.rerun()
                else:
                    st.error(res.get("erreur", "Erreur lors de l'enregistrement."))
            except Exception:
                st.error("Erreur — réessayez.")
