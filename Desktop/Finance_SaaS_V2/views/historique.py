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
from core.cache import invalider as _invalider_cache, get_categories as _get_cats, get_sous_categories as _get_scats

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

    # ── Tabs ──────────────────────────────────────────────────────────────────
    inconnus = audit.get_a_classifier()
    nb_label = f" ({len(inconnus)})" if inconnus else ""
    tab_hist, tab_carnet, tab_clf = st.tabs([
        "📋 Transactions", "💳 Carnet de Crédit", f"🔍 À Classifier{nb_label}"
    ])

    with tab_carnet:
        _render_carnet(audit)

    with tab_clf:
        _render_a_classifier(audit, inconnus)

    with tab_hist:
        # ── Filtres ───────────────────────────────────────────────────────────
        f1, f2, f3 = st.columns([2, 1, 1])
        with f1:
            cats = ["Toutes"] + _get_cats(audit, audit.user_id)
            cat_sel = st.selectbox("Catégorie", cats, key="hist_cat")
        with f2:
            sens_sel = st.selectbox("Sens", ["Tous", "OUT", "IN"], key="hist_sens")
        with f3:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("🔄 Rafraîchir", key="hist_refresh", use_container_width=True):
                st.rerun()

        # ── Données ───────────────────────────────────────────────────────────
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
                        "Montant (DH)", value=abs(float(tx["Montant"])),
                        min_value=0.01, step=1.0, key=f"emnt_{tid}"
                    )
                e3, e4 = st.columns(2)
                with e3:
                    all_cats = _get_cats(audit, audit.user_id)
                    cat_idx  = all_cats.index(cat) if cat in all_cats else 0
                    new_cat  = st.selectbox("Catégorie", all_cats, index=cat_idx, key=f"ecat_{tid}")
                with e4:
                    scats    = _get_scats(audit, new_cat, audit.user_id)
                    scat_idx = scats.index(scat) if scat in scats else 0
                    new_scat = st.selectbox("Sous-catégorie", scats or ["—"],
                                            index=scat_idx, key=f"escat_{tid}")
                e5, e6 = st.columns(2)
                with e5:
                    new_tags = st.text_input(
                        "🏷️ Tags", value=tx.get("Tags", "") or "",
                        placeholder="hanout, famille…", key=f"etags_{tid}",
                    )
                with e6:
                    new_contact = st.text_input(
                        "👤 Contact", value=tx.get("Contact", "") or "",
                        placeholder="ex: Karim", key=f"econtact_{tid}",
                    )
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
                            new_cat, new_scat, str(new_date),
                            tags=new_tags, contact=new_contact,
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
        tags_str    = (tx.get("Tags", "") or "").strip()
        contact_str = (tx.get("Contact", "") or "").strip()

        tags_html = ""
        if tags_str:
            tags_html += "".join(
                f'<span style="background:{T.BG_CARD_ALT};color:{T.TEXT_MED};'
                f'font-size:10px;padding:2px 7px;border-radius:{T.RADIUS_PILL};'
                f'margin-right:4px;border:1px solid {T.BORDER}">🏷 {t.strip()}</span>'
                for t in tags_str.split(",") if t.strip()
            )
        if contact_str:
            tags_html += (
                f'<span style="background:{T.PRIMARY}15;color:{T.PRIMARY};'
                f'font-size:10px;padding:2px 7px;border-radius:{T.RADIUS_PILL};'
                f'margin-right:4px;border:1px solid {T.PRIMARY}30">👤 {contact_str}</span>'
            )

        meta_line = f"{cat} · {scat} · {date_v}"
        tags_row  = f'<div style="margin-top:4px">{tags_html}</div>' if tags_html else ""

        row_html = (
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_MD};padding:12px 16px;'
            f'display:flex;align-items:center;gap:12px;margin-bottom:6px">'
            f'<div style="width:8px;height:8px;border-radius:50%;'
            f'background:{couleur};flex-shrink:0"></div>'
            f'<div style="flex:1;min-width:0">'
            f'<div style="color:{T.TEXT_HIGH};font-weight:600;font-size:13px">{tx["Libelle"]}</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:11px">{meta_line}</div>'
            f'{tags_row}'
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


