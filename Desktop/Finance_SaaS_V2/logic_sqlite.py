"""
LOGIC_SQLITE.PY — MOTEUR MÉTIER COMPLET (SQLite)
=================================================
Contient :
  - BLOC 0 : Dataclasses (Transaction, Enveloppe, BilanMensuel, etc.)
  - BLOC 1 : Douane (normalisation texte, montant, date)
  - BLOC 2 : ClassificationEngine (DICO + Trieur fuzzy 5 niveaux)
  - BLOC 3 : Méthodes de lecture / stats pour audit.py et app.py
"""

import re
import math
import sqlite3
import logging
import unicodedata
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field

import pandas as pd
from rapidfuzz import fuzz, process as fuzz_process

from db_manager import DatabaseManager, STATUT_A_CLASSIFIER, STATUT_VALIDE
from config import (
    DB_PATH,
    MOT_CLE_MIN_LEN,
    MOT_CLE_MAX_LEN,
    NB_MOIS_REF_DEFAUT,
    TOP_N_DEPENSES,
    NB_MOIS_EVOLUTION,
    SCORE_POIDS_EPARGNE,
    SCORE_POIDS_BUDGET,
    SCORE_POIDS_DIVERS,
    SCORE_NIVEAU_EXCELLENT,
    SCORE_NIVEAU_BON,
    SCORE_NIVEAU_MOYEN,
)

logger = logging.getLogger("LOGIC_ENGINE")


# ─────────────────────────────────────────────────────────────────────────────
# BLOC 0 : DATACLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Transaction:
    date: datetime
    mot_cle: str
    montant: float
    sens: str = "OUT"
    categorie: str = ""
    sous_categorie: str = ""
    id_unique: str = ""
    source: str = "SAISIE"

    def __post_init__(self):
        try:
            self.montant = abs(float(self.montant))
            if self.sens.upper() == "OUT":
                self.montant = -self.montant
        except (ValueError, TypeError):
            self.montant = 0.0
            logger.warning(f"Montant invalide pour '{self.mot_cle}'")

@dataclass
class DepenseFixe:
    nom_fixe: str
    montant: float
    jour: int
    categorie: str
    sous_categorie: str
    plafond_mensuel: float = 0.0

@dataclass
class ReferentielItem:
    categorie: str
    sous_categorie: str
    sens: str
    frequence: str
    statut: str
    compteur_n: int = 0
    montant_cumule: float = 0.0

@dataclass
class Enveloppe:
    sous_categorie: str
    budget: float
    depense_reelle: float = 0.0

    @property
    def restant(self) -> float:
        return self.budget + self.depense_reelle

    @property
    def taux_consommation(self) -> float:
        return (abs(self.depense_reelle) / self.budget * 100) if self.budget > 0 else 0.0

@dataclass
class BilanMensuel:
    mois: str
    revenus: float = 0.0
    depenses: float = 0.0
    epargne_reelle: float = 0.0
    evolution_dh: float = 0.0
    score_sante: str = "PENDING"
    enveloppes: List[Enveloppe] = field(default_factory=list)

@dataclass
class CandidatClassification:
    rang: int
    mot_cle_dico: str
    categorie: str
    sous_categorie: str
    sens: str
    score: float

    def __str__(self) -> str:
        return (f"[{self.rang}] {self.categorie} / {self.sous_categorie} "
                f"<- '{self.mot_cle_dico}' (score {self.score:.0f}%)")

@dataclass
class ResultatClassification:
    categorie: str
    sous_categorie: str
    methode: str
    score: float = 100.0
    sens: str = "OUT"
    statut: str = "AUTO"
    candidats: List[CandidatClassification] = field(default_factory=list)
    mot_cle_original: str = ""

    def est_valide(self) -> bool:
        return self.methode != "INCONNU"

@dataclass
class EcritureComptable:
    id_unique: str
    date_saisie: str
    date_valeur: date
    mot_cle: str
    montant: float
    categorie: str
    sous_categorie: str


# ─────────────────────────────────────────────────────────────────────────────
# BLOC 1 : DOUANE — NORMALISATION
# ─────────────────────────────────────────────────────────────────────────────

class Douane:
    """Normalisation des données brutes : texte, montant, date, DataFrame."""

    @staticmethod
    def supprimer_accents(texte: str) -> str:
        nfkd = unicodedata.normalize("NFKD", str(texte))
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    @classmethod
    def normaliser_texte(cls, texte: str) -> str:
        if pd.isna(texte) or not str(texte).strip():
            return ""
        t = str(texte).strip().upper()
        t = cls.supprimer_accents(t)
        t = re.sub(r"[^\w\s\-\'\.\/]", " ", t)
        t = re.sub(r"\s+", " ", t)
        return t.strip()

    @staticmethod
    def normaliser_montant(valeur: Any) -> Optional[float]:
        if pd.isna(valeur) or str(valeur).strip() == "":
            return None
        s = str(valeur).strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
        if s.count(".") > 1:
            parts = s.rsplit(".", 1)
            s = parts[0].replace(".", "") + "." + parts[1]
        try:
            return round(float(s), 2)
        except ValueError:
            return None

    @staticmethod
    def normaliser_date(valeur: Any) -> Optional[date]:
        if pd.isna(valeur) or str(valeur).strip() == "":
            return None
        s = str(valeur).strip()
        formats = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d.%m.%Y", "%Y/%m/%d"]
        for fmt in formats:
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    @classmethod
    def nettoyer_dataframe(cls, df: pd.DataFrame, mapping_colonnes: Dict[str, str]) -> pd.DataFrame:
        df = df.copy()
        for col, type_col in mapping_colonnes.items():
            if col not in df.columns:
                continue
            if type_col == "texte":
                df[col] = df[col].apply(cls.normaliser_texte)
            elif type_col == "montant":
                df[col] = df[col].apply(cls.normaliser_montant)
                df[col] = pd.to_numeric(df[col], errors="coerce")
            elif type_col == "date":
                df[col] = df[col].apply(cls.normaliser_date)
            elif type_col == "sens":
                def parse_sens(v):
                    t = cls.normaliser_texte(str(v))
                    if t in ("IN", "ENTREE", "REVENU", "+"):
                        return "IN"
                    if t in ("OUT", "SORTIE", "DEPENSE", "-"):
                        return "OUT"
                    return ""
                df[col] = df[col].apply(parse_sens)
        df.dropna(how="all", inplace=True)
        return df


# ─────────────────────────────────────────────────────────────────────────────
# BLOC 2 : TRIEUR — MOTEUR FUZZY 5 NIVEAUX
# ─────────────────────────────────────────────────────────────────────────────

SEUIL_AUTO           = 85
SEUIL_FUZZY_MIN      = 50
SEUIL_FUSION_INCONNU = 90
MIN_LETTRES_PARTIEL  = 5
NB_CANDIDATS_FUZZY   = 3
BLACKLIST_PARTIEL    = {
    "MARKET", "SHOP", "STORE", "ACHAT", "PAIEMENT",
    "PAYMENT", "ONLINE", "WEB", "APP", "SERVICE"
}

FALLBACK_IN  = ("Revenu", "Autre")
FALLBACK_OUT = ("Divers", "Divers_Autre")


