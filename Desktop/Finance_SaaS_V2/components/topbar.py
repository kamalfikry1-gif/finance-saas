"""
components/topbar.py — Persistent topbar across all pages.

Shows: streak badge · current month label · user initial avatar.
Rendered in app.py before every page, after ctx is built.
"""

import streamlit as st
from components.design_tokens import T


def render(ctx: dict) -> None:
    streak_jours, mois_verts = ctx.get("streak", (0, 0))
    mois_lbl = ctx.get("mois_lbl", "")
    username = ctx.get("username", "") or ""
    initial  = username[:1].upper() if username else "U"

    if streak_jours >= 2:
        streak_text  = f"🔥 {streak_jours}j"
        streak_color = T.SUCCESS
    elif streak_jours == 1:
        streak_text  = "🔥 1j"
        streak_color = T.WARNING
    elif mois_verts >= 1:
        streak_text  = f"✅ {mois_verts} mois verts"
        streak_color = T.SUCCESS
    else:
        streak_text  = "—"
        streak_color = T.TEXT_LOW

    st.markdown(
        f'<div style="display:flex;align-items:center;justify-content:space-between;'
        f'padding:8px 0 14px;border-bottom:1px solid {T.BORDER};margin-bottom:18px">'

        # Left: streak badge
        f'<div style="background:{streak_color}15;border:1px solid {streak_color}30;'
        f'border-radius:{T.RADIUS_PILL};padding:4px 12px;'
        f'color:{streak_color};font-size:12px;font-weight:700;letter-spacing:0.02em">'
        f'{streak_text}</div>'

        # Center: current month
        f'<div style="color:{T.TEXT_MED};font-size:13px;font-weight:600;'
        f'letter-spacing:0.03em">{mois_lbl}</div>'

        # Right: user avatar (visual only)
        f'<div style="width:32px;height:32px;border-radius:50%;'
        f'background:linear-gradient(135deg,{T.PRIMARY},{T.PURPLE});'
        f'display:flex;align-items:center;justify-content:center;'
        f'color:#0a1020;font-size:13px;font-weight:800;'
        f'flex-shrink:0">{initial}</div>'

        f'</div>',
        unsafe_allow_html=True,
    )
