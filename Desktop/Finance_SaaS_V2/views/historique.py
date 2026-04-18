"""
views/historique.py — Historique des transactions avec filtres, édition et suppression.

La liste est wrappée dans `@st.fragment` : un clic sur Modifier/Supprimer
ne rerun que le fragment (pas la page entière, pas de refetch bilan/KPIs).
Les écritures DB déclenchent un `st.rerun(scope="app")` pour rafraîchir
les KPIs et invalident les caches UI via `core.cache.invalider()`.
"""

import logging
from datetime import datetime
import streamlit as st
from components.design_tokens import T
from components.helpers import dh as _dh, section as _section
from core.cache import invalider as _invalider_cache

logger = logging.getLogger(__name__)


def render(ctx: dict) -> None:
    audit    = ctx["audit"]
    mois_sel = ctx["mois_sel"]
    mois_lbl = ctx["mois_lbl"]

    st.markdown(
        f'<h2 style="color:{T.TEXT_HIGH};font-weight:900;'
        f'font-size:24px;margin-bottom:4px">📋 Historique</h2>'
        f'<p style="color:{T.TEXT_LOW};font-size:13px;margin-bottom:20px">'
        f'Consultez, modifiez ou supprimez vos transactions · {mois_lbl}</p>',
        unsafe_allow_html=True,
    )

    # ── Filtres ───────────────────────────────────────────────────────────────
    f1, f2, f3 = st.columns([2, 1, 1])
    with f1:
        cats = ["Toutes"] + audit.get_categories()
        cat_sel = st.selectbox("Catégorie", cats, key="hist_cat")
    with f2:
        sens_sel = st.selectbox("Sens", ["Tous", "OUT", "IN"], key="hist_sens")
    with f3:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("🔄 Rafraîchir", key="hist_refresh", use_container_width=True):
            st.rerun()

    # ── Données ───────────────────────────────────────────────────────────────
    rows = audit.get_transactions(mois_sel, sens_sel, cat_sel)

    if not rows:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_LG};padding:40px;text-align:center;margin-top:20px">'
            f'<div style="font-size:32px;margin-bottom:10px">📭</div>'
            f'<div style="color:{T.TEXT_MED};font-size:14px">Aucune transaction pour cette période</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    # KPI ligne
    total_out = sum(r["Montant"] for r in rows if r["Sens"] == "OUT")
    total_in  = sum(r["Montant"] for r in rows if r["Sens"] == "IN")
    k1, k2, k3 = st.columns(3)
    k1.metric("Transactions", len(rows))
    k2.metric("Dépenses", _dh(total_out))
    k3.metric("Revenus", _dh(total_in))

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    _section(f"{len(rows)} transaction(s)")

    _render_liste(audit, rows)


@st.fragment
def _render_liste(audit, rows) -> None:
    """
    Rendu isolé de la liste : les toggles Modifier/Supprimer/Annuler ne
    rerun que ce fragment. Les écritures DB passent en scope="app".
    """
    edit_key = st.session_state.get("hist_edit_id")
    del_key  = st.session_state.get("hist_del_id")

    for tx in rows:
        tid     = tx["ID_Unique"]
        sens    = tx["Sens"]
        couleur = T.DANGER if sens == "OUT" else T.SUCCESS
        signe   = "-" if sens == "OUT" else "+"
        cat     = tx.get("Categorie") or "—"
        scat    = tx.get("Sous_Categorie") or ""
        date_v  = tx.get("Date_Valeur", "")[:10]

        # ── Confirmation suppression ──────────────────────────────────────────
        if del_key == tid:
            st.warning(f"Supprimer **{tx['Libelle']}** — {signe}{_dh(tx['Montant'])} ?")
            cc1, cc2 = st.columns(2)
            with cc1:
                if st.button("✅ Confirmer", key=f"del_ok_{tid}", type="primary", use_container_width=True):
                    audit.supprimer_transaction(tid)
                    st.session_state.hist_del_id = None
                    _invalider_cache()
                    st.rerun(scope="app")
            with cc2:
                if st.button("❌ Annuler", key=f"del_no_{tid}", use_container_width=True):
                    st.session_state.hist_del_id = None
                    st.rerun()
            continue

        # ── Formulaire modification ───────────────────────────────────────────
        if edit_key == tid:
            with st.container():
                st.markdown(
                    f'<div style="background:{T.BG_CARD_ALT};border:1px solid {T.BORDER_MED};'
                    f'border-radius:{T.RADIUS_MD};padding:16px;margin-bottom:6px">',
                    unsafe_allow_html=True,
                )
                e1, e2 = st.columns(2)
                with e1:
                    new_lib = st.text_input("Libellé", value=tx["Libelle"], key=f"elib_{tid}")
                with e2:
                    new_mnt = st.number_input(
                        "Montant (DH)", value=float(tx["Montant"]),
                        min_value=0.01, step=1.0, key=f"emnt_{tid}"
                    )
                e3, e4 = st.columns(2)
                with e3:
                    all_cats = audit.get_categories()
                    cat_idx  = all_cats.index(cat) if cat in all_cats else 0
                    new_cat  = st.selectbox("Catégorie", all_cats, index=cat_idx, key=f"ecat_{tid}")
                with e4:
                    scats    = audit.get_sous_categories(new_cat)
                    scat_idx = scats.index(scat) if scat in scats else 0
                    new_scat = st.selectbox("Sous-catégorie", scats or ["—"],
                                            index=scat_idx, key=f"escat_{tid}")
                try:
                    date_def = datetime.strptime(date_v, "%Y-%m-%d").date()
                except ValueError:
                    from datetime import date as dt_date
                    date_def = dt_date.today()
                new_date = st.date_input("Date", value=date_def, key=f"edate_{tid}")

                ea, eb = st.columns(2)
                with ea:
                    if st.button("💾 Enregistrer", key=f"esave_{tid}", type="primary", use_container_width=True):
                        audit.modifier_transaction(
                            tid, new_lib.strip(), new_mnt,
                            new_cat, new_scat, str(new_date)
                        )
                        st.session_state.hist_edit_id = None
                        _invalider_cache()
                        st.rerun(scope="app")
                with eb:
                    if st.button("❌ Annuler", key=f"ecancel_{tid}", use_container_width=True):
                        st.session_state.hist_edit_id = None
                        st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
            continue

        # ── Affichage normal ──────────────────────────────────────────────────
        row_html = (
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_MD};padding:12px 16px;'
            f'display:flex;align-items:center;gap:12px;margin-bottom:6px">'
            f'<div style="width:8px;height:8px;border-radius:50%;'
            f'background:{couleur};flex-shrink:0"></div>'
            f'<div style="flex:1;min-width:0">'
            f'<div style="color:{T.TEXT_HIGH};font-weight:600;font-size:13px">{tx["Libelle"]}</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:11px">{cat} · {scat} · {date_v}</div>'
            f'</div>'
            f'<div style="color:{couleur};font-weight:700;font-size:15px;white-space:nowrap">'
            f'{signe} {_dh(tx["Montant"])}</div>'
            f'</div>'
        )
        st.markdown(row_html, unsafe_allow_html=True)

        ca, cb = st.columns([1, 1])
        with ca:
            if st.button("✏️ Modifier", key=f"edit_{tid}", use_container_width=True):
                st.session_state.hist_edit_id = tid
                st.session_state.hist_del_id  = None
                st.rerun()
        with cb:
            if st.button("🗑️ Supprimer", key=f"del_{tid}", use_container_width=True):
                st.session_state.hist_del_id  = tid
                st.session_state.hist_edit_id = None
                st.rerun()
