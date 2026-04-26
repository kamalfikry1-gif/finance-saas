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

/* Hide Streamlit chrome (header, footer, menu) */
header[data-testid="stHeader"] {{ display: none !important; }}
div[data-testid="stToolbar"]  {{ display: none !important; }}
#MainMenu {{ visibility: hidden !important; }}
footer    {{ visibility: hidden !important; }}

/* Keep native sidebar collapsed-control visible and styled */
div[data-testid="stSidebarCollapsedControl"] {{
    display: flex !important;
    visibility: visible !important;
    background: {T.BG_CARD} !important;
    border-radius: 0 {T.RADIUS_MD} {T.RADIUS_MD} 0 !important;
    border: 1px solid {T.BORDER} !important;
    border-left: none !important;
    top: 12px !important;
    width: 20px !important;
    padding: 8px 4px !important;
    box-shadow: 2px 0 8px rgba(0,0,0,0.4) !important;
}}
div[data-testid="stSidebarCollapsedControl"] button {{
    color: {T.PRIMARY} !important;
    font-size: 14px !important;
}}

/* Reduce Streamlit default top padding */
.block-container {{
    padding-top: 0.5rem !important;
    padding-bottom: 1rem !important;
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
    background: linear-gradient(135deg, var(--bg-card-alt) 0%, var(--bg-page) 100%);
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
    margin-bottom: 6px !important;
    transition: border-color 0.18s !important;
}}
details[open] {{
    border-color: var(--border-glow) !important;
}}
summary {{
    color: var(--text-high) !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    padding: 13px 16px !important;
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

/* ═════════════════════════════════════════════════════════════════════════════
   ACCUEIL — CALME VARIATION (design handoff 2026-04-18)
   Editorial hero + 4 KPIs + categories list + coach/score/goals right rail.
   Palette maps teal accent to --primary, warn to --warning, etc.
   ═════════════════════════════════════════════════════════════════════════════ */

.v1-hero {{
    padding: 44px 40px 40px;
    background:
        radial-gradient(circle at 85% 20%, var(--primary-glo), transparent 55%),
        radial-gradient(circle at 10% 90%, rgba(139,92,246,0.07), transparent 55%),
        var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-xl);
    position: relative;
    overflow: hidden;
    margin-bottom: 18px;
}}
.v1-hero-label {{
    font-size: 11px;
    letter-spacing: 0.16em;
    color: var(--text-med);
    text-transform: uppercase;
}}
.v1-hero-amount {{
    font-size: 84px;
    line-height: 1;
    font-weight: 300;
    letter-spacing: -0.035em;
    margin: 14px 0 14px;
    color: var(--text-high);
    font-variant-numeric: tabular-nums;
}}
.v1-hero-amount .sign.pos {{ color: var(--success); }}
.v1-hero-amount .sign.neg {{ color: var(--danger); }}
.v1-hero-amount .unit {{
    font-size: 24px;
    color: var(--text-med);
    font-weight: 400;
    margin-left: 8px;
    letter-spacing: 0.02em;
}}
.v1-hero-sub {{
    color: var(--text-med);
    font-size: 13.5px;
    display: flex;
    flex-wrap: wrap;
    gap: 16px 20px;
    align-items: center;
}}
.v1-hero-sub .hv {{ color: var(--text-high); font-variant-numeric: tabular-nums; }}
.v1-hero-sub .hv.warn {{ color: var(--warning); }}
.v1-hero-sub .hdot {{
    width: 3px; height: 3px;
    background: var(--text-low);
    border-radius: 50%;
}}
.v1-hero-pill {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 11px;
    font-size: 12px;
    background: var(--success-glo);
    color: var(--success);
    border: 1px solid rgba(0,229,160,0.2);
    border-radius: 99px;
}}