class Trieur:
    """
    Moteur de classification en 5 niveaux, alimenté par DICO_MATCHING en base.

    Niveaux (du plus précis au moins précis) :
      1. EXACT        — match exact dans DICO (case-insensitive)
      2. EXACT_COURT  — acronyme < 4 chars, mot entier dans la transaction
      3. NEAR_AUTO    — fuzzy score >= SEUIL_AUTO (85%)
      4. PARTIEL      — token contenu dans une clé du dico
      5. FUZZY        — score >= SEUIL_FUZZY_MIN (50%) → propose candidats
      Repli           — IN=Revenu/Autre, OUT=Divers/Divers_Autre + A_CLASSIFIER
    """

    def __init__(self, db: DatabaseManager, seuil_auto: int = SEUIL_AUTO, seuil_fuzzy_min: int = SEUIL_FUZZY_MIN):
        self.db = db
        self.seuil_auto = seuil_auto
        self.seuil_fuzzy_min = seuil_fuzzy_min
        self._dico: Dict[Tuple[str, str], Tuple[str, str]] = {}
        self._dico_exact: Dict[Tuple[str, str], Tuple[str, str]] = {}
        self._charger_dico()

    def _charger_dico(self):
        """Charge DICO_MATCHING depuis SQLite en mémoire pour le fuzzy."""
        with self.db.connexion() as conn:
            rows = conn.execute(
                "SELECT Sens, Mot_Cle, Categorie_Cible, Sous_Categorie_Cible FROM DICO_MATCHING"
            ).fetchall()

        for row in rows:
            sens = str(row[0]).strip().upper()
            mot_norm = Douane.normaliser_texte(str(row[1]))
            cat  = str(row[2]).strip()
            scat = str(row[3]).strip()
            if not mot_norm or not cat:
                continue
            if len(mot_norm) >= 4:
                self._dico[(mot_norm, sens)] = (cat, scat)
            else:
                self._dico_exact[(mot_norm, sens)] = (cat, scat)

        logger.info(f"Trieur charge : {len(self._dico)} mots fuzzy + {len(self._dico_exact)} acronymes")

    def classifier(self, mot_cle: str, sens_transaction: str = "OUT") -> ResultatClassification:
        mot_norm = Douane.normaliser_texte(mot_cle)
        sens_transaction = sens_transaction.strip().upper()

        if not mot_norm:
            return self._repli_inconnu(mot_cle, sens_transaction)

        # Filtrer le dico sur le bon sens uniquement
        dico_autorise = {
            m: (cat, scat)
            for (m, s), (cat, scat) in self._dico.items()
            if s == sens_transaction
        }
        mots_cibles = list(dico_autorise.keys())

        # ── Niveau 1 : EXACT (mots >= 4 chars uniquement) ────────────────────
        if len(mot_norm) >= 4 and mot_norm in dico_autorise:
            cat, scat = dico_autorise[mot_norm]
            return ResultatClassification(cat, scat, "EXACT", 100.0, sens_transaction, "AUTO", [], mot_cle)

        # ── Niveau 2 : EXACT_COURT (acronymes < 4 chars) ─────────────────────
        # Vérification frontière de mot avec regex pour éviter RMA dans phaRMAcie
        for (acronyme, s), (cat, scat) in self._dico_exact.items():
            if s == sens_transaction and re.search(r'\b' + re.escape(acronyme) + r'\b', mot_norm):
                return ResultatClassification(cat, scat, "EXACT_COURT", 100.0, sens_transaction, "AUTO", [], mot_cle)

        # ── Niveau 3 : NEAR_AUTO (fuzzy >= seuil_auto) ───────────────────────
        if mots_cibles:
            res = fuzz_process.extract(mot_norm, mots_cibles, scorer=fuzz.WRatio, limit=1)
            if res and res[0][1] >= self.seuil_auto:
                cle, score, _ = res[0]
                cat, scat = dico_autorise[cle]
                return ResultatClassification(cat, scat, "NEAR_AUTO", score, sens_transaction, "AUTO", [], mot_cle)

        # ── Niveau 4 : PARTIEL (token contenu dans clé dico) ─────────────────
        res_partiel = self._matching_partiel(mot_norm, mot_cle, dico_autorise, sens_transaction)
        if res_partiel:
            return res_partiel

        # ── Niveau 5 : FUZZY (score >= seuil_fuzzy_min) ──────────────────────
        if mots_cibles:
            candidats = []
            res_fuzzy = fuzz_process.extract(mot_norm, mots_cibles, scorer=fuzz.WRatio, limit=NB_CANDIDATS_FUZZY)
            for rang, (cle, score, _) in enumerate(res_fuzzy, start=1):
                if score >= self.seuil_fuzzy_min:
                    cat, scat = dico_autorise[cle]
                    candidats.append(CandidatClassification(rang, cle, cat, scat, sens_transaction, float(score)))
            if candidats:
                if sens_transaction == "IN":
                    return ResultatClassification(*FALLBACK_IN, "AUTO_IN", 100.0, "IN", "AUTO", [], mot_cle)
                else:
                    self._enregistrer_inconnu(mot_cle, sens_transaction)
                    return ResultatClassification(*FALLBACK_OUT, "FUZZY", candidats[0].score, "OUT", "AUTO", candidats, mot_cle)

        # ── Repli total ───────────────────────────────────────────────────────
        return self._repli_inconnu(mot_cle, sens_transaction)

    def apprendre(self, mot_cle: str, categorie: str, sous_categorie: str, sens: str = "OUT"):
        """Ajoute un mot-clé confirmé en mémoire ET dans DICO_MATCHING."""
        mot_norm = Douane.normaliser_texte(mot_cle)
        if not mot_norm:
            return
        self._dico[(mot_norm, sens.upper())] = (categorie, sous_categorie)
        with self.db.connexion() as conn:
            conn.execute(
                """
                INSERT INTO DICO_MATCHING (Sens, Mot_Cle, Categorie_Cible, Sous_Categorie_Cible)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (Sens, Mot_Cle) DO NOTHING
                """,
                (sens.upper(), mot_cle.strip(), categorie.strip(), sous_categorie.strip())
            )
        logger.info(f"Appris : '{mot_cle}' -> {categorie}/{sous_categorie}")

    def _matching_partiel(self, mot_norm: str, mot_cle_original: str, dico_autorise: dict, sens: str) -> Optional[ResultatClassification]:
        tokens = set(mot_norm.split()) | {mot_norm}
        meilleur_cle = None
        meilleur_len = 0
        for token in tokens:
            if len(token) < MIN_LETTRES_PARTIEL or token in BLACKLIST_PARTIEL:
                continue
            for cle_dico in dico_autorise:
                if len(cle_dico) < MIN_LETTRES_PARTIEL or cle_dico in BLACKLIST_PARTIEL:
                    continue
                # Vérification frontière de mot — évite RMA dans phaRMAcie
                # On accepte uniquement si token et cle_dico partagent un mot entier
                token_in_cle = bool(re.search(r'\b' + re.escape(token) + r'\b', cle_dico))
                cle_in_token = bool(re.search(r'\b' + re.escape(cle_dico) + r'\b', token))
                if (token_in_cle or cle_in_token) and len(cle_dico) > meilleur_len:
                    meilleur_len = len(cle_dico)
                    meilleur_cle = cle_dico
        if meilleur_cle:
            cat, scat = dico_autorise[meilleur_cle]
            return ResultatClassification(cat, scat, "PARTIEL", 90.0, sens, "AUTO", [], mot_cle_original)
        return None

    def _repli_inconnu(self, mot_cle: str, sens: str) -> ResultatClassification:
        if sens == "IN":
            return ResultatClassification(*FALLBACK_IN, "AUTO_IN", 100.0, "IN", "AUTO", [], mot_cle)
        self._enregistrer_inconnu(mot_cle, sens)
        return ResultatClassification(*FALLBACK_OUT, "INCONNU", 0.0, sens, "INCONNU", [], mot_cle)

    def _enregistrer_inconnu(self, mot_cle: str, sens: str):
        """Double écriture dans A_CLASSIFIER."""
        cat, scat = FALLBACK_IN if sens == "IN" else FALLBACK_OUT
        self.db.enregistrer_mot_cle_inconnu(mot_cle, sens, cat, scat)


# ─────────────────────────────────────────────────────────────────────────────
# BLOC 3 : COMPTABLE BUDGET — ÉCRITURES SQLITE
# ─────────────────────────────────────────────────────────────────────────────

FENETRE_DOUBLON_SECONDES = 120  # Anti-double clic : 2 minutes

_CAT_EPARGNE_NORM  = "FINANCES CREDITS"
_SCAT_EPARGNE_NORM = "EPARGNE INVESTISSEMENT"


class ComptableBudget:
    """
    Reçoit (date_valeur, mot_cle, montant, classification) et exécute :
      · Vérification doublon (fenêtre 2 min)
      · Génération ID unique  AAAAMMJJ_HHMMSS_XX
      · Écriture TRANSACTIONS (avec user_id)
      · Mise à jour EPARGNE_HISTO si catégorie épargne

    NOTE : Le REFERENTIEL n'est JAMAIS modifié automatiquement.
    """

    def __init__(self, db: DatabaseManager, user_id: int):
        self.db      = db
        self.user_id = user_id
        self._compteur_seconde: Dict[str, int] = {}
        self._cat_epargne, self._scat_epargne = self._charger_ids_epargne()

    # ── 1. ID UNIQUE ──────────────────────────────────────────────────────────

    def _generer_id(self, dt: Optional[datetime] = None) -> str:
        if dt is None:
            dt = datetime.now()
        base  = dt.strftime("%Y%m%d_%H%M%S")
        count = self._compteur_seconde.get(base, 0) + 1
        self._compteur_seconde = {base: count}
        return f"{base}_{count:02d}"

    # ── 2. DÉTECTION DOUBLON ──────────────────────────────────────────────────

    def _est_doublon(self, date_valeur: date, mot_cle: str, montant_abs: float) -> bool:
        fenetre   = datetime.now() - timedelta(seconds=FENETRE_DOUBLON_SECONDES)
        mot_norm  = Douane.normaliser_texte(mot_cle)
        with self.db.connexion() as conn:
            rows = conn.execute(
                """
                SELECT Date_Saisie, Date_Valeur, Libelle, Montant
                FROM TRANSACTIONS
                WHERE Date_Saisie >= ? AND user_id = ?
                """,
                (fenetre.strftime("%Y-%m-%d %H:%M:%S"), self.user_id)
            ).fetchall()

        for row in rows:
            dv_row  = Douane.normaliser_date(str(row[1]))
            mot_row = Douane.normaliser_texte(str(row[2]))
            mnt_row = Douane.normaliser_montant(row[3])
            if (dv_row == date_valeur
                    and mot_row == mot_norm
                    and mnt_row is not None
                    and abs(abs(mnt_row) - montant_abs) < 0.01):
                return True
        return False

    # ── 3. MISE À JOUR RÉFÉRENTIEL ────────────────────────────────────────────

    def _maj_referentiel(self, sous_categorie: str, montant_abs: float):
        """
        Met à jour UNIQUEMENT Compteur_N et Montant_Cumule sur une ligne existante.
        JAMAIS d'INSERT, JAMAIS de modification de Categorie/Sous_Categorie/Sens/Frequence.
        Si la sous-catégorie est absente du REFERENTIEL → log warning, rien de plus.
        """
        with self.db.connexion() as conn:
            row = conn.execute(
                "SELECT Compteur_N, Montant_Cumule FROM REFERENTIEL WHERE Sous_Categorie = ?",
                (sous_categorie,)
            ).fetchone()

            if row:
                conn.execute(
                    """
                    UPDATE REFERENTIEL
                    SET Compteur_N = ?, Montant_Cumule = ?
                    WHERE Sous_Categorie = ?
                    """,
                    (row[0] + 1, round(row[1] + montant_abs, 2), sous_categorie)
                )
                logger.info(f"REFERENTIEL — '{sous_categorie}' : Compteur={row[0]+1} | Cumul={round(row[1]+montant_abs,2)}")
            else:
                logger.warning(f"REFERENTIEL — '{sous_categorie}' absente, aucune modification effectuee")

    # ── 4. MISE À JOUR ÉPARGNE_HISTO ─────────────────────────────────────────

    def _maj_epargne_histo(self, date_valeur: date, montant_abs: float):
        mois_str = date_valeur.strftime("%m/%Y")
        with self.db.connexion() as conn:
            row = conn.execute(
                "SELECT Montant_Vise, Montant_Reel, Cumul_Total FROM EPARGNE_HISTO WHERE Mois = ? AND user_id = ?",
                (mois_str, self.user_id)
            ).fetchone()

            if row:
                vise         = float(row[0] or 0)
                nouveau_reel  = round(float(row[1] or 0) + montant_abs, 2)
                evolution     = round(nouveau_reel - vise, 2)
                nouveau_cumul = round(float(row[2] or 0) + montant_abs, 2)
                conn.execute(
                    """
                    UPDATE EPARGNE_HISTO
                    SET Montant_Reel = ?, Evolution_DH = ?, Cumul_Total = ?
                    WHERE Mois = ? AND user_id = ?
                    """,
                    (nouveau_reel, evolution, nouveau_cumul, mois_str, self.user_id)
                )
            else:
                conn.execute(
                    """
                    INSERT INTO EPARGNE_HISTO
                    (Mois, Montant_Vise, Montant_Reel, Evolution_DH, Cumul_Total, user_id)
                    VALUES (?, 0.0, ?, ?, ?, ?)
                    """,
                    (mois_str, round(montant_abs,2), round(montant_abs,2),
                     round(montant_abs,2), self.user_id)
                )
                logger.info(f"EPARGNE_HISTO — nouvelle ligne creee pour {mois_str}")

    # ── 5. CHARGEMENT IDS ÉPARGNE ─────────────────────────────────────────────

    def _charger_ids_epargne(self) -> Tuple[str, str]:
        with self.db.connexion() as conn:
            rows = conn.execute(
                "SELECT Categorie, Sous_Categorie FROM REFERENTIEL"
            ).fetchall()
        for row in rows:
            scat = Douane.normaliser_texte(str(row[1]))
            if "EPARGNE" in scat and "INVESTISSEMENT" in scat:
                return Douane.normaliser_texte(str(row[0])), scat
        return _CAT_EPARGNE_NORM, _SCAT_EPARGNE_NORM

    # ── 6. POINT D'ENTRÉE PRINCIPAL ───────────────────────────────────────────

    def enregistrer_transaction(
        self,
        date_valeur:    date,
        mot_cle:        str,
        montant:        float,
        classification: ResultatClassification,
        source:         str = "SAISIE",
    ) -> Dict[str, Any]:
        """
        Enregistre une transaction complète.
        Retourne {id_unique, montant} ou {id_unique: None, doublon: True, message}.
        """
        now          = datetime.now()
        date_saisie  = now.strftime("%Y-%m-%d %H:%M:%S")
        dv           = date_valeur or date.today()
        montant_abs  = abs(montant)
        montant_signe = -montant_abs if classification.sens == "OUT" else montant_abs

        # Vérification doublon
        if self._est_doublon(dv, mot_cle, montant_abs):
            logger.warning(f"Doublon bloque : '{mot_cle}' | {montant_abs:.2f} | {dv}")
            return {
                "id_unique": None,
                "montant":   montant_signe,
                "doublon":   True,
                "message":   f"Doublon detecte : '{mot_cle}' deja enregistre dans les {FENETRE_DOUBLON_SECONDES // 60} dernieres minutes.",
            }

        id_unique = self._generer_id(now)

        # Écriture TRANSACTIONS
        src = source.upper() if source.upper() in ("SAISIE", "IMPORT", "ONBOARDING") else "SAISIE"
        with self.db.connexion() as conn:
            conn.execute(
                """
                INSERT INTO TRANSACTIONS
                (ID_Unique, Date_Saisie, Date_Valeur, Libelle, Montant,
                 Sens, Categorie, Sous_Categorie, Statut, Source, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (ID_Unique, user_id) DO NOTHING
                """,
                (
                    id_unique,
                    date_saisie,
                    dv.strftime("%Y-%m-%d"),
                    mot_cle.strip(),
                    montant_signe,
                    classification.sens,
                    classification.categorie,
                    classification.sous_categorie,
                    STATUT_VALIDE,
                    src,
                    self.user_id,
                )
            )

        # Mise à jour REFERENTIEL (Compteur_N + Montant_Cumule uniquement)
        self._maj_referentiel(classification.sous_categorie, montant_abs)

        # Mise à jour EPARGNE_HISTO si catégorie épargne
        cat_norm  = Douane.normaliser_texte(classification.categorie)
        scat_norm = Douane.normaliser_texte(classification.sous_categorie)
        if cat_norm == self._cat_epargne and scat_norm == self._scat_epargne:
            self._maj_epargne_histo(dv, montant_abs)

        logger.info(f"[{id_unique}] '{mot_cle}' -> {classification.categorie}/{classification.sous_categorie} | {montant_signe:+.2f}")

        return {"id_unique": id_unique, "montant": montant_signe}

    # ── 7. FLUX RÉCENT ────────────────────────────────────────────────────────

    def get_flux_recent(self, n: int = 10) -> List[Dict[str, Any]]:
        """Retourne les n dernières transactions, plus récentes en premier."""
        with self.db.connexion() as conn:
            rows = conn.execute(
                """
                SELECT Date_Saisie, Libelle, Montant, Categorie, Sous_Categorie, ID_Unique
                FROM TRANSACTIONS
                WHERE user_id = ?
                ORDER BY Date_Saisie DESC
                LIMIT ?
                """,
                (self.user_id, n)
            ).fetchall()

        return [
            {
                "heure_saisie":   row[0],
                "mot_cle":        row[1],
                "montant":        row[2],
                "categorie":      row[3],
                "sous_categorie": row[4],
                "id_unique":      row[5],
            }
            for row in rows
        ]


