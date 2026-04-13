"""
components/charts.py — Graphiques Plotly réutilisables.

Exports :
    _gauge()   — Jauge indicateur (50/30/20, score, etc.)
"""

import plotly.graph_objects as go


def _gauge(value: float, cible: float, titre: str,
           suffix: str = "%", max_v: float = 100) -> go.Figure:
    ecart = value - cible
    col   = ("#22c55e" if abs(ecart) <= 5 else
             "#f59e0b" if abs(ecart) <= 15 else "#ef4444")
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=value,
        delta={"reference": cible, "valueformat": ".1f",
               "increasing": {"color": "#ef4444"},
               "decreasing": {"color": "#22c55e"}},
        number={"suffix": suffix, "font": {"size": 26, "color": "#f1f5f9"}},
        title={
            "text": (f"<b>{titre}</b><br>"
                     f"<span style='font-size:10px;color:#94a3b8'>"
                     f"Cible {cible:.0f}{suffix}</span>"),
            "font": {"color": "#f1f5f9", "size": 13},
        },
        gauge={
            "axis":  {"range": [0, max_v],
                      "tickcolor": "#334155",
                      "tickfont": {"color": "#475569", "size": 9}},
            "bar":   {"color": col, "thickness": 0.28},
            "bgcolor": "#13132a", "borderwidth": 0,
            "threshold": {"line": {"color": "#6366f1", "width": 2},
                          "thickness": 0.8, "value": cible},
            "steps": [{"range": [0, max_v], "color": "#0a0a14"}],
        },
    ))
    fig.update_layout(
        height=195, margin=dict(t=58, b=5, l=15, r=15),
        paper_bgcolor="#0a0a14", font_color="#f1f5f9",
    )
    return fig