/* KPI cards (override the plain fs-card inside Accueil) */
.v1-kpi {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-xl);
    padding: 18px 20px;
    position: relative;
    overflow: hidden;
    height: 100%;
}}
.v1-kpi-accent {{
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: var(--primary);
}}
.v1-kpi-accent.warn    {{ background: var(--warning); }}
.v1-kpi-accent.danger  {{ background: var(--danger); }}
.v1-kpi-accent.violet  {{ background: var(--purple, #8b5cf6); }}
.v1-kpi-accent.success {{ background: var(--success); }}
.v1-kpi .lbl {{
    font-size: 11px;
    letter-spacing: 0.14em;
    color: var(--text-med);
    text-transform: uppercase;
}}
.v1-kpi .val {{
    font-size: 26px;
    font-weight: 500;
    margin-top: 8px;
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
    color: var(--text-high);
}}
.v1-kpi .val .u {{
    font-size: 13px;
    color: var(--text-med);
    font-weight: 400;
    margin-left: 3px;
}}
.v1-kpi .delta {{
    font-size: 12px;
    margin-top: 10px;
    color: var(--text-med);
}}
.v1-kpi .delta.up   {{ color: var(--success); }}
.v1-kpi .delta.down {{ color: var(--danger); }}
.v1-kpi .delta.warn {{ color: var(--warning); }}

/* Section header (title + muted kicker) */
.v1-sec-head {{
    color: var(--text-med);
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    margin: 18px 0 10px;
}}

/* Category rows (Calme style — flat list with inline bar, expander body) */
.cat-row-head {{
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 6px 0 10px;
}}
.cat-swatch {{
    width: 10px; height: 10px;
    border-radius: 3px;
    flex-shrink: 0;
}}
.cat-name {{ font-weight: 500; font-size: 14px; flex: 1; color: var(--text-high); }}
.cat-amt  {{ font-weight: 500; font-size: 14px; color: var(--text-high); font-variant-numeric: tabular-nums; }}
.cat-pct  {{ color: var(--text-med); font-size: 12px; min-width: 52px; text-align: right; font-variant-numeric: tabular-nums; }}
.cat-bar {{
    height: 4px;
    background: var(--bg-input);
    border-radius: 99px;
    overflow: hidden;
    margin-bottom: 6px;
}}
.cat-bar-fill {{
    height: 100%;
    border-radius: 99px;
    transition: width 0.8s cubic-bezier(0.2, 0.8, 0.2, 1);
}}
.cat-sub-row {{
    display: grid;
    grid-template-columns: 150px 1fr 85px 38px;
    align-items: center;
    gap: 12px;
    font-size: 12.5px;
    margin: 8px 0;
}}
.cat-sub-row .n {{ color: var(--text-med); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.cat-sub-row .b {{ height: 3px; background: var(--bg-input); border-radius: 99px; overflow: hidden; }}
.cat-sub-row .bf {{ height: 100%; border-radius: 99px; }}
.cat-sub-row .a {{ text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; }}
.cat-sub-row .p {{ text-align: right; color: var(--text-low); font-variant-numeric: tabular-nums; }}

/* Coach card (Calme) */
.coach-card-v1 {{
    padding: 20px;
    border-radius: var(--radius-xl);
    background:
        linear-gradient(180deg, var(--primary-glo), transparent 50%),
        var(--bg-card);
    border: 1px solid var(--border);
}}
.coach-head-v1 {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 14px;
}}
.coach-avatar-v1 {{
    width: 38px; height: 38px;
    border-radius: 50%;
    background: linear-gradient(135deg, var(--primary), var(--purple, #8b5cf6));
    display: grid; place-items: center;
    color: #0a1020;
    font-weight: 700;
    font-size: 15px;
}}
.coach-meta-v1 .name {{ font-size: 13.5px; font-weight: 600; color: var(--text-high); }}
.coach-meta-v1 .role {{ font-size: 11px; color: var(--text-med); letter-spacing: 0.04em; }}
.mood-pill-v1 {{
    margin-left: auto;
    font-size: 10.5px;
    letter-spacing: 0.12em;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 99px;
    text-transform: uppercase;
}}
.mood-pill-v1.cool    {{ background: var(--success-glo); color: var(--success); }}
.mood-pill-v1.neutre  {{ background: var(--warning-glo); color: var(--warning); }}
.mood-pill-v1.serieux {{ background: var(--danger-glo);  color: var(--danger); }}
.coach-quote-v1 {{
    font-size: 14px;
    color: var(--text-high);
    line-height: 1.55;
    opacity: 0.92;
}}

/* Gauge (Score Santé) — SVG-based 270° arc */
.gauge-card {{
    padding: 20px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-xl);
}}
.gauge-title {{
    font-size: 11px;
    letter-spacing: 0.14em;
    color: var(--text-med);
    text-transform: uppercase;
    font-weight: 600;
}}
.gauge-wrap {{
    position: relative;
    display: grid;
    place-items: center;
    padding: 8px 0 2px;
}}
.gauge-text {{
    position: absolute;
    top: 38px;
    left: 0; right: 0;
    text-align: center;
    pointer-events: none;
}}
.gauge-num   {{ font-size: 42px; font-weight: 600; letter-spacing: -0.02em; line-height: 1; font-variant-numeric: tabular-nums; }}
.gauge-total {{ color: var(--text-med); font-size: 12px; margin-top: 4px; }}
.gauge-label {{ font-size: 10.5px; letter-spacing: 0.14em; text-transform: uppercase; font-weight: 700; margin-top: 8px; }}

/* Plan 50/30/20 rows */
.plan-row-v1 {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12.5px;
    padding: 8px 0;
    border-bottom: 1px dashed var(--border);
}}
.plan-row-v1:last-child {{ border-bottom: 0; }}
.plan-row-v1 .k {{ color: var(--text-high); display: flex; align-items: center; gap: 8px; }}
.plan-row-v1 .k .dot {{ width: 8px; height: 8px; border-radius: 2px; }}
.plan-row-v1 .v {{ display: flex; gap: 10px; align-items: baseline; }}
.plan-row-v1 .v .pct {{ color: var(--text-med); font-variant-numeric: tabular-nums; }}
.plan-row-v1 .v .amt {{ font-weight: 600; font-variant-numeric: tabular-nums; }}

/* Goals card */
.goal-card-v1 {{
    padding: 14px 16px;
    border-radius: var(--radius-md);
    background: var(--bg-card-alt);
    border: 1px solid var(--border);
    margin-top: 10px;
}}
.goal-head-v1 {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}}
.goal-title-v1 {{ font-size: 13px; font-weight: 600; color: var(--text-high); }}
.goal-date-v1  {{ font-size: 11px; color: var(--text-med); }}
.goal-bar-v1 {{
    height: 6px;
    background: var(--bg-input);
    border-radius: 99px;
    overflow: hidden;
    margin: 6px 0;
}}
.goal-bar-fill-v1 {{
    height: 100%;
    background: linear-gradient(90deg, var(--primary), var(--success));
    border-radius: 99px;
    transition: width 0.8s cubic-bezier(0.2, 0.8, 0.2, 1);
}}
.goal-foot-v1 {{
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: var(--text-med);
}}
.goal-foot-v1 .cur {{ color: var(--text-high); font-weight: 600; font-variant-numeric: tabular-nums; }}

/* ── Category cards — flat premium list ─────────────────────────────────── */
.cat-list {{
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 16px;
}}
.cat-card {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 13px 16px 10px;
    transition: border-color 0.18s, box-shadow 0.18s;
}}
.cat-card:hover {{
    border-color: var(--border-glow);
    box-shadow: 0 2px 14px rgba(0,0,0,0.3);
}}
.cat-card-main {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 10px;
}}
.cat-swatch-v2 {{
    width: 3px;
    height: 28px;
    border-radius: 2px;
    flex-shrink: 0;
}}
.cat-card-name {{
    flex: 1;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-high);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.cat-card-amt {{
    font-size: 15px;
    font-weight: 700;
    color: var(--text-high);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}}
.cat-card-unit {{
    font-size: 11px;
    font-weight: 400;
    color: var(--text-med);
    margin-left: 2px;
}}
.cat-card-pct {{
    font-size: 12px;
    color: var(--text-med);
    min-width: 38px;
    text-align: right;
    font-variant-numeric: tabular-nums;
}}
.cat-bar-v2 {{
    height: 3px;
    background: var(--bg-input);
    border-radius: 99px;
    overflow: hidden;
}}
.cat-bar-fill-v2 {{
    height: 100%;
    border-radius: 99px;
    opacity: 0.8;
}}

/* ── Coach panel — unified red zone card ────────────────────────────────── */
.coach-panel {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-xl);
    overflow: hidden;
    margin-top: 8px;
}}
.cp-header {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 18px 20px 16px;
    background: linear-gradient(180deg, var(--primary-glo), transparent 70%);
}}
.cp-divider {{
    height: 1px;
    background: rgba(255,255,255,0.05);
}}
.cp-score-row {{
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 14px 20px 16px;
}}
.cp-score-num {{
    font-size: 44px;
    font-weight: 700;
    line-height: 1;
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;
}}
.cp-score-denom {{
    font-size: 14px;
    font-weight: 400;
    color: var(--text-low);
    margin-left: 2px;
}}
.cp-message {{
    padding: 14px 20px;
    font-size: 13.5px;
    color: var(--text-high);
    line-height: 1.55;
    opacity: 0.92;
}}
.cp-section {{
    padding: 14px 20px;
}}
.cp-section-lbl {{
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--text-low);
    margin-bottom: 10px;
}}

/* ── FAB Coach — fixed bottom-right, every page ─────────────────────────── */
/* Marker div injected by app.py via st.markdown; adjacent sibling = button  */
.fab-anchor {{ display: none; }}

.element-container:has(.fab-anchor) + .element-container {{
    position: fixed !important;
    bottom: 28px !important;
    right: 28px !important;
    z-index: 10000 !important;
    width: 56px !important;
    height: 56px !important;
    margin: 0 !important;
    padding: 0 !important;
}}

.element-container:has(.fab-anchor) + .element-container > div {{
    width: 56px !important;
    height: 56px !important;
}}

.element-container:has(.fab-anchor) + .element-container button {{
    width: 56px !important;
    height: 56px !important;
    min-height: 56px !important;
    border-radius: 50% !important;
    padding: 0 !important;
    margin: 0 !important;
    font-size: 20px !important;
    font-weight: 800 !important;
    line-height: 1 !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease !important;
}}

.element-container:has(.fab-anchor) + .element-container button:hover {{
    transform: scale(1.08) !important;
}}

@media (max-width: 768px) {{
    .element-container:has(.fab-anchor) + .element-container {{
        bottom: 80px !important;
        right: 16px !important;
    }}
}}

</style>
""", unsafe_allow_html=True)
