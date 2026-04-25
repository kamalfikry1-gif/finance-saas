"""
components/sidebar.py — Sidebar complète : navigation, période, saisie rapide.

Export principal :
    render(audit) → str   (retourne mois_sel sélectionné)
"""

import logging
from datetime import date, datetime
from typing import Dict, List

import streamlit as st

logger = logging.getLogger(__name__)

from components.design_tokens import T
from core.cache import invalider as _invalider_cache

# ── Navigation groups ─────────────────────────────────────────────────────────

NAV_GROUPS = [
    {
        "label": "Principal",
        "pages": [
            {"id": "Accueil",    "icon": "🏠", "label": "Accueil"},
            {"id": "Historique", "icon": "📋", "label": "Historique"},
            {"id": "Moi",        "icon": "👤", "label": "Moi"},
        ],
    },
    {
        "label": "Planification",
        "pages": [
            {"id": "Objectif",   "icon": "🎯", "label": "Objectif"},
            {"id": "Plafond",    "icon": "🔔", "label": "Plafond"},
            {"id": "Daret",      "icon": "🔄", "label": "Daret"},
            {"id": "Journal",    "icon": "📔", "label": "Journal"},
        ],
    },
]


def _generer_mois_options() -> List[Dict]:
    opts, now = [], datetime.now()
    for i in range(12):
        m, y = now.month - i, now.year
        while m <= 0:
            m += 12
            y -= 1
        opts.append({
            "label": datetime(y, m, 1).strftime("%B %Y").capitalize(),
            "value": f"{m:02d}/{y}",
        })
    return opts


def render(audit) -> str:
    """
    Affiche la sidebar complète et retourne le mois sélectionné (str 'MM/YYYY').
    """
    with st.sidebar:
        # ── Logo (cliquable → Accueil) ────────────────────────────────────────
        if st.button(
            "💰 Finance SaaS",
            key="nav_logo",
            use_container_width=True,
        ):
            st.session_state.page = "Accueil"
            st.rerun()
        st.markdown(
            f'<div style="color:{T.TEXT_LOW};font-size:10px;margin:-8px 0 16px 4px;'
            f'text-transform:uppercase;letter-spacing:1.5px">Dashboard Personnel</div>',
            unsafe_allow_html=True,
        )

        # ── Navigation (grouped) ─────────────────────────────────────────────
        current_page = st.session_state.page

        for group in NAV_GROUPS:
            page_ids      = [p["id"] for p in group["pages"]]
            group_active  = current_page in page_ids

            with st.expander(group["label"], expanded=group_active):
                for page in group["pages"]:
                    pid   = page["id"]
                    icon  = page["icon"]
                    label = page["label"]

                    if current_page == pid:
                        st.markdown(
                            f'<div style="display:flex;align-items:center;gap:10px;'
                            f'background:{T.PRIMARY}18;border-radius:{T.RADIUS_MD};'
                            f'padding:8px 12px;margin:2px 0;'
                            f'border-left:3px solid {T.PRIMARY}">'
                            f'<span style="font-size:14px">{icon}</span>'
                            f'<span style="color:{T.PRIMARY};font-weight:700;'
                            f'font-size:13px">{label}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        if st.button(f"{icon}  {label}", key=f"nav_{pid}",
                                     use_container_width=True):
                            st.session_state.page = pid
                            st.rerun()

        # ── Admin (visible uniquement si is_admin) ────────────────────────────
        if st.session_state.get("is_admin"):
            st.markdown(
                f'<div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:2px;'
                f'margin:12px 0 6px">Admin</div>',
                unsafe_allow_html=True,
            )
            is_active = st.session_state.page == "Admin"
            if is_active:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:10px;'
                    f'background:{T.WARNING}18;border-radius:{T.RADIUS_MD};'
                    f'padding:9px 14px;margin:2px 0;'
                    f'border-left:3px solid {T.WARNING}">'
                    f'<span style="font-size:14px">⚙️</span>'
                    f'<span style="color:{T.WARNING};font-weight:700;font-size:13px">'
                    f'Administration</span></div>',
                    unsafe_allow_html=True,
                )
            else:
                if st.button("⚙️  Administration", key="nav_Admin",
                             use_container_width=True):
                    st.session_state.page = "Admin"
                    st.rerun()

        # ── Restart Onboarding ────────────────────────────────────────────────
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        if st.button(
            "🔄  Refaire l'onboarding",
            key="btn_restart_onboarding",
            use_container_width=True,
            type="secondary",
        ):
            _restart_onboarding(audit)
            st.rerun()

        st.divider()

        # ── Période ───────────────────────────────────────────────────────────
        st.markdown(
            f'<div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:2px;margin-bottom:6px">'
            f'Période</div>',
            unsafe_allow_html=True,
        )
        mois_opts = _generer_mois_options()
        mois_sel  = st.selectbox(
            "mois",
            options=[m["value"] for m in mois_opts],
            format_func=lambda v: next(
                m["label"] for m in mois_opts if m["value"] == v
            ),
            label_visibility="collapsed",
            key="sidebar_mois_sel",
        )

        st.divider()

        # ── Saisie rapide ─────────────────────────────────────────────────────
        st.markdown(
            f'<div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:2px;margin-bottom:8px">'
            f'+ Transaction</div>',
            unsafe_allow_html=True,
        )

        _k = st.session_state.saisie_ctr

        libelle_raw = st.text_input(
            "Libellé", placeholder="ex: MARJANE",
            key=f"saisie_lib_{_k}",
            label_visibility="collapsed",
        )
        libelle_final = libelle_raw.strip()

        if len(libelle_raw.strip()) >= 2:
            suggs = _suggestions_live(audit, libelle_raw.strip(),
                                      st.session_state.saisie_sens)
            if suggs:
                LIBRE = "— saisie libre —"
                choix = st.selectbox(
                    "sugg", options=[LIBRE] + suggs,
                    label_visibility="collapsed",
                    key=f"saisie_sugg_{_k}",
                )
                if choix != LIBRE:
                    libelle_final = choix

        bc1, bc2 = st.columns(2)
        with bc1:
            if st.button(
                "💸 Dépense", use_container_width=True,
                type="primary" if st.session_state.saisie_sens == "OUT" else "secondary",
                key="btn_dep",
            ):
                st.session_state.saisie_sens = "OUT"
                st.rerun()
        with bc2:
            if st.button(
                "💰 Revenu", use_container_width=True,
                type="primary" if st.session_state.saisie_sens == "IN" else "secondary",
                key="btn_rev",
            ):
                st.session_state.saisie_sens = "IN"
                st.rerun()

        montant_str = st.text_input(
            "Montant", placeholder="0.00",
            key=f"saisie_mnt_{_k}",
            label_visibility="collapsed",
        )
        try:
            montant = float(montant_str.replace(",", ".").replace(" ", "")) if montant_str.strip() else 0.0
        except ValueError:
            montant = 0.0

        dv = st.date_input(
            "Date", value=date.today(),
            label_visibility="collapsed",
            key=f"saisie_date_{_k}",
        )

        # ── Tags & Contact (optionnel, caché) ─────────────────────────────────
        with st.expander("🏷️ Tags & Contact", expanded=False):
            saisie_tags = st.text_input(
                "Tags", placeholder="hanout, famille, boulot…",
                key=f"saisie_tags_{_k}",
                label_visibility="collapsed",
            )
            saisie_contact = st.text_input(
                "Contact", placeholder="ex: Karim, Hanout Derb Omar…",
                key=f"saisie_contact_{_k}",
                label_visibility="collapsed",
            )

        if st.button("Enregistrer ↵", use_container_width=True,
                     type="primary", key="btn_enreg"):
            if not libelle_final:
                st.warning("Libellé requis.")
            elif montant <= 0:
                st.warning("Montant > 0 requis.")
            else:
                with st.spinner("Traitement..."):
                    res = audit.recevoir(libelle_final, montant,
                                        st.session_state.saisie_sens, dv)
                action = res.get("action")
                if action == "OK":
                    tx_id = res.get("id_unique")
                    if tx_id and (saisie_tags.strip() or saisie_contact.strip()):
                        audit.update_tags_contact(tx_id, saisie_tags, saisie_contact)
                    st.success(
                        f"✅ **{res.get('categorie')}**  \n"
                        f"{res.get('sous_categorie')} · {res.get('methode')} "
                        f"({res.get('score', 0):.0f}%)"
                    )
                    st.session_state.saisie_ctr += 1
                    _invalider_cache()
                    st.rerun()
                elif action == "CONFIRMER":
                    st.session_state.saisie_confirmer = {
                        "libelle": libelle_final, "montant": montant,
                        "sens": st.session_state.saisie_sens, "dv": dv,
                        "tags": saisie_tags, "contact": saisie_contact,
                    }
                    st.warning(f"⚠️ {res.get('message','')}")
                elif action == "BLOQUER":
                    st.session_state.saisie_confirmer = None
                    st.error(f"🚫 {res.get('message', 'Doublon détecté')}")
                else:
                    st.error(res.get("erreur", "Erreur inconnue"))

        if st.session_state.saisie_confirmer:
            p = st.session_state.saisie_confirmer
            if st.button("Confirmer quand même", key="btn_forcer", type="secondary"):
                res2 = audit.recevoir(p["libelle"], p["montant"], p["sens"], p["dv"], forcer=True)
                if res2.get("action") == "OK":
                    tx_id = res2.get("id_unique")
                    if tx_id and (p.get("tags", "").strip() or p.get("contact", "").strip()):
                        audit.update_tags_contact(tx_id, p.get("tags", ""), p.get("contact", ""))
                st.session_state.saisie_confirmer = None
                st.session_state.saisie_ctr += 1
                _invalider_cache()
                st.rerun()

        # ── Zone Test ─────────────────────────────────────────────────────────
        st.divider()
        with st.expander("🛠️ Zone Test", expanded=False):
            st.markdown(
                f'<div style="color:{T.DANGER};font-size:11px;margin-bottom:8px">'
                f'Supprime toutes les transactions et réinitialise l\'onboarding.</div>',
                unsafe_allow_html=True,
            )
            confirme = st.checkbox("Je confirme la suppression", key="reset_confirm")
            if st.button(
                "Réinitialiser les données",
                key="btn_reset_data",
                type="secondary",
                use_container_width=True,
                disabled=not confirme,
            ):
                _reset_donnees(audit)
                st.success("Données effacées. Rechargement...")
                st.rerun()

    return mois_sel