# ─────────────────────────────────────────────────────────────────────────────
# CLASSE MOTEUR DE CLASSIFICATION SQLITE
# ─────────────────────────────────────────────────────────────────────────────

class ClassificationEngine:
    """
    Moteur de classification des transactions via règles utilisateur.
    
    L'utilisateur ne peut PAS créer de nouvelles catégories — il ne fait
    que créer des règles pour classer les transactions A_CLASSIFIER vers VALIDE.
    
    Usage :
        engine = ClassificationEngine(DB_PATH)
        
        # Créer une règle et classer en masse
        nb_classees = engine.apply_classification_rule(
            sens="OUT",
            mot_cle="CARREFOUR",
            montant=None,  # ou 50.0 pour un montant exact
            categorie_cible="Alimentation"
        )
        print(f"{nb_classees} transactions classées !")
        
        # Lire les transactions non classées
        df_pending = engine.get_unclassified_transactions()
        
        # Lister les catégories disponibles
        categories = engine.get_available_categories()
    """

    def __init__(self, db_path: str = DB_PATH):
        """
        Paramètres :
          db_path — Chemin vers la base SQLite (doit exister et être initialisée).
        """
        self.db = DatabaseManager(db_path)
        logger.info(f"🔧 ClassificationEngine initialisé — {db_path}")

    # ─────────────────────────────────────────────────────────────────────────
    # CLASSIFICATION AUTOMATIQUE PAR DICO_MATCHING
    # ─────────────────────────────────────────────────────────────────────────

    # Catégories par défaut pour les mots-clés inconnus
    FALLBACK_IN  = ("Revenu",  "Autre")
    FALLBACK_OUT = ("Divers",  "Divers_Autre")

    def classifier_transaction(self, mot_cle: str, sens: str) -> Dict[str, str]:
        """
        Classifie un mot-clé en cherchant dans DICO_MATCHING.

        Règles :
          1. Recherche exacte dans DICO_MATCHING (Mot_Cle + Sens)
          2. Si trouvé → retourne Categorie + Sous_Categorie
          3. Si inconnu :
             - IN  → Revenu / Autre
             - OUT → Divers / Divers_Autre
             + Double écriture dans A_CLASSIFIER pour enrichissement futur

        Retourne un dict : {categorie, sous_categorie, source}
          source = 'DICO' | 'FALLBACK'
        """
        sens = sens.strip().upper()
        mot_cle = mot_cle.strip()

        with self.db.connexion() as conn:
            row = conn.execute(
                """
                SELECT Categorie_Cible, Sous_Categorie_Cible
                FROM DICO_MATCHING
                WHERE UPPER(Mot_Cle) = UPPER(?) AND Sens = ?
                LIMIT 1
                """,
                (mot_cle, sens)
            ).fetchone()

        if row:
            logger.info(f"✅ DICO — '{mot_cle}' → {row[0]} / {row[1]}")
            return {
                "categorie":      row[0],
                "sous_categorie": row[1],
                "source":         "DICO",
            }

        # Mot-clé inconnu → fallback + double écriture
        cat, sous_cat = self.FALLBACK_IN if sens == "IN" else self.FALLBACK_OUT
        logger.warning(f"⚠️ Inconnu — '{mot_cle}' ({sens}) → {cat} / {sous_cat} [FALLBACK]")

        self.db.enregistrer_mot_cle_inconnu(mot_cle, sens, cat, sous_cat)

        return {
            "categorie":      cat,
            "sous_categorie": sous_cat,
            "source":         "FALLBACK",
        }

    def get_mots_cles_inconnus(self) -> "pd.DataFrame":
        """
        Retourne les mots-clés inconnus non encore enrichis dans DICO_MATCHING.
        Trié par Nb_Occurrences décroissant — les plus fréquents en premier.
        Utile pour que l'utilisateur priorise l'enrichissement.
        """
        with self.db.connexion() as conn:
            df = pd.read_sql_query(
                """
                SELECT id, Mot_Cle_Inconnu, Sens, Categorie_Auto,
                       Sous_Categorie_Auto, Nb_Occurrences, Date_Ajout
                FROM A_CLASSIFIER
                WHERE Enrichi = 0
                ORDER BY Nb_Occurrences DESC
                """,
                conn
            )
        logger.info(f"📋 {len(df)} mot(s)-clé(s) inconnu(s) en attente d'enrichissement")
        return df

    # ─────────────────────────────────────────────────────────────────────────
    # MISSION 2 : MOTEUR DE CLASSIFICATION (TRANSACTION ATOMIQUE)
    # ─────────────────────────────────────────────────────────────────────────

    def apply_classification_rule(
        self,
        sens: str,
        mot_cle: str,
        montant: Optional[float],
        categorie_cible: str,
    ) -> int:
        """
        Enregistre une règle de classification ET met à jour en masse
        toutes les transactions correspondantes — en une seule transaction SQL.
        
        Paramètres :
          sens            — 'IN' ou 'OUT' (flux de la transaction)
          mot_cle         — Mot-clé à matcher dans le libellé (recherche LIKE %mot_cle%)
          montant         — Montant exact à matcher (None pour ignorer ce critère)
          categorie_cible — Catégorie vers laquelle classer les transactions
        
        Retourne :
          Le nombre de transactions mises à jour (cursor.rowcount).
          Permet d'afficher "X transactions classées !" dans Streamlit.
        
        Raises :
          ValueError — Si la catégorie cible n'existe pas dans CATEGORIES.
          sqlite3.Error — En cas d'erreur SQL (rollback automatique).
        
        Exemple :
            # Règle sans montant : classe tous les "NETFLIX" en sortie
            nb = engine.apply_classification_rule("OUT", "NETFLIX", None, "Loisirs")
            
            # Règle avec montant : classe les virements de 3500€ en entrée
            nb = engine.apply_classification_rule("IN", "VIREMENT", 3500.0, "Revenu")
        """
        # ── Validation des inputs ─────────────────────────────────────────────
        sens = sens.strip().upper()
        if sens not in ("IN", "OUT"):
            raise ValueError(f"sens doit être 'IN' ou 'OUT', reçu : '{sens}'")
        
        mot_cle = mot_cle.strip()
        if not mot_cle:
            raise ValueError("mot_cle ne peut pas être vide")
        
        categorie_cible = categorie_cible.strip()
        if not categorie_cible:
            raise ValueError("categorie_cible ne peut pas être vide")

        # Normalisation du montant (None si vide ou 0)
        if montant is not None:
            try:
                montant = round(float(montant), 2)
                if montant == 0:
                    montant = None
            except (ValueError, TypeError):
                montant = None

        nb_transactions_classees = 0

        with self.db.connexion() as conn:
            # ── Vérification : la catégorie cible existe-t-elle ? ─────────────
            existe = conn.execute(
                "SELECT 1 FROM CATEGORIES WHERE Categorie = ? LIMIT 1",
                (categorie_cible,)
            ).fetchone()
            
            if not existe:
                raise ValueError(
                    f"❌ Catégorie '{categorie_cible}' introuvable dans CATEGORIES. "
                    f"L'utilisateur ne peut pas créer de nouvelles catégories."
                )

            # ══════════════════════════════════════════════════════════════════
            # ÉTAPE A : ENREGISTREMENT DE LA RÈGLE
            # ══════════════════════════════════════════════════════════════════
            conn.execute(
                """
                INSERT INTO REGLES_UTILISATEUR (Sens, Mot_Cle, Montant, Categorie_Cible)
                VALUES (?, ?, ?, ?)
                """,
                (sens, mot_cle, montant, categorie_cible)
            )
            logger.info(
                f"📝 Règle enregistrée : {sens} | '{mot_cle}' | "
                f"{'ANY' if montant is None else montant} → {categorie_cible}"
            )

            # ══════════════════════════════════════════════════════════════════
            # ÉTAPE B : MISE À JOUR EN MASSE (LA MAGIE ✨)
            # ══════════════════════════════════════════════════════════════════
            # Construction dynamique de la requête selon la présence du montant
            
            # Pattern LIKE pour matching flexible
            pattern_like = f"%{mot_cle}%"
            
            if montant is not None:
                # ── Avec montant : match exact ────────────────────────────────
                cursor = conn.execute(
                    """
                    UPDATE TRANSACTIONS
                    SET Categorie = ?,
                        Statut = ?
                    WHERE Statut = ?
                      AND Sens = ?
                      AND Libelle LIKE ?
                      AND Montant = ?
                    """,
                    (
                        categorie_cible,
                        STATUT_VALIDE,
                        STATUT_A_CLASSIFIER,
                        sens,
                        pattern_like,
                        montant,
                    )
                )
            else:
                # ── Sans montant : ignore le critère montant ──────────────────
                cursor = conn.execute(
                    """
                    UPDATE TRANSACTIONS
                    SET Categorie = ?,
                        Statut = ?
                    WHERE Statut = ?
                      AND Sens = ?
                      AND Libelle LIKE ?
                    """,
                    (
                        categorie_cible,
                        STATUT_VALIDE,
                        STATUT_A_CLASSIFIER,
                        sens,
                        pattern_like,
                    )
                )

            nb_transactions_classees = cursor.rowcount

            logger.info(
                f"✅ {nb_transactions_classees} transaction(s) classée(s) → '{categorie_cible}'"
            )

        # Le commit est fait automatiquement par le context manager
        return nb_transactions_classees

    # ─────────────────────────────────────────────────────────────────────────
    # MISSION 3 : MÉTHODES DE LECTURE POUR STREAMLIT
    # ─────────────────────────────────────────────────────────────────────────

    def get_unclassified_transactions(self) -> pd.DataFrame:
        """
        Retourne un DataFrame des transactions à classifier (statut = A_CLASSIFIER).
        
        Colonnes retournées :
          ID_Unique, Date_Valeur, Libelle, Montant, Sens
        
        Trié par Date_Valeur décroissant (plus récent en premier).
        Retourne un DataFrame vide si aucune transaction en attente.
        """
        with self.db.connexion() as conn:
            df = pd.read_sql_query(
                """
                SELECT 
                    ID_Unique,
                    Date_Valeur,
                    Libelle,
                    Montant,
                    Sens
                FROM TRANSACTIONS
                WHERE Statut = ?
                ORDER BY Date_Valeur DESC
                """,
                conn,
                params=(STATUT_A_CLASSIFIER,)
            )

        nb = len(df)
        if nb > 0:
            logger.info(f"📋 {nb} transaction(s) à classifier")
        else:
            logger.info("✅ Aucune transaction en attente de classification")

        return df

    def get_available_categories(self) -> List[str]:
        """
        Retourne la liste unique des catégories disponibles (depuis CATEGORIES).
        
        Utilisé pour alimenter un selectbox Streamlit.
        Trié alphabétiquement.
        """
        with self.db.connexion() as conn:
            cursor = conn.execute(
                """
                SELECT DISTINCT Categorie
                FROM CATEGORIES
                ORDER BY Categorie ASC
                """
            )
            categories = [row[0] for row in cursor.fetchall()]

        logger.info(f"📂 {len(categories)} catégorie(s) disponible(s)")
        return categories

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTHODES COMPLÉMENTAIRES (BONUS)
    # ─────────────────────────────────────────────────────────────────────────

    def get_classification_rules(self) -> pd.DataFrame:
        """
        Retourne toutes les règles de classification créées par l'utilisateur.
        Utile pour afficher un historique ou permettre la suppression.
        """
        with self.db.connexion() as conn:
            df = pd.read_sql_query(
                """
                SELECT 
                    id,
                    Sens,
                    Mot_Cle,
                    Montant,
                    Categorie_Cible,
                    Date_Creation
                FROM REGLES_UTILISATEUR
                ORDER BY Date_Creation DESC
                """,
                conn
            )
        return df

    def get_classified_transactions(self, limit: int = 100) -> pd.DataFrame:
        """
        Retourne les transactions validées (statut = VALIDE).
        Limité aux `limit` plus récentes par défaut.
        """
        with self.db.connexion() as conn:
            df = pd.read_sql_query(
                """
                SELECT 
                    ID_Unique,
                    Date_Valeur,
                    Libelle,
                    Montant,
                    Sens,
                    Categorie
                FROM TRANSACTIONS
                WHERE Statut = ?
                ORDER BY Date_Valeur DESC
                LIMIT ?
                """,
                conn,
                params=(STATUT_VALIDE, limit)
            )
        return df

    def get_stats_by_category(self) -> pd.DataFrame:
        """
        Retourne les statistiques agrégées par catégorie (transactions validées).
        Colonnes : Categorie, Nb_Transactions, Total_Montant
        """
        with self.db.connexion() as conn:
            df = pd.read_sql_query(
                """
                SELECT 
                    Categorie,
                    COUNT(*) AS Nb_Transactions,
                    SUM(Montant) AS Total_Montant
                FROM TRANSACTIONS
                WHERE Statut = ?
                GROUP BY Categorie
                ORDER BY Total_Montant ASC
                """,
                conn,
                params=(STATUT_VALIDE,)
            )
        return df

    def supprimer_regle(self, rule_id: int) -> bool:
        """
        Supprime une règle de classification par son ID.
        Note : Ne dé-classe PAS les transactions déjà classées par cette règle.
        
        Retourne True si supprimée, False si introuvable.
        """
        with self.db.connexion() as conn:
            cursor = conn.execute(
                "DELETE FROM REGLES_UTILISATEUR WHERE id = ?",
                (rule_id,)
            )
            supprimee = cursor.rowcount > 0
        
        if supprimee:
            logger.info(f"🗑️ Règle #{rule_id} supprimée")
        else:
            logger.warning(f"⚠️ Règle #{rule_id} introuvable")
        
        return supprimee


