"""
views/journal.py — Journal financier : notes contextuelles par date.
Permet d'expliquer les anomalies de dépenses (ex: "J'ai acheté un frigo ce mois").
"""

from datetime import date
import streamlit as st
from components.design_tokens import T


_HUMEURS = {"": "—", "BIEN": "😊 Bien", "NEUTRE": "😐 Neutre", "STRESSE": "😰 Stressé"}
_HUMEUR_COULEUR = {
    "BIEN":    T.SUCCESS,
    "NEUTRE":  T.WARNING,
    "STRESSE": T.DANGER,
    "":        T.TEXT_LOW,
}
_TAGS_SUGGERES = [
    "achat exceptionnel", "voyage", "santé", "réparation", "cadeau",
    "fête", "rentrée", "urgence", "investissement", "remboursement",
]


def _section(titre: str) -> None:
    st.markdown(
        f'<div style="color:{T.TEXT_LOW};font-size:10px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:2px;'
        f'margin:0 0 12px;padding-bottom:6px;'
        f'border-bottom:1px solid {T.BORDER}">{titre}</div>',
        unsafe_allow_html=True,
    )


def render(ctx: dict) -> None:
    audit   = ctx["audit"]
    db      = audit.db
    user_id = audit.user_id

    st.markdown(
        f'<h2 style="color:{T.TEXT_HIGH};font-weight:900;'
        f'font-size:24px;margin-bottom:4px">📔 Journal Financier</h2>'
        f'<p style="color:{T.TEXT_LOW};font-size:13px;margin-bottom:24px">'
        f'Notez le contexte de vos dépenses inhabituelles — '
        f'le coach s\'en souviendra pour interpréter vos mois atypiques.</p>',
        unsafe_allow_html=True,
    )

    # ── Formulaire nouvelle note ──────────────────────────────────────────────
    _section("Nouvelle Note")

    with st.container():
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_LG};padding:20px;margin-bottom:20px">',
            unsafe_allow_html=True,
        )

        j1, j2 = st.columns([2, 1])
        with j1:
            note_date = st.date_input(
                "Date de l'événement", value=date.today(), key="j_date"
            )
        with j2:
            humeur_label = list(_HUMEURS.values())
            humeur_keys  = list(_HUMEURS.keys())
            humeur_sel   = st.selectbox(
                "Humeur financière", humeur_label, key="j_humeur"
            )
            humeur_val = humeur_keys[humeur_label.index(humeur_sel)]

        note_txt = st.text_area(
            "Contexte / Note",
            placeholder="Ex: J'ai acheté un frigo ce mois (2 800 DH) — dépense exceptionnelle, "
                        "non reproductible. Budget alimentation gonflé aussi à cause du Ramadan.",
            height=120,
            key="j_note",
        )

        tags_sel = st.multiselect(
            "Tags (optionnel)", _TAGS_SUGGERES, key="j_tags"
        )
        tags_str = ", ".join(tags_sel)

        if st.button("📝 Ajouter la note", key="j_save", type="primary"):
            if not note_txt.strip():
                st.warning("La note ne peut pas être vide.")
            else:
                db.ajouter_note_journal(
                    date_entree=str(note_date),
                    note=note_txt.strip(),
                    user_id=user_id,
                    tags=tags_str,
                    humeur=humeur_val,
                )
                st.cache_data.clear()
                st.success("✅ Note ajoutée au journal")
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # ── Liste des notes ───────────────────────────────────────────────────────
    notes = db.get_journal(user_id=user_id, limit=200)

    if not notes:
        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-radius:{T.RADIUS_LG};padding:40px;text-align:center">'
            f'<div style="font-size:32px;margin-bottom:10px">📭</div>'
            f'<div style="color:{T.TEXT_MED};font-size:14px">'
            f'Aucune note pour l\'instant. Commencez à contextualiser vos dépenses !</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    _section(f"{len(notes)} note(s)")

    del_id = st.session_state.get("j_del_id")

    for note in notes:
        nid     = note["id"]
        humeur  = note.get("Humeur", "")
        couleur = _HUMEUR_COULEUR.get(humeur, T.TEXT_LOW)
        tags    = note.get("Tags", "")
        date_e  = note.get("Date_Entree", "")[:10]
        note_tx = note.get("Note", "")

        # ── Confirmation suppression ──────────────────────────────────────────
        if del_id == nid:
            st.warning(f"Supprimer cette note du {date_e} ?")
            dc1, dc2 = st.columns(2)
            with dc1:
                if st.button("✅ Confirmer", key=f"jdok_{nid}", type="primary", use_container_width=True):
                    db.supprimer_note_journal(nid, user_id)
                    st.session_state.j_del_id = None
                    st.rerun()
            with dc2:
                if st.button("❌ Annuler", key=f"jdno_{nid}", use_container_width=True):
                    st.session_state.j_del_id = None
                    st.rerun()
            continue

        # ── Affichage note ────────────────────────────────────────────────────
        tags_html = ""
        if tags:
            tags_pills = "".join(
                f'<span style="background:{T.BG_CARD_ALT};color:{T.TEXT_MED};'
                f'font-size:10px;padding:2px 8px;border-radius:{T.RADIUS_PILL};'
                f'margin-right:4px">{t.strip()}</span>'
                for t in tags.split(",") if t.strip()
            )
            tags_html = f'<div style="margin-top:8px">{tags_pills}</div>'

        humeur_badge = ""
        if humeur:
            humeur_badge = (
                f'<span style="background:{couleur}18;color:{couleur};'
                f'font-size:10px;font-weight:700;padding:2px 8px;'
                f'border-radius:{T.RADIUS_PILL};border:1px solid {couleur}30">'
                f'{_HUMEURS.get(humeur, humeur)}</span>'
            )

        st.markdown(
            f'<div style="background:{T.BG_CARD};border:1px solid {T.BORDER};'
            f'border-left:3px solid {couleur};'
            f'border-radius:{T.RADIUS_MD};padding:16px;margin-bottom:8px">'
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">'
            f'<span style="color:{T.TEXT_MED};font-size:12px;font-weight:600">{date_e}</span>'
            f'{humeur_badge}'
            f'</div>'
            f'<div style="color:{T.TEXT_HIGH};font-size:13px;line-height:1.6">{note_tx}</div>'
            f'{tags_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

        if st.button("🗑️", key=f"jdel_{nid}", help="Supprimer cette note"):
            st.session_state.j_del_id = nid
            st.rerun()
