"""
components/helpers.py — Shared formatting helpers used across views.

Centralises _dh, _pct, section so every view uses the same logic.
"""

import streamlit as st
from components.design_tokens import T


def dh(v) -> str:
    """Format a value as '1 234 DH' (absolute, NULL-safe)."""
    v = 0.0 if v is None else float(v)
    return f"{abs(v):,.0f} DH".replace(",", " ")


def pct(v) -> str:
    """Format a value as '12.3%' (NULL-safe)."""
    v = 0.0 if v is None else float(v)
    return f"{v:.1f}%"


def section(titre: str) -> None:
    """Uppercase section divider used in list views."""
    st.markdown(
        f'<div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:2px;'
        f'margin:0 0 12px;padding-bottom:6px;'
        f'border-bottom:1px solid {T.BORDER}">{titre}</div>',
        unsafe_allow_html=True,
    )


def render_page_header(icon: str, title: str, subtitle: str = "") -> None:
    """Standard page header — icon · title · subtitle. Applied to all pages."""
    sub_html = (
        f'<div style="color:{T.TEXT_LOW};font-size:12px;margin-top:3px">{subtitle}</div>'
        if subtitle else ""
    )
    st.markdown(
        f'<div style="margin-bottom:20px;padding-bottom:14px;'
        f'border-bottom:1px solid {T.BORDER}">'
        f'<div style="display:flex;align-items:center;gap:10px">'
        f'<span style="font-size:20px;line-height:1">{icon}</span>'
        f'<div>'
        f'<div style="color:{T.TEXT_HIGH};font-size:20px;font-weight:800;'
        f'line-height:1.1;letter-spacing:-0.3px">{title}</div>'
        f'{sub_html}'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )
