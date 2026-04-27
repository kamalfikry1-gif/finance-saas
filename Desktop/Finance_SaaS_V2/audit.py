"""
AUDIT.PY — COUCHE INTERMÉDIAIRE (7 RÔLES)
==========================================
Architecture : app.py → audit.py → logic_sqlite.py → db_manager.py → SQLite

Rôles :
  1  Gateway + Validator  — Un seul point d'entrée, valide l'input AVANT logic
  2  Audit Trail          — Chaque action tracée dans AUDIT_LOG (immuable)
  3  Anticipation Engine  — 50/30/20, projections, tendances en arrière-plan
  4  Snapshot Manager     — Cache horodaté, invalide si nouvelles données
  5  UI State Manager     — Construit l'état complet pour app.py
  6  Anomaly Detector     — Détecte doublon / montant suspect AVANT logic
  7  Query Engine         — Route les requêtes complexes vers MoteurAnalyse

Usage :
    audit  = AuditMiddleware("finance_saas.db")
    result = audit.recevoir("CARREFOUR", 45.50, "OUT")
    state  = audit.get_ui_state()
    data   = audit.query("plan_5030_20", mois="04/2026")
"""

import json
import math
import logging
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from db_manager import DatabaseManager
from logic_sqlite import (
    Douane,
    Trieur,
    ComptableBudget,
    MoteurAnalyse,
    ResultatClassification,
)
from config import (
    MOT_CLE_MIN_LEN,
    MOT_CLE_MAX_LEN,
    SEUIL_ANOMALIE_SIGMA,
    HEURE_INHABITUELLE_MIN,
    HEURE_INHABITUELLE_MAX,
    IDENTITES_COACH,
    HUMEUR_COOL,
    HUMEUR_NEUTRE,
    HUMEUR_SERIEUX,
    HUMEUR_SCORE_SERIEUX,
    HUMEUR_TAUX_EP_SERIEUX,
    HUMEUR_SAVINGS_SERIEUX,
    HUMEUR_SAVINGS_COOL_RATIO,
)

logger = logging.getLogger("AUDIT")


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES LOCALES (non exportées dans config car internes à audit)
# ─────────────────────────────────────────────────────────────────────────────

MONTANT_MIN            = 0.01
MONTANT_MAX            = 999_999.0

# Catégories fixes par bucket (ne changent pas selon l'identité)
_CATEGORIES_NEEDS   = {"Logement", "Alimentation", "Transport",
                        "Sante", "Santé", "Vie Quotidienne"}
_CATEGORIES_WANTS   = {"Loisirs", "Abonnements", "Divers"}
_CATEGORIES_SAVINGS = {"Finances Credits", "Finances & Crédits", "Epargne", "Épargne"}


# ─────────────────────────────────────────────────────────────────────────────
# CLASSE PRINCIPALE
# ─────────────────────────────────────────────────────────────────────────────

