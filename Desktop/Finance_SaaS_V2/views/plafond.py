"""
views/plafond.py — Gestion des plafonds budgétaires par catégorie.
Plafond permanent (CATEGORIES.Plafond) — le système alerte quand dépassé.
"""

import streamlit as st
from components.design_tokens import T


def _dh(v: float) -> str:
    return f"{v:,.0f} DH".replace(",", " ")


def _get_depenses_mois(audit, mois: str) -> dict:
    """Retourne {(Categorie, Sous_Categorie): montant_depense} pour le mois."""
    try:
        parts   = mois.split("/")
        mois_db = f"{parts[1]}-{parts[0]}"
        with audit.db.connexion() as conn:
            rows = conn.execute(
                """SELECT Categorie, Sous_Categorie, SUM(Montant) as total
                   FROM TRANSACTIONS
                   WHERE Sens='OUT' AND user_id=? AND Date_Valeur LIKE ? AND Statut='VALIDE'
                   GROUP BY Categorie, Sous_Categorie""",
                (audit.user_id, f"{mois_db}%")
            ).fetchall()
        return {(r[0], r[1]): float(r[2]) for r in rows}
    except Exception:
        return {}


def render(ctx: dict) -> None:
    audit    = ctx["audit"]
    mois_sel = ctx["mois_sel"]
    mois_lbl = ctx["mois_lbl"]
    db       = audit.db

    st.markdown(
        f'<h2 style="color:{T.TEXT_HIGH};font-weight:900;'
        f'font-size:24px;margin-bottom:4px">🔔 Plafonds Budgétaires</h2>'
        f'<p style="color:{T.TEXT_LOW};font-size:13px;margin-bottom:24px">'
        f'Définissez un plafond mensuel par sous-catégorie. '
        f'Le coach vous alerte automatiquement quand vous approchez de la limite. '
        f'· Vue mois : <strong style="color:{T.PRIMARY}">{mois_lbl}</strong></p>',
        unsafe_allow_html=True,
    )

    cats        = db.get_plafonds_categories()
    depenses    = _get_depenses_mois(audit, mois_sel)
    categories  = {}

    for row in cats:
        cat  = row["Categorie"]
        scat = row["Sous_Categorie"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append({
            "sous_cat": scat,
            "plafond":  float(row["Plafond"] or 0),
            "depense":  depenses.get((cat, scat), 0.0),
        })

    if not categories:
        st.info("Aucune catégorie de dépense trouvée. Commencez par saisir des transactions.")
        return

    # Modifications en attente
    if "plafond_changes" not in st.session_state:
        st.session_state.plafond_changes = {}

    for cat, items in categories.items():
        # En-tête catégorie
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_LG};padding:20px;margin-bottom:12px">',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="color:{T.PRIMARY};font-size:14px;font-weight:700;'
            f'margin-bottom:14px;text-transform:uppercase;letter-spacing:1px">{cat}</div>',
            unsafe_allow_html=True,
        )

        for item in items:
            scat    = item["sous_cat"]
            plafond = item["plafond"]
            depense = item["depense"]
            key     = f"plafond_{cat}_{scat}"

            pct     = min((depense / plafond * 100) if plafond > 0 else 0, 100)
            couleur = T.SUCCESS if pct < 70 else (T.WARNING if pct < 90 else T.DANGER)

            col_a, col_b, col_c = st.columns([3, 2, 2])
            with col_a:
                st.markdown(
                    f'<div style="color:{T.TEXT_HIGH};font-weight:600;'
                    f'font-size:13px;padding-top:8px">{scat}</div>',
                    unsafe_allow_html=True,
                )
                if plafond > 0:
                    st.markdown(
                        f'<div style="background:{T.BORDER};border-radius:{T.RADIUS_PILL};'
                        f'height:6px;margin-top:6px;overflow:hidden">'
                        f'<div style="width:{pct:.0f}%;height:100%;'
                        f'background:{couleur};border-radius:{T.RADIUS_PILL}"></div>'
                        f'</div>'
                        f'<div style="color:{T.TEXT_LOW};font-size:10px;margin-top:3px">'
                        f'{depense:,.0f} / {plafond:,.0f} DH ({pct:.0f}%)</div>'.replace(",", " "),
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div style="color:{T.TEXT_LOW};font-size:10px;margin-top:6px">'
                        f'Dépensé ce mois : {_dh(depense)} · Pas de plafond défini</div>',
                        unsafe_allow_html=True,
                    )
            with col_b:
                new_val = st.number_input(
                    "Plafond (DH)", min_value=0.0, max_value=999_999.0,
                    value=plafond, step=100.0, format="%.0f",
                    label_visibility="collapsed",
                    key=key,
                )
                if new_val != plafond:
                    st.session_state.plafond_changes[(cat, scat)] = new_val
            with col_c:
                if (cat, scat) in st.session_state.plafond_changes:
                    if st.button("💾 Sauv.", key=f"psave_{cat}_{scat}", use_container_width=True, type="primary"):
                        db.set_plafond_categorie(cat, scat, new_val)
                        del st.session_state.plafond_changes[(cat, scat)]
                        st.cache_data.clear()
                        st.success(f"✅ {scat} — plafond : {_dh(new_val)}")
                        st.rerun()
                else:
                    if plafond > 0 and pct >= 90:
                        st.markdown(
                            f'<div style="color:{T.DANGER};font-size:11px;'
                            f'font-weight:700;padding-top:8px">⚠️ Limite atteinte</div>',
                            unsafe_allow_html=True,
                        )
                    elif plafond > 0 and pct >= 70:
                        st.markdown(
                            f'<div style="color:{T.WARNING};font-size:11px;'
                            f'font-weight:700;padding-top:8px">🔸 Attention</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            f'<div style="color:{T.TEXT_LOW};font-size:11px;'
                            f'padding-top:8px">—</div>',
                            unsafe_allow_html=True,
                        )

        st.markdown("</div>", unsafe_allow_html=True)

    # Bouton global
    st.divider()
    n_changes = len(st.session_state.plafond_changes)
    if n_changes > 0:
        st.info(f"{n_changes} modification(s) non sauvegardée(s) — cliquez sur 💾 Sauv. pour chaque ligne.")
