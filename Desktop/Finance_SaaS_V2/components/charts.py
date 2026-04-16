"""
components/charts.py — Graphiques Plotly réutilisables.

Exports :
    _gauge()   — Jauge indicateur (50/30/20, score, etc.)
"""

import plotly.graph_objects as go

from components.design_tokens import T


def _gauge(value: float, cible: float, titre: str,
           suffix: str = "%", max_v: float = 100) -> go.Figure:
    ecart = value - cible
    col   = (T.SUCCESS if abs(ecart) <= 5 else
             T.WARNING if abs(ecart) <= 15 else T.DANGER)
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=value,
        delta={"reference": cible, "valueformat": ".1f",
               "increasing": {"color": T.DANGER},
               "decreasing": {"color": T.SUCCESS}},
        number={"suffix": suffix, "font": {"size": 26, "color": T.TEXT_HIGH}},
        title={
            "text": (f"<b>{titre}</b><br>"
                     f"<span style='font-size:10px;color:{T.TEXT_MED}'>"
                     f"Cible {cible:.0f}{suffix}</span>"),
            "font": {"color": T.TEXT_HIGH, "size": 13},
        },
        gauge={
            "axis":  {"range": [0, max_v],
                      "tickcolor": T.TEXT_MUTED,
                      "tickfont": {"color": T.TEXT_LOW, "size": 9}},
            "bar":   {"color": col, "thickness": 0.28},
            "bgcolor": T.BG_CARD, "borderwidth": 0,
            "threshold": {"line": {"color": T.PRIMARY, "width": 2},
                          "thickness": 0.8, "value": cible},
            "steps": [{"range": [0, max_v], "color": T.BG_PAGE}],
        },
    ))
    fig.update_layout(
        height=195, margin=dict(t=58, b=5, l=15, r=15),
        paper_bgcolor=T.BG_PAGE, font_color=T.TEXT_HIGH,
    )
    return fig
