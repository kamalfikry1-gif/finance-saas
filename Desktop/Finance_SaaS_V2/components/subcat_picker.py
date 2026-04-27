"""
components/subcat_picker.py — Quick sub-category refinement after grocery transactions.

Pattern: when user logs at a grocery merchant (BIM, Marjane…), the Trieur
defaults to "Courses maison". Right after, this component offers 3 quick-pick
sub-cats (Alimentation / Produits ménagers / Snacks & Boissons) so the user
can refine in 1 click. Skip = keep "Courses maison".

Usage:
    from components.subcat_picker import queue_picker, render_picker

    # In any transaction entry point, after audit.recevoir() succeeds:
    if res.get("action") == "OK":
        queue_picker(
            tx_id=res.get("id_unique"),
            libelle=libelle,
            current_subcat=res.get("sous_categorie", ""),
        )

    # In app.py, before page rendering:
    render_picker(audit)
"""

import streamlit as st

from components.design_tokens import T
from core.cache import invalider as _invalider_cache


# MA grocery merchants — match against transaction libelles (case-insensitive substring)
GROCERY_MERCHANTS = [
    "BIM", "MARJANE", "CARREFOUR", "ACIMA", "ASWAK",
    "ATACADAO", "LABEL'VIE", "LABEL VIE", "METRO", "HANOUT",
]

_PICKER_KEY = "_subcat_picker_state"

SUBCAT_OPTIONS = [
    {"key": "Alimentation",        "icon": "🍞", "label": "Alimentation"},
    {"key": "Produits ménagers",   "icon": "🧴", "label": "Produits ménagers"},
    {"key": "Snacks & Boissons",   "icon": "🍿", "label": "Snacks & Boissons"},
]


def is_grocery_merchant(libelle: str) -> bool:
    """True if the transaction libelle contains a known MA grocery merchant."""
    if not libelle:
        return False
    upper = libelle.upper()
    return any(m in upper for m in GROCERY_MERCHANTS)


def queue_picker(tx_id, libelle: str, current_subcat: str = "") -> None:
    """Set session state so the picker renders on the next rerun.
    Only queues if the libelle matches a grocery merchant."""
    if not tx_id or not is_grocery_merchant(libelle):
        return
    st.session_state[_PICKER_KEY] = {
        "tx_id":   str(tx_id),
        "libelle": libelle,
        "current": current_subcat or "Courses maison",
    }


def render_picker(audit) -> None:
    """If a picker is queued, render the 3-option card + Skip.
    Called from app.py after the topbar, before page render."""
    state = st.session_state.get(_PICKER_KEY)
    if not state:
        return

    tx_id   = state["tx_id"]
    libelle = state["libelle"]
    current = state["current"]

    st.markdown(
        f'<div style="background:{T.PRIMARY_GLO};border:1px solid {T.PRIMARY}33;'
        f'border-left:3px solid {T.PRIMARY};border-radius:{T.RADIUS_MD};'
        f'padding:12px 16px;margin-bottom:14px">'
        f'  <div style="color:{T.TEXT_HIGH};font-size:13px;font-weight:600;margin-bottom:4px">'
        f"    🛒 Précise tes courses : <b style='color:{T.PRIMARY}'>{libelle}</b>"
        f'  </div>'
        f'  <div style="color:{T.TEXT_MED};font-size:11px;margin-bottom:8px">'
        f"    Actuellement : {current} · 1 clic pour préciser, ou Skip pour garder."
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(4)
    for i, opt in enumerate(SUBCAT_OPTIONS):
        with cols[i]:
            if st.button(
                f"{opt['icon']}  {opt['label']}",
                key=f"sp_pick_{i}_{tx_id}",
                use_container_width=True,
                type="primary" if opt["key"] == current else "secondary",
            ):
                ok = audit.db.update_transaction_subcat(tx_id, opt["key"], audit.user_id)
                if ok:
                    _invalider_cache()
                    st.toast(f"✅ Classé en {opt['label']}", icon=opt["icon"])
                st.session_state.pop(_PICKER_KEY, None)
                st.rerun()
    with cols[3]:
        if st.button("✕  Skip", key=f"sp_skip_{tx_id}", use_container_width=True):
            st.session_state.pop(_PICKER_KEY, None)
            st.rerun()
