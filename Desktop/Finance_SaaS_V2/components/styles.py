"""
components/styles.py — Injection du CSS global de Finance SaaS.
Appeler inject_css() une seule fois depuis app.py.

Toutes les couleurs utilisent var(--token) définis dans design_tokens.py.
Pour changer le thème : modifier design_tokens.py uniquement.
"""

import streamlit as st
from components.design_tokens import css_variables


def inject_css() -> None:
    st.markdown(f"""
<style>
{css_variables()}

/* ── Base ──────────────────────────────────────────────────────────────────── */
.stApp {{
    background: var(--bg-page);
    color: var(--text-high);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}}

section[data-testid="stSidebar"] {{
    background: var(--bg-sidebar) !important;
    border-right: 1px solid var(--border);
}}

/* ── KPI Card ───────────────────────────────────────────────────────────────── */
.fs-card {{
    background: linear-gradient(135deg, var(--bg-card) 0%, var(--bg-card-alt) 100%);
    border-radius: var(--radius-lg);
    padding: 20px 22px;
    border: 1px solid var(--border);
    margin-bottom: 10px;
    position: relative;
    overflow: hidden;
    transition: var(--transition);
    box-shadow: var(--shadow-card);
}}
.fs-card::before {{
    content: '';
    position: absolute; top: 0; left: 0;
    width: 3px; height: 100%;
    background: var(--accent, var(--primary));
    border-radius: 3px 0 0 3px;
}}
.fs-card:hover {{
    border-color: var(--accent, var(--primary));
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
    transform: translateY(-1px);
}}
.fs-card .lbl {{
    color: var(--text-low);
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
}}
.fs-card .val {{
    color: var(--text-high);
    font-size: 26px;
    font-weight: 900;
    margin: 6px 0 2px;
    line-height: 1;
    letter-spacing: -0.5px;
}}
.fs-card .sub {{
    color: var(--text-muted);
    font-size: 11px;
}}

/* ── Hero Solde ─────────────────────────────────────────────────────────────── */
.fs-hero {{
    background: linear-gradient(135deg, #0f0f2e 0%, var(--bg-page) 100%);
    border-radius: var(--radius-xl);
    padding: 36px 32px;
    margin-bottom: 16px;
    border: 1px solid var(--border-glow);
    text-align: center;
    box-shadow: var(--shadow-card);
    position: relative;
    overflow: hidden;
}}
.fs-hero::after {{
    content: '';
    position: absolute;
    top: -60px; left: 50%;
    transform: translateX(-50%);
    width: 300px; height: 300px;
    background: radial-gradient(circle, var(--primary-glo) 0%, transparent 70%);
    pointer-events: none;
}}
.fs-hero .h-lbl {{
    color: var(--primary);
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 2.5px;
}}
.fs-hero .h-val {{
    font-size: 52px;
    font-weight: 900;
    margin: 10px 0 4px;
    line-height: 1;
    letter-spacing: -1px;
}}
.fs-hero .h-sub {{
    color: var(--text-low);
    font-size: 13px;
}}

/* ── Cat row ────────────────────────────────────────────────────────────────── */
.fs-cat {{
    background: var(--bg-card);
    border-radius: var(--radius-md);
    padding: 14px 16px;
    margin-bottom: 8px;
    border: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 14px;
    transition: var(--transition);
}}
.fs-cat:hover {{
    border-color: var(--border-glow);
    background: var(--bg-card-alt);
}}
.cat-dot   {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
.cat-name  {{ color: var(--text-high); font-weight: 600; font-size: 14px; }}
.cat-right {{ margin-left: auto; text-align: right; }}
.cat-amt   {{ color: var(--text-high); font-weight: 700; font-size: 15px; }}
.cat-pct   {{ color: var(--text-low); font-size: 11px; }}
.fs-bar-bg {{ background: var(--border); border-radius: var(--radius-pill); height: 4px; width: 100%; margin-top: 8px; }}
.fs-bar    {{ height: 4px; border-radius: var(--radius-pill); transition: width 0.6s ease; }}

/* ── Alert box ──────────────────────────────────────────────────────────────── */
.fs-alert {{
    border-radius: var(--radius-md);
    padding: 12px 16px;
    margin: 4px 0;
    font-size: 13px;
    border: 1px solid;
    line-height: 1.5;
}}

/* ── Boutons navigation sidebar ─────────────────────────────────────────────── */
.stButton > button {{
    background: transparent;
    color: var(--text-low);
    border: none;
    border-radius: var(--radius-md);
    font-weight: 600;
    font-size: 13px;
    padding: 9px 14px;
    text-align: left;
    transition: var(--transition);
    width: 100%;
}}
.stButton > button:hover {{
    background: var(--bg-card-alt);
    color: var(--text-high);
}}

/* ── Boutons primaires ──────────────────────────────────────────────────────── */
.stButton > button[kind="primary"] {{
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dim) 100%) !important;
    color: #fff !important;
    border-radius: var(--radius-md) !important;
    font-weight: 700 !important;
    font-size: 13px !important;
    border: none !important;
    box-shadow: 0 2px 12px var(--primary-glo) !important;
    transition: var(--transition) !important;
}}
.stButton > button[kind="primary"]:hover {{
    background: linear-gradient(135deg, var(--primary-dim) 0%, var(--primary) 100%) !important;
    box-shadow: var(--shadow-primary) !important;
    transform: translateY(-1px) !important;
}}

/* ── Inputs ─────────────────────────────────────────────────────────────────── */
.stTextInput input,
.stNumberInput input,
.stSelectbox > div > div,
.stDateInput input {{
    background: var(--bg-input) !important;
    color: var(--text-high) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    transition: var(--transition) !important;
}}
.stTextInput input:focus,
.stNumberInput input:focus {{
    border-color: var(--primary) !important;
    box-shadow: 0 0 0 2px var(--primary-glo) !important;
}}
.stSelectbox label, .stNumberInput label,
.stTextInput label, .stDateInput label,
.stSlider label {{
    color: var(--text-low) !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
}}

/* ── Tabs ───────────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {{
    background: var(--bg-sidebar);
    border-radius: var(--radius-md);
    gap: 4px;
    border: 1px solid var(--border);
    padding: 4px;
}}
.stTabs [data-baseweb="tab"] {{
    color: var(--text-low);
    font-weight: 600;
    font-size: 13px;
    border-radius: var(--radius-sm) !important;
    transition: var(--transition);
}}
.stTabs [aria-selected="true"] {{
    color: var(--primary) !important;
    background: var(--bg-card) !important;
    border-bottom: 2px solid var(--primary) !important;
}}

/* ── Metric ─────────────────────────────────────────────────────────────────── */
div[data-testid="stMetric"] {{
    background: var(--bg-card);
    border-radius: var(--radius-md);
    padding: 14px 18px;
    border: 1px solid var(--border);
}}
div[data-testid="stMetricValue"] {{ color: var(--text-high) !important; font-weight: 900 !important; }}
div[data-testid="stMetricLabel"] {{ color: var(--text-low) !important; font-size: 11px !important; }}

/* ── DataFrame ──────────────────────────────────────────────────────────────── */
div[data-testid="stDataFrameResizable"] {{
    border-radius: var(--radius-md);
    overflow: hidden;
    border: 1px solid var(--border);
}}

/* ── Divider ────────────────────────────────────────────────────────────────── */
hr {{ border-color: var(--border) !important; margin: 12px 0; }}

/* ── Expander ───────────────────────────────────────────────────────────────── */
details {{
    background: var(--bg-card) !important;
    border-radius: var(--radius-md) !important;
    border: 1px solid var(--border) !important;
}}
summary {{
    color: var(--text-med) !important;
    font-weight: 600 !important;
    font-size: 13px !important;
}}

/* ── Scrollbar ──────────────────────────────────────────────────────────────── */
::-webkit-scrollbar {{ width: 6px; height: 6px; }}
::-webkit-scrollbar-track {{ background: var(--bg-page); }}
::-webkit-scrollbar-thumb {{ background: var(--border-glow); border-radius: 3px; }}
::-webkit-scrollbar-thumb:hover {{ background: var(--primary); }}

/* ── Section label ──────────────────────────────────────────────────────────── */
.fs-section-label {{
    color: var(--text-low);
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 2px;
    margin: 20px 0 10px;
    padding-left: 2px;
}}
</style>
""", unsafe_allow_html=True)