def _render_a_classifier(audit, inconnus: list) -> None:
    """
    🔍 À Classifier — let the user teach the app unknown keywords.
    Each validated row writes to REGLES_UTILISATEUR and re-classifies
    matching A_CLASSIFIER transactions immediately.
    """
    st.markdown(
        f'<p style="color:{T.TEXT_LOW};font-size:13px;margin-bottom:16px">'
        f'Ces mots-clés n\'ont pas pu être classifiés automatiquement. '
        f'Chaque règle validée s\'applique à toutes les transactions correspondantes.</p>',
        unsafe_allow_html=True,
    )

    if not inconnus:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_LG};padding:32px;text-align:center">'
            f'<div style="font-size:28px;margin-bottom:8px">✅</div>'
            f'<div style="color:{T.TEXT_MED};font-size:13px">'
            f'Aucun mot-clé inconnu — tout est classifié.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    all_cats = _get_cats(audit, audit.user_id)

    for item in inconnus:
        mot   = item.get("Mot_Cle_Inconnu", "")
        sens  = item.get("Sens", "OUT")
        nb    = int(item.get("Nb_Occurrences", 1))
        auto_cat  = item.get("Categorie_Auto", "")
        auto_scat = item.get("Sous_Categorie_Auto", "")

        sens_color = T.DANGER if sens == "OUT" else T.SUCCESS
        sens_label = "Dépense" if sens == "OUT" else "Revenu"

        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_MD};padding:14px 16px;margin-bottom:6px">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'margin-bottom:10px">'
            f'<div style="display:flex;align-items:center;gap:10px">'
            f'<span style="color:{T.TEXT_HIGH};font-weight:700;font-size:14px">{mot}</span>'
            f'<span style="background:{sens_color}20;color:{sens_color};font-size:10px;'
            f'padding:2px 8px;border-radius:{T.RADIUS_PILL};font-weight:700">{sens_label}</span>'
            f'</div>'
            f'<span style="color:{T.TEXT_LOW};font-size:11px">{nb}× rencontré</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
        with c1:
            cat_idx = all_cats.index(auto_cat) if auto_cat in all_cats else 0
            new_cat = st.selectbox("Catégorie", all_cats, index=cat_idx,
                                   key=f"clf_cat_{mot}_{sens}", label_visibility="collapsed")
        with c2:
            scats = _get_scats(audit, new_cat, audit.user_id)
            scat_idx = scats.index(auto_scat) if auto_scat in scats else 0
            new_scat = st.selectbox("Sous-catégorie", scats or ["—"], index=scat_idx,
                                    key=f"clf_scat_{mot}_{sens}", label_visibility="collapsed")
        with c3:
            if st.button("✅ Valider", key=f"clf_ok_{mot}_{sens}",
                         type="primary", use_container_width=True):
                nb_fixed = audit.valider_classification(mot, sens, new_cat, new_scat)
                _invalider_cache()
                st.success(f"{nb_fixed} transaction(s) reclassifiée(s) → {new_cat} / {new_scat}")
                st.rerun()
        with c4:
            if st.button("Ignorer", key=f"clf_skip_{mot}_{sens}", use_container_width=True):
                audit.ignorer_mot_cle(mot, sens)
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)


def _render_carnet(audit) -> None:
    """
    💳 Carnet de Crédit — soldes par contact (hanout, amis, famille).
    Toutes les transactions avec un Contact renseigné, groupées par contact.
    """
    st.markdown(
        f'<p style="color:{T.TEXT_LOW};font-size:13px;margin-bottom:16px">'
        f'Suivi des dettes et créances — tout ce qui est tagué avec un Contact.</p>',
        unsafe_allow_html=True,
    )

    # Fetch all transactions with a contact across all time
    try:
        with audit.db.connexion() as conn:
            rows = conn.execute(
                """SELECT Contact, Sens, SUM(ABS(Montant)) AS Total
                   FROM TRANSACTIONS
                   WHERE user_id=%s AND Contact IS NOT NULL AND Contact != ''
                     AND Statut='VALIDE'
                   GROUP BY Contact, Sens
                   ORDER BY Contact""",
                (audit.user_id,),
            ).fetchall()
    except Exception:
        st.info("Aucun contact enregistré pour l'instant.")
        return

    if not rows:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_LG};padding:32px;text-align:center">'
            f'<div style="font-size:28px;margin-bottom:8px">📒</div>'
            f'<div style="color:{T.TEXT_MED};font-size:13px">'
            f'Aucun contact enregistré.<br>Ajoutez un Contact lors de la saisie d\'une transaction.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    # Aggregate per contact
    from collections import defaultdict
    balances: dict = defaultdict(lambda: {"out": 0.0, "in": 0.0})
    for r in rows:
        contact = r[0] if hasattr(r, "__getitem__") else r["Contact"]
        sens    = r[1] if hasattr(r, "__getitem__") else r["Sens"]
        total   = float(r[2] if hasattr(r, "__getitem__") else r["Total"])
        if sens == "OUT":
            balances[contact]["out"] += total
        else:
            balances[contact]["in"] += total

    for contact, data in sorted(balances.items()):
        net = data["out"] - data["in"]
        if net > 0:
            color  = T.DANGER
            status = f"Tu as dépensé {_dh(net)} (hanout / avance)"
        elif net < 0:
            color  = T.SUCCESS
            status = f"Tu as reçu {_dh(abs(net))} de plus que dépensé"
        else:
            color  = T.TEXT_LOW
            status = "Soldé"

        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-left:3px solid {color};border-radius:{T.RADIUS_MD};'
            f'padding:14px 16px;margin-bottom:8px;'
            f'display:flex;justify-content:space-between;align-items:center">'
            f'<div>'
            f'<div style="color:{T.TEXT_HIGH};font-weight:700;font-size:14px">👤 {contact}</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:11px;margin-top:3px">{status}</div>'
            f'</div>'
            f'<div style="text-align:right">'
            f'<div style="color:{color};font-weight:900;font-size:18px">{_dh(abs(net))}</div>'
            f'<div style="color:{T.TEXT_LOW};font-size:10px">'
            f'Sorti : {_dh(data["out"])} · Entré : {_dh(data["in"])}</div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