def _reset_donnees(audit) -> None:
    try:
        with audit.db.connexion() as conn:
            conn.execute("DELETE FROM TRANSACTIONS WHERE user_id = ?", (audit.user_id,))
            conn.execute("DELETE FROM BUDGETS_MENSUELS WHERE user_id = ?", (audit.user_id,))
            conn.execute(
                "DELETE FROM PREFERENCES WHERE user_id = ? AND Cle IN "
                "('onboarding_done','revenu_salaire','revenu_extras_json','revenu_total_attendu')",
                (audit.user_id,)
            )
    except Exception:
        logger.exception("_reset_onboarding_data DB cleanup failed")

    _invalider_cache()
    for key in list(st.session_state.keys()):
        if key.startswith("ob_") or key.startswith("_ob_") or key == "onboarding_budgets":
            del st.session_state[key]


def _restart_onboarding(audit) -> None:
    """
    Réinitialise l'onboarding sans supprimer les transactions manuelles.
    · Supprime les préférences onboarding (flag + revenus saisis)
    · Supprime uniquement les transactions Source=ONBOARDING (saisies auto)
    · Vide le cache Streamlit
    """
    try:
        with audit.db.connexion() as conn:
            conn.execute(
                "DELETE FROM PREFERENCES WHERE user_id = ? AND Cle IN "
                "('onboarding_done','revenu_salaire','revenu_extras_json','revenu_total_attendu')",
                (audit.user_id,)
            )
            conn.execute(
                "DELETE FROM TRANSACTIONS WHERE user_id = ? AND Source = 'ONBOARDING'",
                (audit.user_id,)
            )
    except Exception:
        logger.exception("_restart_onboarding DB cleanup failed")

    _invalider_cache()
    for key in list(st.session_state.keys()):
        if key.startswith("ob_") or key.startswith("_ob_") or key == "onboarding_budgets":
            del st.session_state[key]


def _suggestions_live(audit, prefix: str, sens: str) -> List[str]:
    q = f"%{prefix.upper()}%"
    results: List[str] = []
    try:
        with audit.db.connexion() as conn:
            rows = conn.execute(
                """SELECT DISTINCT Mot_Cle FROM DICO_MATCHING
                   WHERE UPPER(Mot_Cle) LIKE ? AND Sens = ?
                   ORDER BY Mot_Cle LIMIT 6""",
                (q, sens)
            ).fetchall()
            results = [r[0] for r in rows]
            if len(results) < 6:
                rows2 = conn.execute(
                    """SELECT DISTINCT Libelle FROM TRANSACTIONS
                       WHERE user_id = ? AND UPPER(Libelle) LIKE ?
                         AND Statut = 'VALIDE'
                       ORDER BY Date_Saisie DESC LIMIT ?""",
                    (audit.user_id, q, 6 - len(results))
                ).fetchall()
                seen = set(results)
                for r in rows2:
                    if r[0] not in seen:
                        results.append(r[0])
    except Exception:
        logger.exception("_suggestions_live query failed")
    return results
