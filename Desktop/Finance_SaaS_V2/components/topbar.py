"""
components/topbar.py — Navigation topbar across all pages.

Layout (left → right):
    👤 Moi  |  💰 + Revenu (popover form)  |  📋 Historique  |  [spacer]  |  Mois · Année
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

    # + Revenu first (primary action), then nav, then date context on the right
    c_add, c_moi, c_hist, c_space, c_date = st.columns(
        [1.6, 1, 1.4, 2, 2], gap="small"
    )

    with c_add:
        with st.popover("💰 + Revenu", use_container_width=True):
            _form_revenu(ctx)

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

    with c_date:
        st.markdown(
            f'<div style="display:flex;align-items:center;justify-content:flex-end;'
            f'gap:6px;height:100%;padding:6px 2px">'
            f'<span style="color:{T.TEXT_HIGH};font-size:14px;font-weight:700">'
            f'{mois_fr}</span>'
            f'<span style="color:{T.BORDER_MED};font-size:12px">·</span>'
            f'<span style="color:{T.TEXT_MED};font-size:13px;font-weight:500">'
            f'{annee}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f'<div style="border-bottom:1px solid {T.BORDER};margin-bottom:18px"></div>',
        unsafe_allow_html=True,
    )


def _form_revenu(ctx: dict) -> None:
    """Mini inline form to log an income transaction."""
    from core.cache import invalider as _invalider_cache

    audit = ctx["audit"]
    k = st.session_state.get("tb_rev_ctr", 0)

    st.markdown(
        f'<div style="color:{T.TEXT_HIGH};font-size:13px;font-weight:700;'
        f'margin-bottom:10px">💰 Nouveau revenu</div>',
        unsafe_allow_html=True,
    )

    libelle = st.text_input(
        "Libellé", placeholder="ex: Salaire, Freelance, Vente…",
        key=f"tb_lib_{k}",
    )
    montant = st.number_input(
        "Montant (DH)", min_value=0.0, step=100.0,
        value=None, placeholder="0",
        format="%.0f", key=f"tb_mnt_{k}",
    )
    jour = st.date_input("Date", value=_date.today(), key=f"tb_date_{k}")

    if st.button("Enregistrer ↵", key=f"tb_save_{k}", type="primary",
                 use_container_width=True):
        if not (libelle or "").strip():
            st.warning("Libellé requis.")
        elif not montant or montant <= 0:
            st.warning("Montant > 0 DH requis.")
        else:
            try:
                res = audit.recevoir(libelle.strip(), float(montant), "IN", jour)
                if res.get("action") == "OK":
                    st.session_state.tb_rev_ctr = k + 1
                    _invalider_cache()
                    st.toast(f"✅ {libelle.strip()} — {montant:,.0f} DH enregistré")
                    st.rerun()
                else:
                    st.error(res.get("erreur", "Erreur lors de l'enregistrement."))
            except Exception:
                st.error("Erreur — réessayez.")
