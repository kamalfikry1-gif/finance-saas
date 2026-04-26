"""
components/hints.py — UI helper to render dismissible one-time hints.

Usage:
    from components.hints import show_hint

    show_hint(
        audit,
        hint_id="hint_accueil_welcome",
        title="Bienvenue sur ton tableau de bord",
        body="Score, dépenses, conseils — tout ici. Bonne navigation.",
        icon="💡",
    )

Hints are stored per-user via core.hints. Once dismissed, never shown again.
"""

import streamlit as st

from components.design_tokens import T
from core import hints as _hints


def show_hint(
    audit,
    hint_id: str,
    title: str,
    body: str,
    icon: str = "💡",
) -> None:
    """Render a dismissible hint card if user hasn't seen this hint before."""
    if _hints.has_seen_hint(audit, hint_id):
        return

    st.markdown(
        f'<div style="background:{T.PRIMARY_GLO};border:1px solid {T.PRIMARY}33;'
        f'border-left:3px solid {T.PRIMARY};border-radius:{T.RADIUS_MD};'
        f'padding:14px 18px;margin:10px 0;display:flex;gap:12px;align-items:flex-start">'
        f'<div style="font-size:20px;flex-shrink:0;line-height:1">{icon}</div>'
        f'<div style="flex:1">'
        f'<div style="color:{T.TEXT_HIGH};font-size:13px;font-weight:700;margin-bottom:4px">'
        f'{title}</div>'
        f'<div style="color:{T.TEXT_MED};font-size:12px;line-height:1.5">{body}</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if st.button("✕ Compris", key=f"hint_dismiss_{hint_id}", type="secondary"):
        _hints.mark_hint_seen(audit, hint_id)
        st.rerun()