# ─────────────────────────────────────────────────────────────────────────────
# MOTEUR D'ANALYSE — 6 NIVEAUX D'INTELLIGENCE FINANCIÈRE
# ─────────────────────────────────────────────────────────────────────────────

class MoteurAnalyse:
    """
    Moteur analytique complet — 6 PARTs d'intelligence financière.

    PART I   — Comptable   : Équilibres globaux (revenus, dépenses, solde)
    PART II  — Analyste    : Hiérarchie et poids par catégorie / sous-catégorie
    PART III — Stratège    : Chronologie et tendances temporelles (mine d'or : ID Unique)
    PART IV  — Visionnaire : Budget vs Réel + projection fin de mois
    PART V   — Coach       : Anomalies, score santé, alertes de seuil
    PART VI  — Simulateur  : Scénarios "Et si ?" — projets, épargne, crash test
    """

    def __init__(self, db: DatabaseManager, user_id: int):
        self.db      = db
        self.user_id = user_id

    # ─────────────────────────────────────────────────────────────────────────
    # UTILS INTERNES
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _mois_to_date_range(mois: str) -> Tuple[str, str]:
        """Convertit 'MM/YYYY' → ('YYYY-MM-01', 'YYYY-MM-dernier_jour')."""
        m, y = int(mois[:2]), int(mois[3:])
        debut = date(y, m, 1)
        fin   = date(y + 1, 1, 1) - timedelta(days=1) if m == 12 else date(y, m + 1, 1) - timedelta(days=1)
        return debut.strftime("%Y-%m-%d"), fin.strftime("%Y-%m-%d")

    @staticmethod
    def _dv_iso(alias: str = "Date_Valeur") -> str:
        """Expression SQL : retourne la colonne date (stockee en YYYY-MM-DD)."""
        return alias

    def _mois_courant(self) -> str:
        return datetime.now().strftime("%m/%Y")

    # =========================================================================
    # PART I — COMPTABLE : ARITHMÉTIQUE SIMPLE
    # =========================================================================

    def get_bilan_mensuel(self, mois: Optional[str] = None) -> BilanMensuel:
        """
        Revenus, Dépenses, Solde net du mois.
        Lit aussi EPARGNE_HISTO pour le cumul d'épargne.

        Paramètre : mois — 'MM/YYYY' (défaut : mois courant).
        """
        if mois is None:
            mois = self._mois_courant()
        d_deb, d_fin = self._mois_to_date_range(mois)
        dv = self._dv_iso()

        with self.db.connexion() as conn:
            row = conn.execute(
                f"""
                SELECT
                    SUM(CASE WHEN Sens = 'IN'  THEN  ABS(Montant) ELSE 0 END),
                    SUM(CASE WHEN Sens = 'OUT' THEN  ABS(Montant) ELSE 0 END),
                    SUM(Montant)
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ?
                  AND {dv} BETWEEN ? AND ?
                """,
                (self.user_id, d_deb, d_fin)
            ).fetchone()
            ep_row = conn.execute(
                f"""
                SELECT SUM(ABS(Montant)) FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND Sens = 'OUT' AND user_id = ?
                  AND Categorie IN ('Epargne', 'Finances Credits')
                  AND {dv} BETWEEN ? AND ?
                """,
                (self.user_id, d_deb, d_fin)
            ).fetchone()

        revenus  = round(float(row[0] or 0), 2)
        depenses = round(float(row[1] or 0), 2)
        solde    = round(float(row[2] or 0), 2)
        ep_mois  = round(float(ep_row[0] or 0), 2) if ep_row else 0.0

        return BilanMensuel(
            mois=mois,
            revenus=revenus,
            depenses=depenses,
            epargne_reelle=ep_mois,
            evolution_dh=solde,
        )

    def get_cumul_epargne(self) -> float:
        with self.db.connexion() as conn:
            row = conn.execute(
                """SELECT SUM(ABS(Montant)) FROM TRANSACTIONS
                   WHERE Statut = 'VALIDE' AND Sens = 'OUT' AND user_id = ?
                   AND Categorie IN ('Epargne', 'Finances Credits')""",
                (self.user_id,)
            ).fetchone()
        return round(float(row[0] or 0), 2) if row else 0.0

    def get_solde_global(self) -> float:
        with self.db.connexion() as conn:
            row = conn.execute(
                "SELECT SUM(Montant) FROM TRANSACTIONS WHERE Statut = 'VALIDE' AND user_id = ?",
                (self.user_id,)
            ).fetchone()
        return round(float(row[0] or 0), 2)

    # =========================================================================
    # PART II — ANALYSTE : HIÉRARCHIE ET POIDS
    # =========================================================================

    def get_repartition_par_categorie(self, mois: Optional[str] = None) -> pd.DataFrame:
        """
        Total et poids (%) des dépenses par catégorie.

        Colonnes : Categorie, Total_DH, Poids_Pct
        Trié par Total_DH décroissant.
        """
        if mois is None:
            mois = self._mois_courant()
        d_deb, d_fin = self._mois_to_date_range(mois)
        dv = self._dv_iso()

        with self.db.connexion() as conn:
            df = pd.read_sql_query(
                f"""
                SELECT Categorie, SUM(ABS(Montant)) AS Total_DH
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND Sens = 'OUT' AND user_id = ?
                  AND {dv} BETWEEN ? AND ?
                GROUP BY Categorie
                ORDER BY Total_DH DESC
                """,
                conn, params=(self.user_id, d_deb, d_fin)
            )

        total = df["Total_DH"].sum()
        df["Poids_Pct"] = (df["Total_DH"] / total * 100).round(1) if total > 0 else 0.0
        return df

    def get_detail_par_sous_categorie(
        self,
        categorie: Optional[str] = None,
        mois: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Détail fin par sous-catégorie, avec poids %.

        Paramètres :
          categorie — Filtre sur une catégorie (None = toutes).
          mois      — 'MM/YYYY' (None = mois courant).

        Colonnes : Categorie, Sous_Categorie, Nb_Transactions, Total_DH, Poids_Pct
        """
        if mois is None:
            mois = self._mois_courant()
        d_deb, d_fin = self._mois_to_date_range(mois)
        dv = self._dv_iso()

        params: list = [self.user_id, d_deb, d_fin]
        filtre_cat = ""
        if categorie:
            filtre_cat = "AND Categorie = ?"
            params.append(categorie)

        with self.db.connexion() as conn:
            df = pd.read_sql_query(
                f"""
                SELECT
                    Categorie, Sous_Categorie,
                    COUNT(*) AS Nb_Transactions,
                    SUM(ABS(Montant)) AS Total_DH
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND Sens = 'OUT' AND user_id = ?
                  AND {dv} BETWEEN ? AND ?
                  {filtre_cat}
                GROUP BY Categorie, Sous_Categorie
                ORDER BY Total_DH DESC
                """,
                conn, params=params
            )

        total = df["Total_DH"].sum()
        df["Poids_Pct"] = (df["Total_DH"] / total * 100).round(1) if total > 0 else 0.0
        return df

    def get_grosses_depenses(
        self,
        mois: Optional[str] = None,
        top_n: int = TOP_N_DEPENSES,
    ) -> pd.DataFrame:
        """
        Mode Inspecteur — top N dépenses du mois, avec poids réel.

        Colonnes :
          Date_Valeur, Libelle, Montant, Categorie, Sous_Categorie,
          Poids_vs_Revenus_Pct   (dépense / revenus du mois × 100)
          Poids_vs_Depenses_Pct  (dépense / total dépenses × 100)

        Trié par Montant décroissant.
        """
        if mois is None:
            mois = self._mois_courant()
        d_deb, d_fin = self._mois_to_date_range(mois)
        dv = self._dv_iso()

        with self.db.connexion() as conn:
            # Revenus + total dépenses du mois
            row_totaux = conn.execute(
                f"""
                SELECT
                    SUM(CASE WHEN Sens = 'IN'  THEN  Montant     ELSE 0 END),
                    SUM(CASE WHEN Sens = 'OUT' THEN ABS(Montant) ELSE 0 END)
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ? AND {dv} BETWEEN ? AND ?
                """,
                (self.user_id, d_deb, d_fin)
            ).fetchone()

            df = pd.read_sql_query(
                f"""
                SELECT Date_Valeur, Libelle, ABS(Montant) AS Montant,
                       Categorie, Sous_Categorie
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ? AND Sens = 'OUT'
                  AND {dv} BETWEEN ? AND ?
                ORDER BY Montant DESC
                LIMIT ?
                """,
                conn, params=(self.user_id, d_deb, d_fin, top_n)
            )

        revenus       = float(row_totaux[0] or 0)
        total_depenses = float(row_totaux[1] or 0)

        df["Poids_vs_Revenus_Pct"]  = (
            (df["Montant"] / revenus       * 100).round(1) if revenus       > 0 else 0.0
        )
        df["Poids_vs_Depenses_Pct"] = (
            (df["Montant"] / total_depenses * 100).round(1) if total_depenses > 0 else 0.0
        )
        df["Montant"] = df["Montant"].round(2)
        return df.reset_index(drop=True)

    # =========================================================================
    # PART III — STRATÈGE : CHRONOLOGIE ET TENDANCES
    # =========================================================================

    def get_transactions_par_plage(
        self,
        date_debut: date,
        date_fin: date,
        sens: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Retourne toutes les transactions sur une plage de dates.

        Colonnes : ID_Unique, Date_Valeur, Libelle, Montant, Sens, Categorie, Sous_Categorie
        """
        dv = self._dv_iso()
        params: list = [self.user_id, date_debut.strftime("%Y-%m-%d"), date_fin.strftime("%Y-%m-%d")]
        filtre_sens = ""
        if sens:
            filtre_sens = "AND Sens = ?"
            params.append(sens.upper())

        with self.db.connexion() as conn:
            df = pd.read_sql_query(
                f"""
                SELECT ID_Unique, Date_Valeur, Libelle, Montant, Sens, Categorie, Sous_Categorie
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ?
                  AND {dv} BETWEEN ? AND ?
                  {filtre_sens}
                ORDER BY {dv} DESC
                """,
                conn, params=params
            )
        return df

    def get_tendances_jour_semaine(self, mois: Optional[str] = None) -> pd.DataFrame:
        """
        Dépenses OUT par jour de la semaine.

        Exploite strftime sur Date_Saisie (ISO YYYY-MM-DD HH:MM:SS).
        Colonnes : Jour_Semaine (0=Dim..6=Sam), Jour_Nom, Nb_Transactions, Total_DH, Moyenne_DH
        """
        if mois is None:
            mois = self._mois_courant()
        d_deb, d_fin = self._mois_to_date_range(mois)

        with self.db.connexion() as conn:
            df = pd.read_sql_query(
                """
                SELECT
                    CAST(strftime('%w', Date_Valeur) AS INTEGER) AS Jour_Semaine,
                    COUNT(*) AS Nb_Transactions,
                    ROUND(SUM(ABS(Montant)), 2) AS Total_DH,
                    ROUND(AVG(ABS(Montant)), 2) AS Moyenne_DH
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ? AND Sens = 'OUT'
                  AND Source != 'ONBOARDING'
                  AND Date_Valeur BETWEEN ? AND ?
                GROUP BY Jour_Semaine
                ORDER BY Jour_Semaine
                """,
                conn, params=(self.user_id, d_deb, d_fin)
            )

        jours = {0: "Dimanche", 1: "Lundi", 2: "Mardi", 3: "Mercredi",
                 4: "Jeudi", 5: "Vendredi", 6: "Samedi"}
        df["Jour_Nom"] = df["Jour_Semaine"].map(jours)
        return df[["Jour_Semaine", "Jour_Nom", "Nb_Transactions", "Total_DH", "Moyenne_DH"]]

    def get_evolution_mensuelle(self) -> pd.DataFrame:
        """
        Évolution mois par mois : revenus, dépenses, solde.

        Colonnes : Mois (YYYY-MM), Revenus, Depenses, Solde
        Trié chronologiquement.
        """
        dv = self._dv_iso()
        with self.db.connexion() as conn:
            df = pd.read_sql_query(
                f"""
                SELECT
                    substr({dv}, 1, 7) AS Mois,
                    ROUND(SUM(CASE WHEN Sens = 'IN'  THEN  ABS(Montant) ELSE 0 END), 2) AS Revenus,
                    ROUND(SUM(CASE WHEN Sens = 'OUT' THEN  ABS(Montant) ELSE 0 END), 2) AS Depenses,
                    ROUND(SUM(Montant), 2) AS Solde
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ?
                  AND Source != 'ONBOARDING'
                GROUP BY Mois
                ORDER BY Mois ASC
                """,
                conn, params=(self.user_id,)
            )
        return df

    def get_croisement_categorie_periode(
        self,
        groupby: str = "mois",
        mois: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Tableau croisé : catégorie × période.

        Paramètres :
          groupby — 'mois' | 'jour_semaine' | 'heure'
          mois    — Filtre sur un mois précis (None = tous).

        Retourne un pivot : périodes en lignes, catégories en colonnes.
        """
        dv = self._dv_iso()
        periode_expr = {
            "mois":         f"substr({dv}, 1, 7)",
            "jour_semaine": "strftime('%w', Date_Saisie)",
            "heure":        "strftime('%H', Date_Saisie)",
        }.get(groupby, f"substr({dv}, 1, 7)")

        params: list = [self.user_id]
        filtre_mois = ""
        if mois:
            d_deb, d_fin = self._mois_to_date_range(mois)
            filtre_mois = f"AND {dv} BETWEEN ? AND ?"
            params.extend([d_deb, d_fin])

        with self.db.connexion() as conn:
            df = pd.read_sql_query(
                f"""
                SELECT {periode_expr} AS Periode, Categorie, ROUND(SUM(ABS(Montant)), 2) AS Total_DH
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ? AND Sens = 'OUT'
                  {filtre_mois}
                GROUP BY Periode, Categorie
                ORDER BY Periode
                """,
                conn, params=params
            )

        if df.empty:
            return df
        pivot = df.pivot_table(
            index="Periode", columns="Categorie", values="Total_DH", fill_value=0
        ).round(2)
        pivot.columns.name = None
        return pivot.reset_index()

    # =========================================================================
    # PART IV — VISIONNAIRE : BUDGET VS RÉEL + PROJECTION
    # =========================================================================

    def get_budget_vs_reel(self, mois: Optional[str] = None) -> pd.DataFrame:
        """
        Compare budget (CATEGORIES.Plafond) aux dépenses réelles du mois.

        Colonnes : Categorie, Sous_Categorie, Budget_DH, Reel_DH, Ecart_DH, Taux_Consommation_Pct
        Trié par Taux_Consommation_Pct décroissant (les plus critiques en premier).
        """
        if mois is None:
            mois = self._mois_courant()
        d_deb, d_fin = self._mois_to_date_range(mois)
        dv = self._dv_iso()

        with self.db.connexion() as conn:
            df_budget = pd.read_sql_query(
                "SELECT Categorie, Sous_Categorie, Plafond AS Budget_DH FROM CATEGORIES WHERE Plafond > 0",
                conn
            )
            df_reel = pd.read_sql_query(
                f"""
                SELECT Categorie, Sous_Categorie, ROUND(SUM(ABS(Montant)), 2) AS Reel_DH
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ? AND Sens = 'OUT'
                  AND {dv} BETWEEN ? AND ?
                GROUP BY Categorie, Sous_Categorie
                """,
                conn, params=(self.user_id, d_deb, d_fin)
            )

        df = df_budget.merge(df_reel, on=["Categorie", "Sous_Categorie"], how="left")
        df["Reel_DH"]   = pd.to_numeric(df["Reel_DH"],   errors="coerce").fillna(0.0).round(2)
        df["Budget_DH"] = pd.to_numeric(df["Budget_DH"], errors="coerce").fillna(0.0).round(2)
        df["Ecart_DH"]  = (df["Budget_DH"] - df["Reel_DH"]).round(2)
        df["Taux_Consommation_Pct"] = (
            (df["Reel_DH"] / df["Budget_DH"].replace(0, float("nan")) * 100)
            .clip(upper=999).round(1).fillna(0.0)
        )
        return df.sort_values("Taux_Consommation_Pct", ascending=False).reset_index(drop=True)

    def get_projection_fin_mois(self, mois: Optional[str] = None) -> Dict[str, Any]:
        """
        Projette les dépenses jusqu'à la fin du mois.

        Méthode : taux_journalier = dépenses_actuelles / jours_écoulés
                  projection = taux_journalier × jours_total

        Retourne un dict avec jours_ecoules, taux_journalier, projection_fin_mois, solde_projete.
        """
        if mois is None:
            mois = self._mois_courant()
        d_deb, d_fin = self._mois_to_date_range(mois)
        dv = self._dv_iso()

        dt_deb = datetime.strptime(d_deb, "%Y-%m-%d").date()
        dt_fin = datetime.strptime(d_fin, "%Y-%m-%d").date()
        aujourd_hui   = date.today()
        jours_ecoules = max(1, (min(aujourd_hui, dt_fin) - dt_deb).days + 1)
        jours_total   = (dt_fin - dt_deb).days + 1
        jours_restants = max(0, (dt_fin - aujourd_hui).days)

        with self.db.connexion() as conn:
            row = conn.execute(
                f"""
                SELECT
                    SUM(CASE WHEN Sens = 'IN'  THEN  Montant ELSE 0 END),
                    SUM(CASE WHEN Sens = 'OUT' THEN ABS(Montant) ELSE 0 END)
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ? AND {dv} BETWEEN ? AND ?
                """,
                (self.user_id, d_deb, d_fin)
            ).fetchone()

            # Charges fixes du mois (Logement + Epargne) — déjà payées, ne pas extrapoler
            fixes_row = conn.execute(
                f"""
                SELECT SUM(ABS(Montant)) FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ? AND Sens = 'OUT'
                  AND Categorie IN ('Logement', 'Epargne', 'Finances Credits')
                  AND {dv} BETWEEN ? AND ?
                """,
                (self.user_id, d_deb, d_fin)
            ).fetchone()

        revenus        = round(float(row[0] or 0), 2)
        depenses       = round(float(row[1] or 0), 2)
        fixes_ce_mois  = round(float(fixes_row[0] or 0), 2)
        variables      = max(0.0, depenses - fixes_ce_mois)

        # Taux journalier sur les dépenses VARIABLES uniquement (hors loyer/épargne)
        taux_jour  = round(variables / jours_ecoules, 2)
        # Projection = charges fixes (déjà payées pour le mois) + variable extrapolée
        projection = round(fixes_ce_mois + taux_jour * jours_total, 2)
        solde_proj = round(revenus - projection, 2)

        pct_ecoule = round(jours_ecoules / jours_total * 100, 1)

        return {
            "mois":                mois,
            "jours_ecoules":       jours_ecoules,
            "jours_restants":      jours_restants,
            "jours_total":         jours_total,
            "pct_mois_ecoule":     pct_ecoule,
            "depenses_actuelles":  depenses,
            "taux_journalier":     taux_jour,
            "projection_fin_mois": projection,
            "revenus_actuels":     revenus,
            "solde_projete":       solde_proj,
        }

    def get_charges_fixes(self, nb_mois_min: int = 2) -> pd.DataFrame:
        """
        Détecte les charges fixes récurrentes (même libellé sur >= nb_mois_min mois).

        Colonnes : Libelle, Nb_Mois, Montant_Moyen, Categorie, Sous_Categorie
        """
        dv = self._dv_iso()
        with self.db.connexion() as conn:
            df = pd.read_sql_query(
                f"""
                SELECT
                    Libelle,
                    COUNT(DISTINCT substr({dv}, 1, 7)) AS Nb_Mois,
                    ROUND(AVG(ABS(Montant)), 2) AS Montant_Moyen,
                    Categorie, Sous_Categorie
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ? AND Sens = 'OUT'
                GROUP BY Libelle, Categorie, Sous_Categorie
                HAVING Nb_Mois >= ?
                ORDER BY Montant_Moyen DESC
                """,
                conn, params=(self.user_id, nb_mois_min)
            )
        return df

    def get_analyse_5030_20(
        self,
        mois: Optional[str] = None,
        mapping: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Règle budgétaire 50/30/20 — compare réel vs cible.

        Paramètre mapping (optionnel, personnalisable via audit.py) :
        {
          "Needs":   {"cible_pct": 50, "categories": {"Logement", "Alimentation", ...}},
          "Wants":   {"cible_pct": 30, "categories": {"Loisirs", "Abonnements", ...}},
          "Savings": {"cible_pct": 20, "categories": {"Finances Credits", ...}},
        }

        Retourne :
        {
          "mois": ...,
          "revenus": ...,
          "buckets": {
            "Needs":   { cible_pct, cible_dh, reel_dh, reel_pct, ecart_dh, ecart_pct, statut },
            "Wants":   { ... },
            "Savings": { ... },
          },
          "non_classe_dh": ...,    # dépenses dont la catégorie n'est dans aucun bucket
          "score_respect": float,  # 0–100, 100 = parfaitement dans les cibles
        }
        """
        if mois is None:
            mois = self._mois_courant()
        if mapping is None:
            mapping = {
                "Needs": {
                    "cible_pct": 50.0,
                    "categories": {
                        "Logement", "Alimentation", "Transport",
                        "Sante", "Santé", "Vie Quotidienne",
                    },
                },
                "Wants": {
                    "cible_pct": 30.0,
                    "categories": {"Loisirs", "Abonnements", "Divers"},
                },
                "Savings": {
                    "cible_pct": 20.0,
                    "categories": {"Finances Credits", "Epargne"},
                },
            }

        d_deb, d_fin = self._mois_to_date_range(mois)
        dv = self._dv_iso()

        with self.db.connexion() as conn:
            # Revenus du mois
            row_rev = conn.execute(
                f"""
                SELECT SUM(Montant) FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ? AND Sens = 'IN'
                  AND {dv} BETWEEN ? AND ?
                """,
                (self.user_id, d_deb, d_fin)
            ).fetchone()

            # Dépenses OUT par catégorie du mois
            rows_dep = conn.execute(
                f"""
                SELECT Categorie, SUM(ABS(Montant)) AS Total
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ? AND Sens = 'OUT'
                  AND {dv} BETWEEN ? AND ?
                GROUP BY Categorie
                """,
                (self.user_id, d_deb, d_fin)
            ).fetchall()

        revenus = round(float(row_rev[0] or 0), 2)

        # Totaux réels par catégorie
        dep_par_cat: Dict[str, float] = {
            str(r[0]): round(float(r[1] or 0), 2) for r in rows_dep
        }
        total_dep = round(sum(dep_par_cat.values()), 2)

        # Construction des buckets
        buckets: Dict[str, Any] = {}
        cats_classees: set = set()

        for bucket, cfg in mapping.items():
            cible_pct = float(cfg["cible_pct"])
            cats_bucket = set(cfg["categories"])
            cats_classees |= cats_bucket

            cible_dh  = round(revenus * cible_pct / 100, 2) if revenus > 0 else 0.0
            reel_dh   = round(sum(dep_par_cat.get(c, 0.0) for c in cats_bucket), 2)
            reel_pct  = round(reel_dh / revenus * 100, 2) if revenus > 0 else 0.0
            ecart_dh  = round(reel_dh - cible_dh, 2)
            ecart_pct = round(reel_pct - cible_pct, 2)
            statut    = (
                "OK"       if abs(ecart_pct) <= 5  else
                "ATTENTION" if abs(ecart_pct) <= 15 else
                "DEPASSE"
            )

            buckets[bucket] = {
                "cible_pct": cible_pct,
                "cible_dh":  cible_dh,
                "reel_dh":   reel_dh,
                "reel_pct":  reel_pct,
                "ecart_dh":  ecart_dh,
                "ecart_pct": ecart_pct,
                "statut":    statut,
                "categories": sorted(cats_bucket),
            }

        # Dépenses non assignées à un bucket
        non_classe = round(
            sum(v for k, v in dep_par_cat.items() if k not in cats_classees), 2
        )

        # Score de respect 0–100 (100 = tous buckets dans la cible ±5%)
        nb_ok    = sum(1 for b in buckets.values() if b["statut"] == "OK")
        score_r  = round(nb_ok / len(buckets) * 100, 1) if buckets else 0.0

        return {
            "mois":          mois,
            "revenus":       revenus,
            "total_depenses": total_dep,
            "buckets":       buckets,
            "non_classe_dh": non_classe,
            "score_respect": score_r,
        }

    def get_comparaison_vs_habitudes(
        self,
        mois: Optional[str] = None,
        nb_mois_ref: int = NB_MOIS_REF_DEFAUT,
    ) -> pd.DataFrame:
        """
        Mode Coach — compare chaque sous-catégorie du mois courant
        vs la moyenne des N mois précédents.

        Colonnes :
          Categorie, Sous_Categorie,
          Mois_Courant_DH    (dépense ce mois)
          Moyenne_Ref_DH     (moyenne sur nb_mois_ref mois précédents)
          Ecart_DH           (Mois_Courant - Moyenne_Ref)
          Ecart_Pct          (Ecart / Moyenne_Ref × 100, None si pas d'historique)
          Tendance           ('HAUSSE' | 'BAISSE' | 'STABLE' | 'NOUVEAU')

        Trié par Ecart_Pct décroissant (les dérives les plus fortes en premier).
        """
        if mois is None:
            mois = self._mois_courant()
        d_deb, d_fin = self._mois_to_date_range(mois)
        dv = self._dv_iso()

        # Mois de référence : les N mois précédents (avant d_deb)
        dt_deb = datetime.strptime(d_deb, "%Y-%m-%d").date()
        ref_fin = (dt_deb - timedelta(days=1)).strftime("%Y-%m-%d")
        ref_deb = (
            dt_deb.replace(year=dt_deb.year - 1)
            if nb_mois_ref >= 12
            else (dt_deb - timedelta(days=nb_mois_ref * 31)).strftime("%Y-%m-%d")
        )

        with self.db.connexion() as conn:
            # Dépenses du mois courant par sous-catégorie
            df_courant = pd.read_sql_query(
                f"""
                SELECT Categorie, Sous_Categorie,
                       ROUND(SUM(ABS(Montant)), 2) AS Mois_Courant_DH
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ? AND Sens = 'OUT'
                  AND {dv} BETWEEN ? AND ?
                GROUP BY Categorie, Sous_Categorie
                """,
                conn, params=(self.user_id, d_deb, d_fin)
            )

            # Moyenne mensuelle sur la période de référence
            df_ref = pd.read_sql_query(
                f"""
                SELECT
                    Categorie, Sous_Categorie,
                    ROUND(SUM(ABS(Montant)) / COUNT(DISTINCT substr({dv}, 1, 7)), 2)
                        AS Moyenne_Ref_DH
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ? AND Sens = 'OUT'
                  AND {dv} BETWEEN ? AND ?
                GROUP BY Categorie, Sous_Categorie
                """,
                conn, params=(self.user_id, ref_deb, ref_fin)
            )

        # Fusion outer pour capturer "NOUVEAU" (présent ce mois, absent historique)
        df = df_courant.merge(
            df_ref, on=["Categorie", "Sous_Categorie"], how="outer"
        )
        df["Mois_Courant_DH"] = df["Mois_Courant_DH"].fillna(0.0)
        df["Moyenne_Ref_DH"]  = df["Moyenne_Ref_DH"].fillna(0.0)

        def _ecart_pct(row):
            ref = row["Moyenne_Ref_DH"]
            cur = row["Mois_Courant_DH"]
            if ref == 0:
                return None
            return round((cur - ref) / ref * 100, 1)

        def _tendance(row):
            if row["Moyenne_Ref_DH"] == 0:
                return "NOUVEAU"
            ep = row.get("Ecart_Pct")
            if ep is None:
                return "STABLE"
            if ep >  10:
                return "HAUSSE"
            if ep < -10:
                return "BAISSE"
            return "STABLE"

        df["Ecart_DH"]  = (df["Mois_Courant_DH"] - df["Moyenne_Ref_DH"]).round(2)
        df["Ecart_Pct"] = df.apply(_ecart_pct, axis=1)
        df["Tendance"]  = df.apply(_tendance,  axis=1)

        return (
            df[["Categorie", "Sous_Categorie",
                "Mois_Courant_DH", "Moyenne_Ref_DH",
                "Ecart_DH", "Ecart_Pct", "Tendance"]]
            .sort_values("Ecart_Pct", ascending=False, na_position="last")
            .reset_index(drop=True)
        )

    # =========================================================================
    # PART V — COACH : ANOMALIES, SCORE SANTÉ, ALERTES
    # =========================================================================

    def detecter_anomalies(
        self,
        mois: Optional[str] = None,
        seuil_sigma: float = 2.0,
    ) -> pd.DataFrame:
        """
        Détecte les dépenses inhabituelles (Z-Score >= seuil_sigma).

        La moyenne et l'écart-type sont calculés sur l'historique complet de chaque catégorie.

        Colonnes : Date_Valeur, Libelle, Montant, Categorie, Moyenne_Cat, Ecart_Type_Cat, Z_Score
        """
        if mois is None:
            mois = self._mois_courant()
        d_deb, d_fin = self._mois_to_date_range(mois)
        dv = self._dv_iso()

        with self.db.connexion() as conn:
            # Stats historiques par catégorie
            df_stats = pd.read_sql_query(
                """
                SELECT
                    Categorie,
                    AVG(ABS(Montant)) AS Moyenne_Cat,
                    AVG(ABS(Montant) * ABS(Montant)) - AVG(ABS(Montant)) * AVG(ABS(Montant)) AS Variance_Cat
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ? AND Sens = 'OUT'
                GROUP BY Categorie
                """,
                conn, params=(self.user_id,)
            )
            # Transactions du mois analysé
            df_mois = pd.read_sql_query(
                f"""
                SELECT Date_Valeur, Libelle, ABS(Montant) AS Montant, Categorie
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ? AND Sens = 'OUT'
                  AND {dv} BETWEEN ? AND ?
                """,
                conn, params=(self.user_id, d_deb, d_fin)
            )

        if df_mois.empty or df_stats.empty:
            return pd.DataFrame(columns=["Date_Valeur", "Libelle", "Montant",
                                         "Categorie", "Moyenne_Cat", "Ecart_Type_Cat", "Z_Score"])

        df_stats["Ecart_Type_Cat"] = df_stats["Variance_Cat"].apply(
            lambda v: math.sqrt(max(float(v or 0), 0))
        ).round(2)
        df_stats["Moyenne_Cat"] = df_stats["Moyenne_Cat"].round(2)

        df = df_mois.merge(df_stats[["Categorie", "Moyenne_Cat", "Ecart_Type_Cat"]],
                           on="Categorie", how="left")

        def _z(row):
            et = row["Ecart_Type_Cat"]
            return round((row["Montant"] - row["Moyenne_Cat"]) / et, 2) if et > 0 else 0.0

        df["Z_Score"] = df.apply(_z, axis=1)
        return (df[df["Z_Score"] >= seuil_sigma]
                .sort_values("Z_Score", ascending=False)
                .reset_index(drop=True))

    def get_score_sante_financiere(self, mois: Optional[str] = None) -> Dict[str, Any]:
        """
        Score de santé financière sur 100.

        Composantes :
          - Taux d'épargne       (40 pts max) : épargne_reel / revenus × 100,  20% cible = 40 pts
          - Respect des budgets  (40 pts max) : proportion catégories dans les plafonds
          - Diversification      (20 pts max) : aucune catégorie ne monopolise > 40% des dépenses

        Retourne : { score, niveau, taux_epargne_pct, nb_depassements, details }
        """
        if mois is None:
            mois = self._mois_courant()

        bilan  = self.get_bilan_mensuel(mois)
        bvr    = self.get_budget_vs_reel(mois)
        repart = self.get_repartition_par_categorie(mois)

        # Composante 1 — Épargne
        taux_ep   = (bilan.epargne_reelle / bilan.revenus * 100) if bilan.revenus > 0 else 0.0
        pts_ep    = min(SCORE_POIDS_EPARGNE, round(taux_ep / 20 * SCORE_POIDS_EPARGNE, 1))

        # Composante 2 — Budgets
        nb_lignes = len(bvr)
        nb_dep    = int((bvr["Taux_Consommation_Pct"] > 100).sum()) if nb_lignes > 0 else 0
        pts_bgt   = round(SCORE_POIDS_BUDGET * (1 - nb_dep / max(nb_lignes, 1)), 1)

        # Composante 3 — Diversification
        pts_div   = SCORE_POIDS_DIVERS
        if not repart.empty:
            pmax = repart["Poids_Pct"].max()
            if   pmax > 80: pts_div = 0.0
            elif pmax > 60: pts_div = round(SCORE_POIDS_DIVERS * 0.5, 1)
            elif pmax > 40: pts_div = round(SCORE_POIDS_DIVERS * 0.75, 1)

        score = round(pts_ep + pts_bgt + pts_div, 1)
        niveau = ("EXCELLENT" if score >= SCORE_NIVEAU_EXCELLENT else
                  "BON"       if score >= SCORE_NIVEAU_BON       else
                  "MOYEN"     if score >= SCORE_NIVEAU_MOYEN     else "CRITIQUE")

        return {
            "mois":             mois,
            "score":            score,
            "niveau":           niveau,
            "taux_epargne_pct": round(taux_ep, 1),
            "nb_depassements":  nb_dep,
            "details": {
                "pts_epargne": pts_ep,
                "pts_budget":  pts_bgt,
                "pts_divers":  pts_div,
            },
        }

    def get_alertes_seuil(
        self,
        seuil_pct: float = 80.0,
        mois: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Catégories ayant atteint >= seuil_pct% de leur budget.

        Retourne une liste de dicts :
          { categorie, sous_categorie, budget, reel, taux_pct, niveau_alerte }
          niveau_alerte : 'WARNING' (>= seuil) | 'CRITIQUE' (>= 100%)
        """
        if mois is None:
            mois = self._mois_courant()
        bvr = self.get_budget_vs_reel(mois)
        alertes = bvr[bvr["Taux_Consommation_Pct"] >= seuil_pct]

        return [
            {
                "categorie":      row["Categorie"],
                "sous_categorie": row["Sous_Categorie"],
                "budget":         row["Budget_DH"],
                "reel":           row["Reel_DH"],
                "taux_pct":       row["Taux_Consommation_Pct"],
                "niveau_alerte":  "CRITIQUE" if row["Taux_Consommation_Pct"] >= 100 else "WARNING",
            }
            for _, row in alertes.iterrows()
        ]

    def detecter_doublons(self, fenetre_jours: int = 1) -> pd.DataFrame:
        """
        Transactions potentiellement en doublon :
        même Libelle + même Montant dans une fenêtre de N jours.

        Colonnes : ID_Unique, Date_Valeur, Libelle, Montant, Categorie
        """
        dv  = self._dv_iso()
        dv1 = self._dv_iso("t1.Date_Valeur")
        dv2 = self._dv_iso("t2.Date_Valeur")

        with self.db.connexion() as conn:
            df = pd.read_sql_query(
                f"""
                SELECT DISTINCT t1.ID_Unique, t1.Date_Valeur, t1.Libelle, t1.Montant, t1.Categorie
                FROM TRANSACTIONS t1
                INNER JOIN TRANSACTIONS t2
                    ON  t1.Libelle   = t2.Libelle
                    AND t1.Montant   = t2.Montant
                    AND t1.user_id   = t2.user_id
                    AND t1.ID_Unique != t2.ID_Unique
                    AND ABS(julianday({dv1}) - julianday({dv2})) <= ?
                WHERE t1.Statut = 'VALIDE' AND t1.user_id = ?
                ORDER BY t1.Libelle, t1.Date_Valeur
                """,
                conn, params=(fenetre_jours, self.user_id)
            )
        return df

    # =========================================================================
    # PART VI — SIMULATEUR : SCÉNARIOS "ET SI ?"
    # =========================================================================

    def _epargne_mensuelle_moyenne(self, nb_mois: int = 3) -> float:
        """Épargne nette mensuelle moyenne sur les N derniers mois."""
        dv = self._dv_iso()
        with self.db.connexion() as conn:
            rows = conn.execute(
                f"""
                SELECT SUM(Montant) AS Solde_Mois
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ?
                GROUP BY substr({dv}, 1, 7)
                ORDER BY substr({dv}, 1, 7) DESC
                LIMIT ?
                """,
                (self.user_id, nb_mois)
            ).fetchall()
        if not rows:
            return 0.0
        return round(sum(float(r[0] or 0) for r in rows) / len(rows), 2)

    def _depenses_mensuelles_moyennes(self, nb_mois: int = 3) -> float:
        """Dépenses OUT mensuelles moyennes sur les N derniers mois."""
        dv = self._dv_iso()
        with self.db.connexion() as conn:
            rows = conn.execute(
                f"""
                SELECT SUM(ABS(Montant)) AS Dep_Mois
                FROM TRANSACTIONS
                WHERE Statut = 'VALIDE' AND user_id = ? AND Sens = 'OUT'
                GROUP BY substr({dv}, 1, 7)
                ORDER BY substr({dv}, 1, 7) DESC
                LIMIT ?
                """,
                (self.user_id, nb_mois)
            ).fetchall()
        if not rows:
            return 0.0
        return round(sum(float(r[0] or 0) for r in rows) / len(rows), 2)

    def simuler_impact_projet(
        self,
        montant_projet: float,
        mois_cibles: int = 12,
    ) -> Dict[str, Any]:
        """
        Impact d'une dépense exceptionnelle (one-shot) sur l'épargne future.

        Paramètres :
          montant_projet — Montant de la dépense (DH).
          mois_cibles    — Horizon de simulation (mois).

        Retourne :
          { montant_projet, mois_cibles, epargne_mensuelle_actuelle,
            mois_pour_rembourser, solde_sans_projet, solde_avec_projet,
            impact_net, faisable }
        """
        ep_mensuelle     = self._epargne_mensuelle_moyenne()
        cumul_actuel     = self.get_cumul_epargne()
        solde_sans       = round(cumul_actuel + ep_mensuelle * mois_cibles, 2)
        solde_avec       = round(solde_sans - montant_projet, 2)
        mois_remboursement = (
            math.ceil(montant_projet / ep_mensuelle) if ep_mensuelle > 0 else None
        )
        faisable = mois_remboursement is not None and mois_remboursement <= mois_cibles

        return {
            "montant_projet":            montant_projet,
            "mois_cibles":               mois_cibles,
            "epargne_mensuelle_actuelle": ep_mensuelle,
            "mois_pour_rembourser":      mois_remboursement,
            "solde_sans_projet":         solde_sans,
            "solde_avec_projet":         solde_avec,
            "impact_net":                round(-montant_projet, 2),
            "faisable":                  faisable,
        }

    def simuler_objectif_epargne(
        self,
        cible_dh: float,
        nb_mois: int,
    ) -> Dict[str, Any]:
        """
        Effort mensuel nécessaire pour atteindre un objectif d'épargne.

        Paramètres :
          cible_dh — Montant cible total d'épargne (DH).
          nb_mois  — Délai pour y arriver.

        Retourne :
          { cible_dh, nb_mois, epargne_actuelle_cumul, manque_a_epargner,
            effort_mensuel_requis, epargne_mensuelle_actuelle,
            atteignable, reductions_suggerees }
        """
        cumul        = self.get_cumul_epargne()
        manque       = round(max(0.0, cible_dh - cumul), 2)
        effort       = round(manque / nb_mois, 2) if nb_mois > 0 else manque
        ep_mensuelle = self._epargne_mensuelle_moyenne()
        atteignable  = effort <= ep_mensuelle * 0.5

        # Top 3 sous-catégories → suggestions de réduction à 15%
        detail = self.get_detail_par_sous_categorie()
        reductions = [
            {
                "sous_categorie":           row["Sous_Categorie"],
                "depense_actuelle":         row["Total_DH"],
                "reduction_suggeree_15pct": round(row["Total_DH"] * 0.15, 2),
            }
            for _, row in detail.head(3).iterrows()
        ] if not detail.empty else []

        return {
            "cible_dh":                  cible_dh,
            "nb_mois":                   nb_mois,
            "epargne_actuelle_cumul":    cumul,
            "manque_a_epargner":         manque,
            "effort_mensuel_requis":     effort,
            "epargne_mensuelle_actuelle": ep_mensuelle,
            "atteignable":               atteignable,
            "reductions_suggerees":      reductions,
        }

    def simuler_crash_test(self, nb_mois_sans_revenu: int = 3) -> Dict[str, Any]:
        """
        "Et si je perdais mes revenus N mois ?" — Résistance du capital.

        Retourne :
          { nb_mois_sans_revenu, solde_actuel, depenses_mensuelles_moyennes,
            mois_de_resistance, date_epuisement_estimee,
            statut ('RESISTANT'|'FRAGILE'|'CRITIQUE'), manque_prevu }
        """
        solde      = self.get_solde_global()
        dep_mois   = self._depenses_mensuelles_moyennes()
        mois_res   = int(solde / dep_mois) if dep_mois > 0 else 999

        date_ep    = None
        if dep_mois > 0 and solde > 0:
            date_ep = (date.today() + timedelta(days=mois_res * 30)).strftime("%m/%Y")

        cout_scenario = round(dep_mois * nb_mois_sans_revenu, 2)
        manque        = round(max(0.0, cout_scenario - solde), 2)

        statut = ("RESISTANT" if mois_res >= nb_mois_sans_revenu * 2 else
                  "FRAGILE"   if mois_res >= nb_mois_sans_revenu      else "CRITIQUE")

        return {
            "nb_mois_sans_revenu":          nb_mois_sans_revenu,
            "solde_actuel":                 round(solde, 2),
            "depenses_mensuelles_moyennes": round(dep_mois, 2),
            "mois_de_resistance":           mois_res,
            "date_epuisement_estimee":      date_ep,
            "statut":                       statut,
            "manque_prevu":                 manque,
        }


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE — DÉMONSTRATION
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    )

    # ── Initialisation ────────────────────────────────────────────────────────
    from db_manager import DatabaseManager

    db = DatabaseManager(DB_PATH)
    db.initialiser_schema()

    # Seed des catégories (lecture seule pour l'utilisateur)
    db.seed_categories([
        {"Categorie": "Alimentation", "Sous_Categorie": "Supermarché", "Plafond": 500},
        {"Categorie": "Alimentation", "Sous_Categorie": "Restaurant", "Plafond": 200},
        {"Categorie": "Transport", "Sous_Categorie": "Carburant", "Plafond": 150},
        {"Categorie": "Loisirs", "Sous_Categorie": "Streaming", "Plafond": 50},
        {"Categorie": "Revenu", "Sous_Categorie": "Salaire", "Plafond": 0},
        {"Categorie": "Divers", "Sous_Categorie": "Autre", "Plafond": 100},
    ])

    # Seed de transactions de test (A_CLASSIFIER)
    df_test = pd.DataFrame([
        {"ID_Unique": "20260401_001", "Date_Saisie": "2026-04-01 10:00:00",
         "Date_Valeur": "01/04/2026", "Libelle": "CARREFOUR MARKET", "Montant": -45.50, "Sens": "OUT"},
        {"ID_Unique": "20260402_001", "Date_Saisie": "2026-04-02 09:00:00",
         "Date_Valeur": "02/04/2026", "Libelle": "NETFLIX MENSUEL", "Montant": -15.99, "Sens": "OUT"},
        {"ID_Unique": "20260403_001", "Date_Saisie": "2026-04-03 08:00:00",
         "Date_Valeur": "03/04/2026", "Libelle": "VIREMENT SALAIRE", "Montant": 3500.00, "Sens": "IN"},
        {"ID_Unique": "20260404_001", "Date_Saisie": "2026-04-04 12:00:00",
         "Date_Valeur": "04/04/2026", "Libelle": "CARREFOUR EXPRESS", "Montant": -12.30, "Sens": "OUT"},
    ])
    db.importer_transactions_df(df_test)

    # ── Test du moteur ────────────────────────────────────────────────────────
    engine = ClassificationEngine(DB_PATH)

    print("\n" + "=" * 60)
    print("AVANT CLASSIFICATION")
    print("=" * 60)
    print(f"Catégories disponibles : {engine.get_available_categories()}")
    print(f"\nTransactions à classifier :\n{engine.get_unclassified_transactions()}")

    # Application d'une règle
    print("\n" + "=" * 60)
    print("APPLICATION DE RÈGLES")
    print("=" * 60)
    
    nb = engine.apply_classification_rule(
        sens="OUT",
        mot_cle="CARREFOUR",
        montant=None,  # Match tous les montants
        categorie_cible="Alimentation"
    )
    print(f"→ {nb} transaction(s) 'CARREFOUR' classée(s) en 'Alimentation'")

    nb = engine.apply_classification_rule(
        sens="OUT",
        mot_cle="NETFLIX",
        montant=None,
        categorie_cible="Loisirs"
    )
    print(f"→ {nb} transaction(s) 'NETFLIX' classée(s) en 'Loisirs'")

    nb = engine.apply_classification_rule(
        sens="IN",
        mot_cle="SALAIRE",
        montant=3500.0,  # Match exact
        categorie_cible="Revenu"
    )
    print(f"→ {nb} transaction(s) 'SALAIRE 3500€' classée(s) en 'Revenu'")

    print("\n" + "=" * 60)
    print("APRÈS CLASSIFICATION")
    print("=" * 60)
    print(f"Transactions restantes à classifier :\n{engine.get_unclassified_transactions()}")
    print(f"\nTransactions classées :\n{engine.get_classified_transactions()}")
    print(f"\nRègles créées :\n{engine.get_classification_rules()}")
    print(f"\nStats par catégorie :\n{engine.get_stats_by_category()}")