class AuditMiddleware:
    """
    Couche intermédiaire entre app.py et logic_sqlite.py.

    app.py ne parle JAMAIS directement à logic — tout passe par ici.
    Chaque appel est validé, tracé, protégé, mis en cache.
    """

    def __init__(self, db: DatabaseManager, user_id: int):
        self.db        = db
        self.user_id   = user_id
        self.trieur    = Trieur(self.db, user_id)
        self.comptable = ComptableBudget(self.db, user_id)
        self.moteur    = MoteurAnalyse(self.db, user_id)
        self._identite_cache: Optional[str] = None
        logger.info(f"AuditMiddleware initialisé — user_id={user_id}")

    # =========================================================================
    # INIT — TABLES PROPRES A AUDIT
    # =========================================================================

    # =========================================================================
    # PRÉFÉRENCES & IDENTITÉ DU COACH
    # =========================================================================

    def get_preference(self, cle: str, defaut: str = "") -> str:
        """Lit une préférence depuis la DB (filtrée par user_id)."""
        return self.db.get_preference(cle, self.user_id, defaut) or defaut

    def set_preference(self, cle: str, valeur: str) -> None:
        """Modifie une préférence et invalide les snapshots UI."""
        self.db.set_preference(cle, valeur, self.user_id)
        if cle == "coach_identite":
            self._identite_cache = None
        self.invalider_snapshots()
        self._log("PREFS", "SET_PREFERENCE", {"cle": cle, "valeur": valeur})

    def get_identite(self) -> str:
        """Retourne l'identité active du coach (défaut : EQUILIBRE).
        Mémoïsé sur l'instance — invalidé par set_identite/set_preference."""
        if self._identite_cache is not None:
            return self._identite_cache
        identite = self.get_preference("coach_identite", "EQUILIBRE").upper()
        if identite not in IDENTITES_COACH:
            identite = "EQUILIBRE"
        self._identite_cache = identite
        return identite

    def set_identite(self, identite: str) -> None:
        """
        Change l'identité du coach.
        Valeurs : 'BATISSEUR' | 'EQUILIBRE' | 'STRATEGE' | 'LIBERE'
        """
        identite = identite.strip().upper()
        if identite not in IDENTITES_COACH:
            raise ValueError(
                f"Identite '{identite}' invalide. "
                f"Valeurs : {list(IDENTITES_COACH.keys())}"
            )
        self.set_preference("coach_identite", identite)
        logger.info(f"Identite coach -> {identite}")

    def _get_mapping_5030_20(self) -> Dict[str, Any]:
        """
        Construit le mapping 50/30/20 depuis l'identité active.
        Les ratios viennent de l'identité, les catégories sont fixes.
        """
        identite = self.get_identite()
        cfg      = IDENTITES_COACH[identite]
        return {
            "Needs":   {"cible_pct": cfg["needs_pct"],   "categories": _CATEGORIES_NEEDS},
            "Wants":   {"cible_pct": cfg["wants_pct"],   "categories": _CATEGORIES_WANTS},
            "Savings": {"cible_pct": cfg["savings_pct"], "categories": _CATEGORIES_SAVINGS},
        }

    # =========================================================================
    # HUMEUR DU COACH
    # =========================================================================

    def _calculer_humeur(
        self,
        score:       Dict[str, Any],
        bilan:       Any,
        bvr_5030:    Dict[str, Any],
    ) -> str:
        """
        Détermine l'humeur du coach selon 3 critères :

          COOL    — solde positif ET score >= seuil identité ET Savings on track
          SERIEUX — solde negatif OU score critique OU Savings < 5%
          NEUTRE  — tout le reste

        Paramètres :
          score    — dict issu de get_score_sante_financiere()
          bilan    — BilanMensuel du mois
          bvr_5030 — dict issu de get_analyse_5030_20()
        """
        identite    = self.get_identite()
        cfg         = IDENTITES_COACH[identite]
        score_val   = float(score.get("score", 0))
        taux_ep     = float(score.get("taux_epargne_pct", 0))
        solde       = float(bilan.evolution_dh)
        savings_reel_pct = float(
            bvr_5030.get("buckets", {})
                    .get("Savings", {})
                    .get("reel_pct", 0)
        )
        # When no explicit Savings transactions exist, taux_ep (already
        # corrected to use net solde as fallback) is the true savings rate.
        effective_savings = savings_reel_pct if savings_reel_pct > 0 else taux_ep

        # ── SERIEUX (conditions bloquantes) ───────────────────────────────────
        if solde < 0:
            return HUMEUR_SERIEUX
        if score_val < HUMEUR_SCORE_SERIEUX:
            return HUMEUR_SERIEUX
        if taux_ep < HUMEUR_TAUX_EP_SERIEUX:
            return HUMEUR_SERIEUX
        if effective_savings < HUMEUR_SAVINGS_SERIEUX:
            return HUMEUR_SERIEUX

        # ── COOL (toutes les conditions positives) ────────────────────────────
        if (solde > 0
                and score_val >= cfg["humeur_seuil_score"]
                and effective_savings >= cfg["savings_pct"] * HUMEUR_SAVINGS_COOL_RATIO):
            return HUMEUR_COOL

        return HUMEUR_NEUTRE

    # =========================================================================
    # OBJECTIFS
    # =========================================================================

    def creer_objectif(
        self, nom: str, montant_cible: float, date_cible: str
    ) -> Dict[str, Any]:
        """
        Crée un objectif d'épargne et le sauvegarde.

        Paramètres :
          nom           — Libellé du projet (ex: 'PC Gaming', 'Voyage Tokyo').
          montant_cible — Montant à atteindre en DH.
          date_cible    — Mois cible format 'MM/YYYY'.

        Retourne le dict de simulation d'impact + l'id créé.
        """
        objectif_id = self.db.creer_objectif(nom, montant_cible, date_cible, self.user_id)

        # Calcul de faisabilité
        simulation = self.moteur.simuler_objectif_epargne(
            cible_dh=montant_cible,
            nb_mois=self._mois_jusqu_a(date_cible),
        )

        self._log(
            "OBJECTIF", "CREE",
            {"nom": nom, "cible": montant_cible, "date": date_cible},
            {"id": objectif_id, "atteignable": simulation.get("atteignable")},
        )
        return {"id": objectif_id, **simulation}

    def get_objectifs(self, statut: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retourne les objectifs avec leur progression en %.

        Statut : 'EN_COURS' | 'ATTEINT' | 'ABANDONNE' | None (tous).
        """
        objectifs = self.db.get_objectifs(self.user_id, statut)
        cumul     = self.moteur.get_cumul_epargne()

        for obj in objectifs:
            cible  = float(obj.get("Montant_Cible", 0))
            actuel = float(obj.get("Montant_Actuel", 0))
            obj["progression_pct"] = round(actuel / cible * 100, 1) if cible > 0 else 0.0
            obj["epargne_cumul"]   = cumul
            obj["manque_dh"]       = round(max(0.0, cible - actuel), 2)

        return objectifs

    def abandonner_objectif(self, objectif_id: int) -> None:
        """Marque un objectif comme abandonné."""
        self.db.abandonner_objectif(objectif_id, self.user_id)
        self._log("OBJECTIF", "ABANDONNE", {"id": objectif_id})

    @staticmethod
    def _mois_jusqu_a(date_cible: str) -> int:
        """Nombre de mois entre aujourd'hui et date_cible 'MM/YYYY' (min 1)."""
        try:
            m, y   = int(date_cible[:2]), int(date_cible[3:])
            now    = datetime.now()
            delta  = (y - now.year) * 12 + (m - now.month)
            return max(1, delta)
        except Exception:
            return 12

    # =========================================================================
    # OBJECTIFS V2 (views/objectif.py)
    # =========================================================================

    def creer_objectif_v2(self, nom: str, type_obj: str, montant_cible: float,
                          date_cible: str, **kwargs) -> int:
        oid = self.db.creer_objectif_v2(
            nom, type_obj, montant_cible, date_cible,
            self.user_id, **kwargs,
        )
        self.invalider_snapshots()
        self._log("OBJECTIF", "CREE_V2", {"nom": nom, "type": type_obj, "cible": montant_cible})
        return oid

    def get_objectifs_v2(self, type_obj: Optional[str] = None) -> List[Dict]:
        return self.db.get_objectifs_v2(self.user_id, type_obj)

    def maj_objectif_actuel(self, objectif_id: int, montant_actuel: float) -> None:
        self.db.maj_objectif_actuel(objectif_id, montant_actuel, self.user_id)
        self.invalider_snapshots()
        self._log("OBJECTIF", "MAJ_ACTUEL", {"id": objectif_id, "montant": montant_actuel})

    def supprimer_objectif(self, objectif_id: int) -> None:
        self.db.supprimer_objectif(objectif_id, self.user_id)
        self.invalider_snapshots()
        self._log("OBJECTIF", "SUPPRIME", {"id": objectif_id})

    # =========================================================================
    # JOURNAL (views/journal.py)
    # =========================================================================

    def ajouter_note_journal(self, date_entree: str, note: str,
                              tags: str = "", humeur: str = "") -> int:
        nid = self.db.ajouter_note_journal(date_entree, note, self.user_id, tags, humeur)
        self._log("JOURNAL", "AJOUT", {"date": date_entree, "note": note[:80]})
        return nid

    def get_journal(self, limit: int = 200) -> List[Dict]:
        return self.db.get_journal(self.user_id, limit)

    def supprimer_note_journal(self, note_id: int) -> None:
        self.db.supprimer_note_journal(note_id, self.user_id)
        self._log("JOURNAL", "SUPPRIME", {"id": note_id})

    # =========================================================================
    # TRANSACTIONS (views/historique.py)
    # =========================================================================

    def get_categories(self) -> List[str]:
        with self.db.connexion() as conn:
            rows = conn.execute(
                "SELECT DISTINCT Categorie FROM CATEGORIES ORDER BY Categorie"
            ).fetchall()
        return [r[0] for r in rows]

    def get_sous_categories(self, categorie: str) -> List[str]:
        with self.db.connexion() as conn:
            rows = conn.execute(
                "SELECT Sous_Categorie FROM CATEGORIES WHERE Categorie=%s ORDER BY Sous_Categorie",
                (categorie,)
            ).fetchall()
        return [r[0] for r in rows]

    def get_transactions(self, mois: str, sens: str = "Tous",
                         categorie: str = "Toutes") -> List[Dict]:
        from db_manager import _canon_dict
        parts = mois.split("/")
        mois_db = f"{parts[1]}-{parts[0]}"
        conditions = ["Date_Valeur LIKE %s", "user_id = %s"]
        params: list = [f"{mois_db}%", self.user_id]
        if sens != "Tous":
            conditions.append("Sens = %s")
            params.append(sens)
        if categorie != "Toutes":
            conditions.append("Categorie = %s")
            params.append(categorie)
        where = " AND ".join(conditions)
        with self.db.connexion() as conn:
            rows = conn.execute(
                f"SELECT * FROM TRANSACTIONS WHERE {where} ORDER BY Date_Valeur DESC, Date_Saisie DESC",
                params,
            ).fetchall()
        return [_canon_dict(r) for r in rows]

    def supprimer_transaction(self, tx_id: str) -> None:
        with self.db.connexion() as conn:
            conn.execute(
                "DELETE FROM TRANSACTIONS WHERE ID_Unique = %s AND user_id = %s",
                (tx_id, self.user_id),
            )
        self.invalider_snapshots()
        self._log("TRANSACTION", "SUPPRIME", {"id": tx_id})

    def modifier_transaction(self, tx_id: str, libelle: str, montant: float,
                              categorie: str, sous_categorie: str, date_valeur: str,
                              tags: str = "", contact: str = "") -> None:
        with self.db.connexion() as conn:
            conn.execute(
                """UPDATE TRANSACTIONS
                   SET Libelle=%s, Montant=%s, Categorie=%s, Sous_Categorie=%s,
                       Date_Valeur=%s, Tags=%s, Contact=%s
                   WHERE ID_Unique=%s AND user_id=%s""",
                (libelle, montant, categorie, sous_categorie, date_valeur,
                 tags.strip(), contact.strip(), tx_id, self.user_id),
            )
        self.invalider_snapshots()
        self._log("TRANSACTION", "MODIFIE", {"id": tx_id, "libelle": libelle})

    def update_tags_contact(self, tx_id: str, tags: str, contact: str) -> None:
        """Attaches tags and contact to an existing transaction (post-save enrichment)."""
        if not tags.strip() and not contact.strip():
            return
        with self.db.connexion() as conn:
            conn.execute(
                "UPDATE TRANSACTIONS SET Tags=%s, Contact=%s WHERE ID_Unique=%s AND user_id=%s",
                (tags.strip(), contact.strip(), tx_id, self.user_id),
            )

    # =========================================================================
    # AGE OF MONEY
    # =========================================================================

    def age_of_money(self, solde: float, burn_rate_journalier: float) -> Optional[int]:
        """
        Âge moyen de l'argent en jours (inspiré de YNAB).
        solde / burn_rate = combien de jours ton solde peut couvrir.
        """
        if burn_rate_journalier <= 0 or solde <= 0:
            return None
        return int(solde / burn_rate_journalier)

    # =========================================================================
    # DARET TRACKER
    # =========================================================================

    def get_darets(self) -> List[Dict]:
        from db_manager import _canon_dict
        with self.db.connexion() as conn:
            rows = conn.execute(
                "SELECT * FROM DARETS WHERE user_id=%s AND Statut='ACTIF' ORDER BY id DESC",
                (self.user_id,),
            ).fetchall()
        return [_canon_dict(r) for r in rows]

    def creer_daret(self, nom: str, montant_mensuel: float, membres: list,
                    date_debut: str, notes: str = "",
                    tirage_seed: Optional[int] = None) -> Dict[str, Any]:
        """Create a daret. If tirage_seed is provided, the (already-shuffled)
        members order is recorded with the seed so anyone can verify fairness:
            random.Random(seed).shuffle(original_list) → recorded order.

        Returns: {"id": int, "invite_token": str} of the created daret.
        """
        import json, secrets
        invite_token = secrets.token_urlsafe(12)
        new_id = None
        with self.db.connexion() as conn:
            cur = conn.execute(
                """INSERT INTO DARETS
                   (Nom, Montant_Mensuel, Nb_Membres, Membres_JSON, Tour_Actuel,
                    Date_Debut, Statut, Notes, invite_token, Tirage_Seed, user_id)
                   VALUES (%s,%s,%s,%s,0,%s,'ACTIF',%s,%s,%s,%s)
                   RETURNING id""",
                (nom.strip(), montant_mensuel, len(membres),
                 json.dumps(membres, ensure_ascii=False),
                 date_debut, notes.strip(), invite_token, tirage_seed, self.user_id),
            )
            row = cur.fetchone() if cur else None
            if row:
                new_id = row[0] if not hasattr(row, "keys") else row["id"]
        return {"id": new_id, "invite_token": invite_token}

    def avancer_tour_daret(self, daret_id: int) -> None:
        with self.db.connexion() as conn:
            conn.execute(
                """UPDATE DARETS SET Tour_Actuel = Tour_Actuel + 1
                   WHERE id=%s AND user_id=%s""",
                (daret_id, self.user_id),
            )

    def cloturer_daret(self, daret_id: int) -> None:
        with self.db.connexion() as conn:
            conn.execute(
                "UPDATE DARETS SET Statut='CLOTURE' WHERE id=%s AND user_id=%s",
                (daret_id, self.user_id),
            )
        self._log("DARET", "CLOTURE", {"id": daret_id})

    # =========================================================================
    # A_CLASSIFIER — mots-clés inconnus + règles utilisateur
    # =========================================================================

    def get_a_classifier(self) -> List[Dict]:
        return self.db.get_mots_cles_inconnus(self.user_id)

    def valider_classification(self, mot_cle: str, sens: str,
                               categorie: str, sous_categorie: str) -> int:
        """
        Persist a user rule, mark the keyword as enriched, re-classify
        matching A_CLASSIFIER transactions. Returns nb of transactions fixed.
        """
        self.db.sauvegarder_regle(sens, mot_cle, categorie, sous_categorie, self.user_id)
        self.db.marquer_enrichi(mot_cle, sens, self.user_id)
        nb = self.db.reclassifier_par_mot_cle(mot_cle, sens, categorie, sous_categorie, self.user_id)
        self._log("CLASSIFIER", "REGLE_VALIDEE",
                  {"mot_cle": mot_cle, "categorie": categorie, "sous_categorie": sous_categorie},
                  {"nb_transactions": nb})
        return nb

    def ignorer_mot_cle(self, mot_cle: str, sens: str) -> None:
        """Mark as enriched without creating a rule — user explicitly skips it."""
        self.db.marquer_enrichi(mot_cle, sens, self.user_id)

    # =========================================================================
    # PLAFONDS (views/plafond.py)
    # =========================================================================

    def get_plafonds_categories(self) -> List[Dict]:
        return self.db.get_plafonds_categories()

    def set_plafond_categorie(self, categorie: str, sous_categorie: str,
                               plafond: float) -> None:
        self.db.set_plafond_categorie(categorie, sous_categorie, plafond)
        self.invalider_snapshots()
        self._log("PLAFOND", "SET", {"cat": categorie, "scat": sous_categorie, "val": plafond})

    def get_depenses_mois(self, mois: str) -> Dict:
        parts = mois.split("/")
        mois_db = f"{parts[1]}-{parts[0]}"
        with self.db.connexion() as conn:
            rows = conn.execute(
                """SELECT Categorie, Sous_Categorie, COALESCE(SUM(Montant), 0) as total
                   FROM TRANSACTIONS
                   WHERE Sens='OUT' AND user_id=%s AND Date_Valeur LIKE %s AND Statut='VALIDE'
                   GROUP BY Categorie, Sous_Categorie""",
                (self.user_id, f"{mois_db}%"),
            ).fetchall()
        return {(r[0], r[1]): float(r[2] or 0) for r in rows}

    # =========================================================================
    # ROLE 2 — AUDIT TRAIL  (privé — appelé par tous les autres rôles)
    # =========================================================================

    def _log(
        self,
        role:       str,
        action:     str,
        input_raw:  Any            = None,
        output_raw: Any            = None,
        methode:    Optional[str]  = None,
        score:      Optional[float] = None,
        statut:     str            = "OK",
    ) -> None:
        """Trace immuable dans AUDIT_LOG. Jamais d'exception levée depuis ici."""
        try:
            def _ser(obj):
                return json.dumps(obj, ensure_ascii=False, default=str) if obj is not None else None

            with self.db.connexion() as conn:
                conn.execute(
                    """
                    INSERT INTO AUDIT_LOG
                        (Role, Action, Input_Raw, Output_Raw, Methode, Score, Statut, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (role, action, _ser(input_raw), _ser(output_raw),
                     methode, score, statut, self.user_id),
                )
        except Exception as e:
            logger.error(f"AUDIT_LOG echec ecriture : {e}")

    def get_audit_log(self, limit: int = 50, role: Optional[str] = None) -> List[Dict]:
        with self.db.connexion() as conn:
            if role:
                rows = conn.execute(
                    "SELECT * FROM AUDIT_LOG WHERE user_id = %s AND Role = %s ORDER BY Timestamp DESC LIMIT %s",
                    (self.user_id, role.upper(), limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM AUDIT_LOG WHERE user_id = %s ORDER BY Timestamp DESC LIMIT %s",
                    (self.user_id, limit)
                ).fetchall()
        from db_manager import _canon_dict
        return [_canon_dict(r) for r in rows]

    # =========================================================================
    # ROLE 4 — SNAPSHOT MANAGER  (privé)
    # =========================================================================

    def invalider_snapshots(self, prefixe: Optional[str] = None) -> None:
        """
        No-op conservé pour compatibilité.

        L'ancien cache DB SNAPSHOTS est remplacé par @st.cache_data
        (core/cache.py). L'invalidation se fait côté UI via
        core.cache.invalider() après chaque écriture.
        """
        return

    # =========================================================================
    # ROLE 6 — ANOMALY DETECTOR  (avant logic)
    # =========================================================================

    def _detecter_anomalie(
        self,
        mot_cle:     str,
        montant:     float,
        sens:        str,
        date_valeur: date,
    ) -> Dict[str, Any]:
        """
        Détecte les anomalies AVANT d'envoyer à logic.

        Checks (dans l'ordre de sévérité) :
          A. Doublon récent    — même libellé + montant dans les 2 dernières minutes
          B. Montant suspect   — Z-score >= SEUIL_ANOMALIE_SIGMA vs historique sens
          C. Heure inhabituelle — entre 01h00 et 05h59

        Retourne :
          {
            safe:      bool,
            anomalies: [{ type, message, severite }],
            action:    'OK' | 'CONFIRMER' | 'BLOQUER'
          }
        """
        anomalies: List[Dict] = []
        mot_norm = Douane.normaliser_texte(mot_cle)

        # ── A : Doublon récent ────────────────────────────────────────────────
        fenetre = (datetime.now() - timedelta(seconds=120)).strftime("%Y-%m-%d %H:%M:%S")
        with self.db.connexion() as conn:
            recents = conn.execute(
                """
                SELECT Libelle, Montant FROM TRANSACTIONS
                WHERE Date_Saisie >= %s AND Statut = 'VALIDE' AND user_id = %s
                """,
                (fenetre, self.user_id)
            ).fetchall()

        for r in recents:
            if (Douane.normaliser_texte(str(r[0])) == mot_norm
                    and abs(abs(float(r[1])) - montant) < 0.01):
                anomalies.append({
                    "type":     "DOUBLON",
                    "message":  f"'{mot_cle}' / {montant:.2f} DH deja enregistre dans les 2 dernieres minutes",
                    "severite": "CRITIQUE",
                })
                break  # Un doublon suffit

        # ── B : Montant suspect (Z-score historique par sens) ─────────────────
        with self.db.connexion() as conn:
            row_stats = conn.execute(
                """
                SELECT
                    AVG(ABS(Montant)),
                    AVG(ABS(Montant) * ABS(Montant)) - AVG(ABS(Montant)) * AVG(ABS(Montant))
                FROM TRANSACTIONS
                WHERE Sens = %s AND Statut = 'VALIDE' AND ABS(Montant) > 0 AND user_id = %s
                """,
                (sens, self.user_id)
            ).fetchone()

        if row_stats and row_stats[0]:
            moyenne    = float(row_stats[0])
            variance   = max(float(row_stats[1] or 0), 0.0)
            ecart_type = math.sqrt(variance)
            if ecart_type > 0:
                z = (montant - moyenne) / ecart_type
                if z >= SEUIL_ANOMALIE_SIGMA:
                    anomalies.append({
                        "type":     "MONTANT_SUSPECT",
                        "message":  (
                            f"{montant:.2f} DH est {z:.1f}x au-dessus de la moyenne "
                            f"historique ({moyenne:.2f} DH)"
                        ),
                        "severite": "WARNING",
                    })

        # ── C : Heure inhabituelle ────────────────────────────────────────────
        heure = datetime.now().hour
        if HEURE_INHABITUELLE_MIN <= heure <= HEURE_INHABITUELLE_MAX:
            anomalies.append({
                "type":     "HEURE_INHABITUELLE",
                "message":  f"Transaction saisie a {heure:02d}h — heure inhabituelle",
                "severite": "INFO",
            })

        # ── Décision finale ───────────────────────────────────────────────────
        a_critique = any(a["severite"] == "CRITIQUE" for a in anomalies)
        a_warning  = any(a["severite"] == "WARNING"  for a in anomalies)
        action     = "BLOQUER" if a_critique else ("CONFIRMER" if a_warning else "OK")

        return {
            "safe":      not a_critique,
            "anomalies": anomalies,
            "action":    action,
        }

    # =========================================================================
    # ROLE 1 — GATEWAY + VALIDATOR  (point d'entrée unique)
    # =========================================================================

    def _valider_input(self, mot_cle: str, montant: Any, sens: str) -> Optional[str]:
        """
        Valide le format de la saisie.
        Retourne None si tout est valide, message d'erreur sinon.
        """
        if not mot_cle or not isinstance(mot_cle, str) or not mot_cle.strip():
            return "Libelle manquant"
        if len(mot_cle.strip()) < MOT_CLE_MIN_LEN:
            return f"Libelle trop court (minimum {MOT_CLE_MIN_LEN} caracteres)"
        if len(mot_cle.strip()) > MOT_CLE_MAX_LEN:
            return f"Libelle trop long (maximum {MOT_CLE_MAX_LEN} caracteres)"

        try:
            m = float(montant)
        except (ValueError, TypeError):
            return "Montant invalide — doit etre un nombre"
        if m <= 0:
            return "Montant doit etre positif (> 0)"
        if m < MONTANT_MIN:
            return f"Montant trop faible (minimum {MONTANT_MIN} DH)"
        if m > MONTANT_MAX:
            return f"Montant trop eleve (maximum {MONTANT_MAX:,.0f} DH)"

        if str(sens).strip().upper() not in ("IN", "OUT"):
            return f"Sens invalide — attendu 'IN' ou 'OUT', recu '{sens}'"

        return None  # Tout valide

    def recevoir(
        self,
        mot_cle:     str,
        montant:     float,
        sens:        str,
        date_valeur: Optional[date] = None,
        forcer:      bool = False,
        source:      str = "SAISIE",
    ) -> Dict[str, Any]:
        """
        POINT D'ENTREE UNIQUE pour toute saisie de transaction.

        Paramètres :
          mot_cle     — Libellé de la transaction (ex: 'CARREFOUR MARKET').
          montant     — Montant positif en DH (le sens détermine le signe).
          sens        — 'IN' (entrée) ou 'OUT' (sortie).
          date_valeur — Date de la transaction (défaut: aujourd'hui).
          forcer      — True = bypasse la demande de confirmation (anomalie WARNING).

        Retourne un dict avec les clés :
          OK      → { id_unique, montant, categorie, sous_categorie, methode,
                      score, action:'OK', anomalies }
          BLOQUER → { id_unique:None, action:'BLOQUER', message, anomalies }
          CONFIRMER→ { id_unique:None, action:'CONFIRMER', message, anomalies }
          REJETE  → { id_unique:None, action:'REJETE', erreur }

        Étapes internes :
          1. Validation format             (Rôle 1)
          2. Détection anomalies           (Rôle 6)
          3. Classification via Trieur     (logic)
          4. Enregistrement ComptableBudget(logic)
          5. Anticipation arrière-plan     (Rôle 3)
          6. Log Audit Trail               (Rôle 2)
          7. Invalidation snapshot UI      (Rôle 4)
        """
        if date_valeur is None:
            date_valeur = date.today()

        input_raw = {
            "mot_cle":     mot_cle,
            "montant":     montant,
            "sens":        sens,
            "date_valeur": str(date_valeur),
        }

        # ── Étape 1 : Validation format ───────────────────────────────────────
        erreur = self._valider_input(mot_cle, montant, sens)
        if erreur:
            self._log("GATEWAY", "VALIDATION_ECHEC", input_raw,
                      {"erreur": erreur}, statut="ERREUR")
            return {"id_unique": None, "action": "REJETE", "erreur": erreur}

        sens      = str(sens).strip().upper()
        mot_cle   = mot_cle.strip()
        montant   = abs(float(montant))

        # ── Étape 2 : Détection anomalies ────────────────────────────────────
        anomalie = self._detecter_anomalie(mot_cle, montant, sens, date_valeur)

        if anomalie["action"] == "BLOQUER":
            self._log("ANOMALY", "DOUBLON_BLOQUE", input_raw,
                      {"anomalies": anomalie["anomalies"]}, statut="BLOQUE")
            return {
                "id_unique": None,
                "action":    "BLOQUER",
                "anomalies": anomalie["anomalies"],
                "message":   anomalie["anomalies"][0]["message"],
            }

        if anomalie["action"] == "CONFIRMER" and not forcer:
            self._log("ANOMALY", "CONFIRMATION_REQUISE", input_raw,
                      {"anomalies": anomalie["anomalies"]}, statut="WARN")
            return {
                "id_unique": None,
                "action":    "CONFIRMER",
                "anomalies": anomalie["anomalies"],
                "message":   anomalie["anomalies"][0]["message"],
            }

        # ── Étape 3 : Classification (Trieur) ────────────────────────────────
        classification: ResultatClassification = self.trieur.classifier(mot_cle, sens)

        # ── Étape 4 : Enregistrement (ComptableBudget) ───────────────────────
        resultat = self.comptable.enregistrer_transaction(
            date_valeur, mot_cle, montant, classification, source=source
        )

        if resultat.get("doublon"):
            self._log("GATEWAY", "DOUBLON_INTERNE", input_raw,
                      {"message": resultat["message"]}, statut="WARN")
            return {
                "id_unique": None,
                "action":    "BLOQUER",
                "message":   resultat["message"],
                "anomalies": [],
            }

        # ── Log Audit Trail ──────────────────────────────────────────────────
        output_data = {
            "id_unique":      resultat["id_unique"],
            "montant":        resultat["montant"],
            "categorie":      classification.categorie,
            "sous_categorie": classification.sous_categorie,
            "methode":        classification.methode,
        }
        self._log(
            "GATEWAY", "TRANSACTION_OK",
            input_raw, output_data,
            methode=classification.methode,
            score=classification.score,
            statut="OK",
        )

        return {
            "id_unique":      resultat["id_unique"],
            "montant":        resultat["montant"],
            "categorie":      classification.categorie,
            "sous_categorie": classification.sous_categorie,
            "methode":        classification.methode,
            "score":          classification.score,
            "action":         "OK",
            "anomalies":      anomalie["anomalies"],
        }

    # =========================================================================
    # ROLE 5 — UI STATE MANAGER
    # =========================================================================

    def get_ui_state(self, mois: Optional[str] = None) -> Dict[str, Any]:
        """
        Construit l'état complet de l'interface — app.py l'affiche sans aucun calcul.

        app.py est "stupide" : elle lit ce dict et rend l'interface.
        Toute la logique de décision (masquer, colorer, alerter) est ici.

        Structure retournée :
        {
          mois, bilan, budget_5030_20, repartition,
          alertes, badges_5030_20, projection,
          score_sante, message_coach, snapshot_ts
        }

        Le résultat est mis en cache côté Streamlit (core/cache.py) :
          - Valide 5 minutes
          - Invalide via ui_cache.invalider() après toute écriture
        """
        mois_str = mois or datetime.now().strftime("%m/%Y")

        # ── Calculs via MoteurAnalyse ─────────────────────────────────────────
        identite    = self.get_identite()
        mapping     = self._get_mapping_5030_20()
        seuil_al    = float(IDENTITES_COACH[identite].get("seuil_alerte", 80))

        bilan       = self.moteur.get_bilan_mensuel(mois_str)
        bvr_5030    = self.moteur.get_analyse_5030_20(mois_str, mapping=mapping)
        repartition = self.moteur.get_repartition_par_categorie(mois_str)
        projection  = self.moteur.get_projection_fin_mois(mois_str)
        score       = self.moteur.get_score_sante_financiere(mois_str)
        alertes_raw = self.moteur.get_alertes_seuil(seuil_al, mois_str)

        # ── Humeur du coach ───────────────────────────────────────────────────
        humeur = self._calculer_humeur(score, bilan, bvr_5030)

        # ── Alertes formatées pour app.py ─────────────────────────────────────
        alertes_ui: List[Dict] = []
        for a in alertes_raw:
            alertes_ui.append({
                "message": (
                    f"{a['sous_categorie']} — {a['taux_pct']:.0f}% du budget "
                    f"({a['reel']:.0f} / {a['budget']:.0f} DH)"
                ),
                "couleur": "red" if a["niveau_alerte"] == "CRITIQUE" else "orange",
                "type":    a["niveau_alerte"],
                "categorie":      a["categorie"],
                "sous_categorie": a["sous_categorie"],
            })

        # ── Badges 50/30/20 ───────────────────────────────────────────────────
        badges: Dict[str, Any] = {}
        for bucket, info in bvr_5030.get("buckets", {}).items():
            reel_pct  = info.get("reel_pct", 0.0)
            cible_pct = info.get("cible_pct", 0.0)
            ecart     = info.get("ecart_pct", 0.0)
            couleur   = (
                "green"  if abs(ecart) <= 5  else
                "orange" if abs(ecart) <= 15 else
                "red"
            )
            badges[bucket] = {
                "reel_dh":   info.get("reel_dh",  0.0),
                "cible_dh":  info.get("cible_dh", 0.0),
                "reel_pct":  reel_pct,
                "cible_pct": cible_pct,
                "ecart_pct": ecart,
                "couleur":   couleur,
                "statut":    info.get("statut", "OK"),
            }

        # ── Message coach (identité + humeur) ────────────────────────────────
        message_coach = self._generer_message_coach(
            score, alertes_raw, bvr_5030, humeur, identite
        )

        # ── Construction du state ─────────────────────────────────────────────
        state: Dict[str, Any] = {
            "mois": mois_str,
            "bilan": {
                "revenus":       bilan.revenus,
                "depenses":      abs(bilan.depenses),
                "solde":         bilan.evolution_dh,
                "epargne_cumul": self.moteur.get_cumul_epargne(),
            },
            "budget_5030_20":      bvr_5030,
            "repartition":         (
                repartition.to_dict("records")
                if not repartition.empty else []
            ),
            "alertes":             alertes_ui,
            "badges_5030_20":      badges,
            "projection":          projection,
            "score_sante":         score,
            "message_coach":       message_coach,
            "humeur_coach":        humeur,
            "identite_coach":      identite,
            "snapshot_ts":         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        logger.debug(
            "UI_STATE_CONSTRUIT mois=%s nb_alertes=%d score=%s",
            mois_str, len(alertes_ui), score.get("score"),
        )

        return state

    def _generer_message_coach(
        self,
        score:    Dict[str, Any],
        alertes:  List[Dict],
        bvr_5030: Dict[str, Any],
        humeur:   str,
        identite: str,
    ) -> str:
        """
        Génère un message personnalisé selon la matrice IDENTITE × HUMEUR.

        Matrice (identite × humeur) → ton + contenu :

          BATISSEUR × COOL    → Factuel + chiffre épargne atteint
          BATISSEUR × NEUTRE  → Chiffre manquant + action précise
          BATISSEUR × SERIEUX → Alerte froide, chiffres bruts, pas de formule de politesse

          EQUILIBRE × COOL    → Encouragement chaleureux
          EQUILIBRE × NEUTRE  → Conseil doux, pédagogique
          EQUILIBRE × SERIEUX → Rappel ferme mais bienveillant

          STRATEGE  × COOL    → Avance vers objectif chiffrée
          STRATEGE  × NEUTRE  → Écart vs objectif + levier concret
          STRATEGE  × SERIEUX → Alerte sur la trajectoire, date impactée

          LIBERE    × COOL    → Félicitation décontractée
          LIBERE    × NEUTRE  → Identifie le gaspillage silencieux
          LIBERE    × SERIEUX → Nomme directement le poste problème
        """
        buckets    = bvr_5030.get("buckets", {})
        savings    = buckets.get("Savings", {})
        wants      = buckets.get("Wants", {})
        needs      = buckets.get("Needs", {})
        taux_ep    = float(score.get("taux_epargne_pct", 0.0))
        score_val  = float(score.get("score", 0))
        niveau     = score.get("niveau", "MOYEN")
        manque_ep  = round(
            float(savings.get("cible_dh", 0)) - float(savings.get("reel_dh", 0)), 0
        )
        scat_alerte = alertes[0].get("sous_categorie", "") if alertes else ""
        wants_pct   = float(wants.get("reel_pct", 0))
        savings_pct = float(savings.get("reel_pct", 0))
        savings_cible = float(savings.get("cible_pct", 20))

        # ══════════════════════════════════════════════════════════════════════
        # BATISSEUR — factuel, froid, chiffres bruts
        # ══════════════════════════════════════════════════════════════════════
        if identite == "BATISSEUR":
            if humeur == HUMEUR_COOL:
                if taux_ep >= 40:
                    return (
                        f"Epargne : {taux_ep:.1f}% — objectif {savings_cible:.0f}% largement depasse. "
                        f"Score {score_val:.0f}/100. Capital inactif : alloue-le."
                    )
                return (
                    f"Epargne : {taux_ep:.1f}% — objectif {savings_cible:.0f}% atteint. "
                    f"Score {score_val:.0f}/100. Aucune action requise."
                )
            if humeur == HUMEUR_NEUTRE:
                return (
                    f"Epargne a {taux_ep:.1f}% vs cible {savings_cible:.0f}%. "
                    f"Manque : {manque_ep:.0f} DH. Identifier les Desirs a couper."
                )
            # SERIEUX
            if scat_alerte:
                return (
                    f"ALERTE — '{scat_alerte}' depasse le budget. "
                    f"Epargne : {taux_ep:.1f}%. Score : {score_val:.0f}/100. "
                    f"Reduction immediate."
                )
            return (
                f"Situation degradee. Score {score_val:.0f}/100. "
                f"Epargne {taux_ep:.1f}%. Revisez les postes Desirs et Besoins."
            )

        # ══════════════════════════════════════════════════════════════════════
        # EQUILIBRE — bienveillant, pédagogique
        # ══════════════════════════════════════════════════════════════════════
        if identite == "EQUILIBRE":
            if humeur == HUMEUR_COOL:
                if taux_ep >= 40:
                    return (
                        f"Excellent mois, khoya ! Tu epargnes {taux_ep:.1f}% — Score {score_val:.0f}/100. "
                        f"Cet argent dort. Pense a le placer : fonds, objectif, ou investissement."
                    )
                return (
                    f"Bonne gestion ce mois ! Score {score_val:.0f}/100. "
                    f"Tu epargnes {taux_ep:.1f}% — continue comme ca."
                )
            if humeur == HUMEUR_NEUTRE:
                if manque_ep > 0:
                    return (
                        f"Presque bien ! Il manque {manque_ep:.0f} DH pour atteindre "
                        f"l'objectif epargne. Essaie de reduire un peu les Loisirs."
                    )
                return (
                    f"Score {score_val:.0f}/100 — quelques ajustements suffiraient "
                    f"pour passer au niveau superieur."
                )
            # SERIEUX
            if scat_alerte:
                return (
                    f"Attention — '{scat_alerte}' a depasse son budget. "
                    f"C'est le bon moment pour faire le point et recadrer les depenses."
                )
            return (
                f"Le solde est sous pression ce mois. "
                f"Concentre-toi sur les essentiels et mets de cote meme un petit montant."
            )

        # ══════════════════════════════════════════════════════════════════════
        # STRATEGE — orienté objectif, trajectoire
        # ══════════════════════════════════════════════════════════════════════
        if identite == "STRATEGE":
            objectifs = self.get_objectifs("EN_COURS")
            obj_str   = (
                f"Objectif '{objectifs[0]['Nom']}' : {objectifs[0].get('progression_pct', '?')}%."
                if objectifs else "Aucun objectif actif."
            )
            if humeur == HUMEUR_COOL:
                if taux_ep >= 40:
                    return (
                        f"Solide — {taux_ep:.1f}% epargne, score {score_val:.0f}/100. "
                        f"Capital disponible : affecte-le a un objectif concret. {obj_str}"
                    )
                return (
                    f"Trajectoire conforme. Epargne {taux_ep:.1f}% — dans les clous. "
                    f"{obj_str}"
                )
            if humeur == HUMEUR_NEUTRE:
                return (
                    f"Ecart epargne : {manque_ep:.0f} DH vs cible. "
                    f"Reduire les Desirs de {max(0, wants_pct - savings_cible):.0f}% "
                    f"permettrait de rattraper. {obj_str}"
                )
            # SERIEUX
            return (
                f"Trajectoire compromise. A ce rythme l'objectif sera retarde. "
                f"Action requise sur les Desirs ({wants_pct:.0f}%). {obj_str}"
            )

        # ══════════════════════════════════════════════════════════════════════
        # LIBERE — direct, nomme le gaspillage
        # ══════════════════════════════════════════════════════════════════════
        if humeur == HUMEUR_COOL:
            if taux_ep >= 40:
                return (
                    f"Solide ! {taux_ep:.1f}% epargne, score {score_val:.0f}/100. "
                    f"L'argent dort — fais-le travailler."
                )
            return (
                f"Propre ! {taux_ep:.1f}% epargne, score {score_val:.0f}/100. "
                f"Tu geres bien, continue."
            )
        if humeur == HUMEUR_NEUTRE:
            if scat_alerte:
                return (
                    f"'{scat_alerte}' gonfle inutilement. "
                    f"Tu peux recuperer facilement {manque_ep:.0f} DH ici."
                )
            return (
                f"Regarde tes abonnements et depenses recurrentes — "
                f"il y a probablement {manque_ep:.0f} DH a recuperer sans effort."
            )
        # SERIEUX
        if scat_alerte:
            return (
                f"Stop — '{scat_alerte}' explose le budget. "
                f"C'est la que part l'argent. A corriger maintenant."
            )
        return (
            f"Les chiffres ne mentent pas : score {score_val:.0f}/100, "
            f"epargne {taux_ep:.1f}%. Il faut agir sur les Desirs maintenant."
        )

    # =========================================================================
    # ROLE 7 — QUERY ENGINE
    # =========================================================================

    # Table de routage : nom public → méthode MoteurAnalyse
    _QUERY_MAP: Dict[str, str] = {
        "bilan_mensuel":          "get_bilan_mensuel",
        "repartition":            "get_repartition_par_categorie",
        "detail_sous_categories": "get_detail_par_sous_categorie",
        "evolution_mensuelle":    "get_evolution_mensuelle",
        "tendances_jours":        "get_tendances_jour_semaine",
        "budget_vs_reel":         "get_budget_vs_reel",
        "projection":             "get_projection_fin_mois",
        "charges_fixes":          "get_charges_fixes",
        "radar_factures":         "get_radar_factures",
        "anomalies":              "detecter_anomalies",
        "score_sante":            "get_score_sante_financiere",
        "alertes":                "get_alertes_seuil",
        "doublons":               "detecter_doublons",
        "plan_5030_20":           "get_analyse_5030_20",
        "impact_projet":          "simuler_impact_projet",
        "objectif_epargne":       "simuler_objectif_epargne",
        "crash_test":             "simuler_crash_test",
        "croisement":             "get_croisement_categorie_periode",
        "transactions_plage":     "get_transactions_par_plage",
        # Mode Inspecteur
        "grosses_depenses":       "get_grosses_depenses",
        # Mode Coach
        "comparaison_habitudes":  "get_comparaison_vs_habitudes",
    }

    def query(self, demande: str, **kwargs) -> Dict[str, Any]:
        """
        Routeur de requêtes analytiques complexes vers MoteurAnalyse.

        Paramètres :
          demande   — Identifiant de la requête (voir liste ci-dessous).
          **kwargs  — Arguments passés à la méthode correspondante.

        Requêtes disponibles :
          'bilan_mensuel'          mois='MM/YYYY'
          'repartition'            mois='MM/YYYY'
          'detail_sous_categories' categorie='...', mois='MM/YYYY'
          'evolution_mensuelle'    (aucun argument)
          'tendances_jours'        mois='MM/YYYY'
          'budget_vs_reel'         mois='MM/YYYY'
          'projection'             mois='MM/YYYY'
          'charges_fixes'          nb_mois_min=2
          'anomalies'              mois='MM/YYYY', seuil_sigma=2.0
          'score_sante'            mois='MM/YYYY'
          'alertes'                seuil_pct=80.0, mois='MM/YYYY'
          'doublons'               fenetre_jours=1
          'plan_5030_20'           mois='MM/YYYY'
          'impact_projet'          montant_projet=15000, mois_cibles=12
          'objectif_epargne'       cible_dh=50000, nb_mois=24
          'crash_test'             nb_mois_sans_revenu=3
          'croisement'             groupby='mois'|'jour_semaine'|'heure', mois='MM/YYYY'
          'transactions_plage'     date_debut=date(...), date_fin=date(...), sens='OUT'

        Retourne :
          { demande, resultat, timestamp }  — succès
          { erreur, connus }               — demande inconnue
          { erreur }                       — paramètres invalides ou erreur SQL
        """
        if demande not in self._QUERY_MAP:
            self._log("QUERY", "REQUETE_INCONNUE",
                      {"demande": demande}, statut="ERREUR")
            return {
                "erreur":  f"Requete '{demande}' inconnue.",
                "connus":  sorted(self._QUERY_MAP.keys()),
            }

        # ── Appel MoteurAnalyse ───────────────────────────────────────────────
        methode = getattr(self.moteur, self._QUERY_MAP[demande])
        try:
            resultat_brut = methode(**kwargs)
        except TypeError as e:
            self._log("QUERY", "PARAMETRES_INVALIDES",
                      {"demande": demande, "kwargs": kwargs},
                      {"erreur": str(e)}, statut="ERREUR")
            return {"erreur": f"Parametres invalides pour '{demande}' : {e}"}
        except Exception as e:
            self._log("QUERY", "ERREUR_REQUETE",
                      {"demande": demande},
                      {"erreur": str(e)}, statut="ERREUR")
            return {"erreur": f"Erreur execution '{demande}' : {e}"}

        # ── Sérialisation ─────────────────────────────────────────────────────
        if isinstance(resultat_brut, pd.DataFrame):
            resultat_serial = resultat_brut.to_dict("records")
        elif hasattr(resultat_brut, "__dataclass_fields__"):
            resultat_serial = {
                k: getattr(resultat_brut, k)
                for k in resultat_brut.__dataclass_fields__
            }
        else:
            resultat_serial = resultat_brut

        output = {
            "demande":   demande,
            "resultat":  resultat_serial,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # ── Log (debug only — pas d'INSERT AUDIT_LOG en hot path) ────────────
        if logger.isEnabledFor(logging.DEBUG):
            nb_res = len(resultat_serial) if isinstance(resultat_serial, list) else 1
            logger.debug("QUERY %s nb_resultats=%d", demande, nb_res)

        return output

    def requetes_disponibles(self) -> List[str]:
        """Retourne la liste de toutes les requêtes disponibles dans le Query Engine."""
        return sorted(self._QUERY_MAP.keys())


