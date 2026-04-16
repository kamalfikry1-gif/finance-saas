"""
DB_MANAGER.PY — GESTIONNAIRE POSTGRESQL (Supabase)
====================================================
Migration SQLite → PostgreSQL pour le déploiement cloud.

Architecture :
  - psycopg2 avec ThreadedConnectionPool (thread-safe pour Streamlit)
  - _ConnProxy : wrapper sqlite3-compatible (conn.execute, conn.executemany)
    → convertit automatiquement les placeholders ? → %s
  - Toutes les tables de données ont un user_id (multi-tenant)
  - Tables partagées sans user_id : CATEGORIES, REFERENTIEL, DICO_MATCHING

Usage :
    db = DatabaseManager(st.secrets["DATABASE_URL"])
    db.initialiser_schema()

    with db.connexion() as conn:
        conn.execute("SELECT * FROM TRANSACTIONS WHERE user_id = %s", (uid,))
"""

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.pool
import psycopg2.extras

from config import (
    DEVISE,
    COACH_IDENTITE_DEFAUT,
    SEUIL_ALERTE_DEFAUT,
    NEEDS_PCT_DEFAUT,
    WANTS_PCT_DEFAUT,
    SAVINGS_PCT_DEFAUT,
)

logger = logging.getLogger("DB_MANAGER")

STATUT_A_CLASSIFIER = "A_CLASSIFIER"
STATUT_VALIDE        = "VALIDE"


# ─────────────────────────────────────────────────────────────────────────────
# HELPER — Canonical column casing
# ─────────────────────────────────────────────────────────────────────────────
# Postgres folds unquoted identifiers to lowercase, so DictCursor rows come
# back as {"categorie": ..., "sous_categorie": ...}. Views were written
# against the original mixed-case schema names. _canon_dict() rebuilds the
# dict using the canonical casing declared in CREATE TABLE.

_CANONICAL_COLS = {c.lower(): c for c in (
    # TRANSACTIONS
    "ID_Unique", "Date_Saisie", "Date_Valeur", "Libelle", "Montant", "Sens",
    "Categorie", "Sous_Categorie", "Statut", "Source",
    # OBJECTIFS
    "Nom", "Type", "Montant_Cible", "Montant_Actuel", "Date_Cible",
    "Date_Creation", "Icone", "Couleur",
    # JOURNAL
    "Date_Entree", "Note", "Tags", "Humeur", "ID_Transaction",
    # CATEGORIES / BUDGETS
    "Plafond", "Mois",
    # REFERENTIEL / DICO_MATCHING
    "Frequence", "Compteur_N", "Montant_Cumule", "Mot_Cle",
    # AUDIT_LOG
    "Timestamp", "Role", "Action", "Input_Raw", "Output_Raw",
)}


def _canon_dict(row) -> Dict:
    """Convert a DictRow (lowercased keys) to a dict with canonical casing."""
    return {_CANONICAL_COLS.get(k, k): v for k, v in dict(row).items()}


# ─────────────────────────────────────────────────────────────────────────────
# HELPER — Extract SELECT column names preserving original SQL case
# ─────────────────────────────────────────────────────────────────────────────

import re as _re

def _extract_col_names(sql: str) -> list:
    """
    Extract SELECT column names/aliases from a SQL string, preserving the
    original case as written in the query (before PostgreSQL lowercases them).

    Handles: bare col, table.col, func() AS alias, expr AS alias.
    Returns [] if parsing fails (read_sql falls back to PG column names).
    """
    # Normalize whitespace so multi-line SQL becomes one line
    s = _re.sub(r'\s+', ' ', sql.strip())
    # Match the outermost SELECT ... FROM block (non-greedy, case-insensitive)
    m = _re.search(r'(?i)\bSELECT\b\s+(?:DISTINCT\s+)?(.*?)\s+\bFROM\b', s)
    if not m:
        return []
    select_part = m.group(1)

    # Split by top-level commas (depth-aware, respects parentheses)
    parts, depth, buf = [], 0, ""
    for ch in select_part:
        if ch == "(":
            depth += 1; buf += ch
        elif ch == ")":
            depth -= 1; buf += ch
        elif ch == "," and depth == 0:
            parts.append(buf.strip()); buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf.strip())

    cols = []
    for part in parts:
        # Prefer explicit AS alias (quoted or unquoted)
        a = _re.search(r'(?i)\bAS\s+"?(\w+)"?\s*$', part)
        if a:
            cols.append(a.group(1))
        else:
            # Bare column reference: last segment after dot, first token only
            bare = part.split(".")[-1].strip().strip('"')
            bare = _re.split(r'[\s(]', bare)[0]
            cols.append(bare)
    return cols


# ─────────────────────────────────────────────────────────────────────────────
# PROXY — API COMPATIBLE sqlite3
# ─────────────────────────────────────────────────────────────────────────────

class _CursorProxy:
    """
    Wrapper autour d'un cursor psycopg2 pour compatibilité pandas.read_sql_query.
    Convertit automatiquement les placeholders ? → %s.
    """
    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql: str, params=None):
        self._cur.execute(sql.replace("?", "%s"), params or ())
        return self

    def fetchall(self):     return self._cur.fetchall()
    def fetchone(self):     return self._cur.fetchone()
    def fetchmany(self, n): return self._cur.fetchmany(n)
    def close(self):        self._cur.close()

    @property
    def description(self): return self._cur.description
    @property
    def rowcount(self):    return self._cur.rowcount
    @property
    def lastrowid(self):   return None  # use RETURNING id


class _ConnProxy:
    """
    Wrapper psycopg2 → sqlite3-like API.
    · conn.execute(sql, params)  — retourne un cursor psycopg2 DictCursor
    · conn.executemany(sql, seq) — batch inserts
    · Convertit automatiquement les placeholders ? → %s (legacy compat)
    · cursor() exposé pour pandas.read_sql
    """

    def __init__(self, raw_conn: psycopg2.extensions.connection):
        self._c = raw_conn

    # ── DBAPI2 compat pour pandas.read_sql ───────────────────────────────────
    def cursor(self, cursor_factory=None):
        if cursor_factory is None:
            cursor_factory = psycopg2.extras.DictCursor
        return _CursorProxy(self._c.cursor(cursor_factory=cursor_factory))

    @property
    def _raw(self):
        """Connexion psycopg2 brute — pour pandas.read_sql(sql, conn._raw)."""
        return self._c

    # ── execute ───────────────────────────────────────────────────────────────
    def execute(self, sql: str, params=None) -> psycopg2.extensions.cursor:
        pg_sql = sql.replace("?", "%s")
        cur = self._c.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(pg_sql, params or ())
        return cur

    # ── executemany ───────────────────────────────────────────────────────────
    def executemany(self, sql: str, seq) -> psycopg2.extensions.cursor:
        pg_sql = sql.replace("?", "%s")
        cur = self._c.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.executemany(pg_sql, seq)
        return cur

    # ── read_sql : remplace pd.read_sql_query — contourne les proxy DBAPI2 ───
    def read_sql(self, sql: str, params=None) -> "pd.DataFrame":
        """
        Exécute une SELECT et retourne un DataFrame pandas.
        · Convertit ? → %s pour psycopg2.
        · Restaure la casse originale des colonnes depuis la chaîne SQL
          (PostgreSQL renvoie tout en minuscules pour les identifiants non quotés).
        """
        import pandas as pd
        pg_sql = sql.replace("?", "%s")
        # Extract intended column names BEFORE PostgreSQL lowercases them
        intended = _extract_col_names(sql)
        cur = self._c.cursor()
        cur.execute(pg_sql, params or ())
        rows = cur.fetchall()
        pg_cols = [d[0] for d in cur.description] if cur.description else []
        cur.close()
        # Use intended names if count matches, else fall back to PG names
        cols = intended if (intended and len(intended) == len(pg_cols)) else pg_cols
        return pd.DataFrame(rows, columns=cols)


# ─────────────────────────────────────────────────────────────────────────────
# GESTIONNAIRE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

class DatabaseManager:
    """
    Gestionnaire centralisé PostgreSQL pour Finance SaaS.

    Usage :
        db = DatabaseManager("postgresql://user:pass@host:5432/db?sslmode=require")
        db.initialiser_schema()
    """

    def __init__(self, database_url: str):
        self.database_url = database_url
        # Test connection at startup to fail fast with a clear error
        try:
            test = psycopg2.connect(database_url)
            test.close()
        except Exception as e:
            logger.error(f"❌ Connexion PostgreSQL échouée : {e}")
            raise
        logger.info("DatabaseManager PostgreSQL initialisé")

    # ─────────────────────────────────────────────────────────────────────────
    # CONNEXION
    # ─────────────────────────────────────────────────────────────────────────

    @contextmanager
    def connexion(self):
        """
        Context manager — ouvre une connexion fraîche, commit ou rollback, puis ferme.
        Compatible avec le transaction pooler Supabase.
        """
        conn = psycopg2.connect(self.database_url)
        proxy = _ConnProxy(conn)
        try:
            yield proxy
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction rollback : {e}")
            raise
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # SCHÉMA — TABLES
    # ─────────────────────────────────────────────────────────────────────────

    def initialiser_schema(self) -> None:
        """Crée toutes les tables si absentes. Idempotent."""
        with self.connexion() as conn:

            # ── UTILISATEURS (auth, partagée) ─────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS UTILISATEURS (
                    id            SERIAL PRIMARY KEY,
                    username      TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    date_creation TIMESTAMP DEFAULT NOW()
                )
            """)
            logger.info("✅ UTILISATEURS")

            # ── CATEGORIES (référentiel partagé, sans user_id) ────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS CATEGORIES (
                    Categorie      TEXT NOT NULL,
                    Sous_Categorie TEXT NOT NULL,
                    Plafond        NUMERIC DEFAULT 0.0,
                    PRIMARY KEY (Categorie, Sous_Categorie)
                )
            """)
            logger.info("✅ CATEGORIES")

            # ── REFERENTIEL (référentiel partagé) ─────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS REFERENTIEL (
                    Categorie      TEXT NOT NULL,
                    Sous_Categorie TEXT NOT NULL,
                    Sens           TEXT NOT NULL CHECK (Sens IN ('IN','OUT')),
                    Frequence      TEXT DEFAULT '',
                    Statut         TEXT DEFAULT 'ACTIF',
                    Compteur_N     INTEGER DEFAULT 0,
                    Montant_Cumule NUMERIC DEFAULT 0.0,
                    PRIMARY KEY (Categorie, Sous_Categorie)
                )
            """)
            logger.info("✅ REFERENTIEL")

            # ── DICO_MATCHING (dictionnaire partagé) ──────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS DICO_MATCHING (
                    id                   SERIAL PRIMARY KEY,
                    Sens                 TEXT NOT NULL CHECK (Sens IN ('IN','OUT')),
                    Mot_Cle              TEXT NOT NULL,
                    Categorie_Cible      TEXT NOT NULL,
                    Sous_Categorie_Cible TEXT DEFAULT '',
                    UNIQUE (Sens, Mot_Cle)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dico_mot_cle
                ON DICO_MATCHING(Mot_Cle)
            """)
            logger.info("✅ DICO_MATCHING")

            # ── TRANSACTIONS (par utilisateur) ────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS TRANSACTIONS (
                    ID_Unique      TEXT NOT NULL,
                    Date_Saisie    TEXT NOT NULL,
                    Date_Valeur    TEXT NOT NULL,
                    Libelle        TEXT NOT NULL,
                    Montant        NUMERIC NOT NULL,
                    Sens           TEXT NOT NULL CHECK (Sens IN ('IN','OUT')),
                    Categorie      TEXT DEFAULT '',
                    Sous_Categorie TEXT DEFAULT '',
                    Statut         TEXT NOT NULL DEFAULT 'A_CLASSIFIER'
                                   CHECK (Statut IN ('A_CLASSIFIER','VALIDE')),
                    Source         TEXT NOT NULL DEFAULT 'SAISIE'
                                   CHECK (Source IN ('SAISIE','IMPORT','ONBOARDING')),
                    user_id        INTEGER NOT NULL REFERENCES UTILISATEURS(id) ON DELETE CASCADE,
                    PRIMARY KEY (ID_Unique, user_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_transactions_user
                ON TRANSACTIONS(user_id, Date_Valeur DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_transactions_statut
                ON TRANSACTIONS(user_id, Statut)
            """)
            logger.info("✅ TRANSACTIONS")

            # ── REGLES_UTILISATEUR (par utilisateur) ──────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS REGLES_UTILISATEUR (
                    id              SERIAL PRIMARY KEY,
                    Sens            TEXT NOT NULL CHECK (Sens IN ('IN','OUT')),
                    Mot_Cle         TEXT NOT NULL,
                    Montant         NUMERIC,
                    Categorie_Cible TEXT NOT NULL,
                    Date_Creation   TIMESTAMP DEFAULT NOW(),
                    user_id         INTEGER NOT NULL REFERENCES UTILISATEURS(id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_regles_user
                ON REGLES_UTILISATEUR(user_id, Sens, Mot_Cle)
            """)
            logger.info("✅ REGLES_UTILISATEUR")

            # ── A_CLASSIFIER (par utilisateur) ────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS A_CLASSIFIER (
                    id                  SERIAL PRIMARY KEY,
                    Mot_Cle_Inconnu     TEXT NOT NULL,
                    Sens                TEXT NOT NULL CHECK (Sens IN ('IN','OUT')),
                    Categorie_Auto      TEXT NOT NULL,
                    Sous_Categorie_Auto TEXT NOT NULL,
                    Nb_Occurrences      INTEGER DEFAULT 1,
                    Date_Ajout          TIMESTAMP DEFAULT NOW(),
                    Enrichi             INTEGER DEFAULT 0,
                    user_id             INTEGER NOT NULL REFERENCES UTILISATEURS(id) ON DELETE CASCADE,
                    UNIQUE (Mot_Cle_Inconnu, Sens, user_id)
                )
            """)
            logger.info("✅ A_CLASSIFIER")

            # ── EPARGNE_HISTO (par utilisateur) ───────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS EPARGNE_HISTO (
                    Mois           TEXT NOT NULL,
                    Montant_Vise   NUMERIC DEFAULT 0.0,
                    Montant_Reel   NUMERIC DEFAULT 0.0,
                    Evolution_DH   NUMERIC DEFAULT 0.0,
                    Cumul_Total    NUMERIC DEFAULT 0.0,
                    user_id        INTEGER NOT NULL REFERENCES UTILISATEURS(id) ON DELETE CASCADE,
                    PRIMARY KEY (Mois, user_id)
                )
            """)
            logger.info("✅ EPARGNE_HISTO")

            # ── PREFERENCES (par utilisateur) ────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS PREFERENCES (
                    Cle     TEXT NOT NULL,
                    Valeur  TEXT NOT NULL,
                    Modifie TIMESTAMP DEFAULT NOW(),
                    user_id INTEGER NOT NULL REFERENCES UTILISATEURS(id) ON DELETE CASCADE,
                    PRIMARY KEY (Cle, user_id)
                )
            """)
            logger.info("✅ PREFERENCES")

            # ── OBJECTIFS (par utilisateur) ───────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS OBJECTIFS (
                    id             SERIAL PRIMARY KEY,
                    Nom            TEXT NOT NULL,
                    Type           TEXT NOT NULL DEFAULT 'EPARGNE'
                                   CHECK (Type IN ('EPARGNE','DEPENSE')),
                    Montant_Cible  NUMERIC NOT NULL,
                    Montant_Actuel NUMERIC DEFAULT 0.0,
                    Date_Cible     TEXT NOT NULL,
                    Date_Creation  TIMESTAMP DEFAULT NOW(),
                    Statut         TEXT DEFAULT 'EN_COURS'
                                   CHECK (Statut IN ('EN_COURS','ATTEINT','ABANDONNE')),
                    Categorie      TEXT DEFAULT '',
                    Icone          TEXT DEFAULT '🎯',
                    Couleur        TEXT DEFAULT '#06b6d4',
                    user_id        INTEGER NOT NULL REFERENCES UTILISATEURS(id) ON DELETE CASCADE
                )
            """)
            logger.info("✅ OBJECTIFS")

            # ── BUDGETS_MENSUELS (par utilisateur) ────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS BUDGETS_MENSUELS (
                    Mois           TEXT NOT NULL,
                    Categorie      TEXT NOT NULL,
                    Sous_Categorie TEXT NOT NULL,
                    Plafond        NUMERIC NOT NULL,
                    user_id        INTEGER NOT NULL REFERENCES UTILISATEURS(id) ON DELETE CASCADE,
                    PRIMARY KEY (Mois, Categorie, Sous_Categorie, user_id)
                )
            """)
            logger.info("✅ BUDGETS_MENSUELS")

            # ── JOURNAL (par utilisateur) ─────────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS JOURNAL (
                    id             SERIAL PRIMARY KEY,
                    Date_Entree    TEXT NOT NULL,
                    Note           TEXT NOT NULL,
                    Tags           TEXT DEFAULT '',
                    Humeur         TEXT DEFAULT '',
                    ID_Transaction TEXT DEFAULT '',
                    Date_Creation  TIMESTAMP DEFAULT NOW(),
                    user_id        INTEGER NOT NULL REFERENCES UTILISATEURS(id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_journal_user_date
                ON JOURNAL(user_id, Date_Entree DESC)
            """)
            logger.info("✅ JOURNAL")

            # ── AUDIT_LOG (par utilisateur) ───────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS AUDIT_LOG (
                    id         SERIAL PRIMARY KEY,
                    Timestamp  TIMESTAMP DEFAULT NOW(),
                    Role       TEXT NOT NULL,
                    Action     TEXT NOT NULL,
                    Input_Raw  TEXT,
                    Output_Raw TEXT,
                    Methode    TEXT,
                    Score      NUMERIC,
                    Statut     TEXT DEFAULT 'OK'
                               CHECK (Statut IN ('OK','WARN','ERREUR','BLOQUE')),
                    user_id    INTEGER REFERENCES UTILISATEURS(id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_user_role
                ON AUDIT_LOG(user_id, Role, Timestamp DESC)
            """)
            logger.info("✅ AUDIT_LOG")

            # ── SNAPSHOTS (par utilisateur) ───────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS SNAPSHOTS (
                    Cle       TEXT NOT NULL,
                    Timestamp TEXT NOT NULL,
                    Payload   TEXT NOT NULL,
                    Nb_Trans  INTEGER DEFAULT 0,
                    user_id   INTEGER NOT NULL REFERENCES UTILISATEURS(id) ON DELETE CASCADE,
                    PRIMARY KEY (Cle, user_id)
                )
            """)
            logger.info("✅ SNAPSHOTS")

        logger.info("🎉 Schéma PostgreSQL initialisé")

    # ─────────────────────────────────────────────────────────────────────────
    # AUTHENTIFICATION
    # ─────────────────────────────────────────────────────────────────────────

    def creer_utilisateur(self, username: str, password_hash: str) -> Optional[int]:
        """
        Crée un nouvel utilisateur.
        Retourne l'id ou None si username déjà pris.
        """
        try:
            with self.connexion() as conn:
                cur = conn.execute(
                    """INSERT INTO UTILISATEURS (username, password_hash)
                       VALUES (%s, %s) RETURNING id""",
                    (username.strip().lower(), password_hash)
                )
                user_id = cur.fetchone()[0]
            self._inserer_preferences_defaut(user_id)
            logger.info(f"Utilisateur créé : '{username}' (id={user_id})")
            return user_id
        except psycopg2.errors.UniqueViolation:
            logger.warning(f"Username déjà pris : '{username}'")
            return None

    def get_utilisateur(self, username: str) -> Optional[Dict]:
        """Retourne {id, username, password_hash} ou None."""
        with self.connexion() as conn:
            cur = conn.execute(
                "SELECT id, username, password_hash FROM UTILISATEURS WHERE username = %s",
                (username.strip().lower(),)
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def _inserer_preferences_defaut(self, user_id: int) -> None:
        """Insère les préférences par défaut pour un nouvel utilisateur."""
        defaults = [
            ("coach_identite",  COACH_IDENTITE_DEFAUT),
            ("needs_pct",       str(int(NEEDS_PCT_DEFAUT))),
            ("wants_pct",       str(int(WANTS_PCT_DEFAUT))),
            ("savings_pct",     str(int(SAVINGS_PCT_DEFAUT))),
            ("devise",          DEVISE),
            ("seuil_alerte",    str(int(SEUIL_ALERTE_DEFAUT))),
        ]
        with self.connexion() as conn:
            for cle, valeur in defaults:
                conn.execute(
                    """INSERT INTO PREFERENCES (Cle, Valeur, user_id)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (Cle, user_id) DO NOTHING""",
                    (cle, valeur, user_id)
                )

    # ─────────────────────────────────────────────────────────────────────────
    # PREFERENCES
    # ─────────────────────────────────────────────────────────────────────────

    def get_preference(self, cle: str, user_id: int, defaut: Optional[str] = None) -> Optional[str]:
        with self.connexion() as conn:
            cur = conn.execute(
                "SELECT Valeur FROM PREFERENCES WHERE Cle = %s AND user_id = %s",
                (cle, user_id)
            )
            row = cur.fetchone()
        return str(row[0]) if row else defaut

    def set_preference(self, cle: str, valeur: str, user_id: int) -> None:
        with self.connexion() as conn:
            conn.execute(
                """INSERT INTO PREFERENCES (Cle, Valeur, user_id, Modifie)
                   VALUES (%s, %s, %s, NOW())
                   ON CONFLICT (Cle, user_id) DO UPDATE
                   SET Valeur = EXCLUDED.Valeur, Modifie = NOW()""",
                (cle, str(valeur), user_id)
            )

    def get_toutes_preferences(self, user_id: int) -> Dict[str, str]:
        with self.connexion() as conn:
            cur = conn.execute(
                "SELECT Cle, Valeur FROM PREFERENCES WHERE user_id = %s", (user_id,)
            )
            rows = cur.fetchall()
        return {r[0]: r[1] for r in rows}

    # ─────────────────────────────────────────────────────────────────────────
    # SEEDING — DONNÉES PARTAGÉES (sans user_id)
    # ─────────────────────────────────────────────────────────────────────────

    def seed_categories(self, categories: List[Dict[str, Any]]) -> int:
        if not categories:
            return 0
        with self.connexion() as conn:
            nb = 0
            for cat in categories:
                conn.execute(
                    """INSERT INTO CATEGORIES (Categorie, Sous_Categorie, Plafond)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (Categorie, Sous_Categorie) DO NOTHING""",
                    (cat.get("Categorie",""), cat.get("Sous_Categorie",""),
                     float(cat.get("Plafond",0.0) or 0.0))
                )
                nb += 1
        logger.info(f"CATEGORIES — {nb} entrée(s) traitées")
        return nb

    def seed_referentiel(self, df) -> int:
        if df.empty:
            return 0
        df = df.copy()
        df.columns = [c.strip() for c in df.columns]
        df = df.fillna(0)
        nb_ref = 0
        with self.connexion() as conn:
            for _, row in df.iterrows():
                try:
                    conn.execute(
                        """INSERT INTO REFERENTIEL
                           (Categorie, Sous_Categorie, Sens, Frequence, Statut, Compteur_N, Montant_Cumule)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (Categorie, Sous_Categorie) DO NOTHING""",
                        (str(row.get("Categorie","")).strip(),
                         str(row.get("Sous_Categorie","")).strip(),
                         str(row.get("Sens","OUT")).strip().upper(),
                         str(row.get("Frequence","")).strip(),
                         str(row.get("Statut","ACTIF")).strip(),
                         int(row.get("Compteur_N",0) or 0),
                         float(row.get("Montant_Cumule",0.0) or 0.0))
                    )
                    conn.execute(
                        """INSERT INTO CATEGORIES (Categorie, Sous_Categorie, Plafond)
                           VALUES (%s,%s,0.0) ON CONFLICT DO NOTHING""",
                        (str(row.get("Categorie","")).strip(),
                         str(row.get("Sous_Categorie","")).strip())
                    )
                    nb_ref += 1
                except Exception:
                    continue
        logger.info(f"REFERENTIEL — {nb_ref} entrée(s)")
        return nb_ref

    def seed_dico_matching(self, df) -> int:
        if df.empty:
            return 0
        df = df.copy()
        df.columns = [c.strip() for c in df.columns]
        nb = 0
        with self.connexion() as conn:
            for _, row in df.iterrows():
                try:
                    conn.execute(
                        """INSERT INTO DICO_MATCHING
                           (Sens, Mot_Cle, Categorie_Cible, Sous_Categorie_Cible)
                           VALUES (%s,%s,%s,%s)
                           ON CONFLICT (Sens, Mot_Cle) DO NOTHING""",
                        (str(row.get("Sens","OUT")).strip().upper(),
                         str(row.get("Mot_Cle","")).strip(),
                         str(row.get("Categorie_Cible","")).strip(),
                         str(row.get("Sous_Categorie_Cible","")).strip())
                    )
                    nb += 1
                except Exception:
                    continue
        logger.info(f"DICO_MATCHING — {nb} mot(s)-clé(s)")
        return nb

    # ─────────────────────────────────────────────────────────────────────────
    # TRANSACTIONS
    # ─────────────────────────────────────────────────────────────────────────

    def enregistrer_mot_cle_inconnu(
        self, mot_cle: str, sens: str,
        categorie_auto: str, sous_categorie_auto: str, user_id: int
    ) -> None:
        with self.connexion() as conn:
            conn.execute(
                """INSERT INTO A_CLASSIFIER
                   (Mot_Cle_Inconnu, Sens, Categorie_Auto, Sous_Categorie_Auto, Nb_Occurrences, user_id)
                   VALUES (%s,%s,%s,%s,1,%s)
                   ON CONFLICT (Mot_Cle_Inconnu, Sens, user_id) DO UPDATE
                   SET Nb_Occurrences = A_CLASSIFIER.Nb_Occurrences + 1""",
                (mot_cle.strip(), sens.strip().upper(),
                 categorie_auto.strip(), sous_categorie_auto.strip(), user_id)
            )

    def importer_transactions_df(self, df, user_id: int) -> int:
        if df.empty:
            return 0
        df = df.copy()
        if "Mot_Cle" in df.columns and "Libelle" not in df.columns:
            df.rename(columns={"Mot_Cle": "Libelle"}, inplace=True)
        if "Sens" not in df.columns:
            df["Sens"] = df["Montant"].apply(lambda m: "IN" if m > 0 else "OUT")
        nb = 0
        with self.connexion() as conn:
            for _, row in df.iterrows():
                try:
                    conn.execute(
                        """INSERT INTO TRANSACTIONS
                           (ID_Unique, Date_Saisie, Date_Valeur, Libelle, Montant,
                            Sens, Categorie, Sous_Categorie, Statut, user_id)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (ID_Unique, user_id) DO NOTHING""",
                        (str(row.get("ID_Unique","")),
                         str(row.get("Date_Saisie","")),
                         str(row.get("Date_Valeur","")),
                         str(row.get("Libelle","")),
                         float(row.get("Montant",0)),
                         str(row.get("Sens","OUT")).upper(),
                         str(row.get("Categorie","")),
                         str(row.get("Sous_Categorie","")),
                         STATUT_A_CLASSIFIER,
                         user_id)
                    )
                    nb += 1
                except Exception:
                    continue
        logger.info(f"TRANSACTIONS — {nb} ligne(s) importées pour user_id={user_id}")
        return nb

    # ─────────────────────────────────────────────────────────────────────────
    # OBJECTIFS
    # ─────────────────────────────────────────────────────────────────────────

    def creer_objectif(self, nom: str, montant_cible: float,
                       date_cible: str, user_id: int) -> int:
        with self.connexion() as conn:
            cur = conn.execute(
                """INSERT INTO OBJECTIFS (Nom, Montant_Cible, Date_Cible, user_id)
                   VALUES (%s,%s,%s,%s) RETURNING id""",
                (nom.strip(), round(float(montant_cible),2), date_cible.strip(), user_id)
            )
            return cur.fetchone()[0]

    def creer_objectif_v2(self, nom: str, type_obj: str, montant_cible: float,
                          date_cible: str, user_id: int,
                          categorie: str = "", icone: str = "🎯",
                          couleur: str = "#06b6d4") -> int:
        with self.connexion() as conn:
            cur = conn.execute(
                """INSERT INTO OBJECTIFS
                   (Nom, Type, Montant_Cible, Date_Cible, Categorie, Icone, Couleur, user_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (nom.strip(), type_obj, round(float(montant_cible),2),
                 date_cible.strip(), categorie.strip(), icone.strip(),
                 couleur.strip(), user_id)
            )
            return cur.fetchone()[0]

    def maj_objectif_actuel(self, objectif_id: int, montant_actuel: float,
                            user_id: int) -> None:
        with self.connexion() as conn:
            cur = conn.execute(
                "SELECT Montant_Cible FROM OBJECTIFS WHERE id=%s AND user_id=%s",
                (objectif_id, user_id)
            )
            row = cur.fetchone()
            if not row:
                return
            cible  = float(row[0])
            actuel = round(float(montant_actuel), 2)
            statut = "ATTEINT" if actuel >= cible else "EN_COURS"
            conn.execute(
                "UPDATE OBJECTIFS SET Montant_Actuel=%s, Statut=%s WHERE id=%s AND user_id=%s",
                (actuel, statut, objectif_id, user_id)
            )

    def get_objectifs(self, user_id: int, statut: Optional[str] = None) -> List[Dict]:
        with self.connexion() as conn:
            if statut:
                cur = conn.execute(
                    "SELECT * FROM OBJECTIFS WHERE Statut=%s AND user_id=%s ORDER BY Date_Cible",
                    (statut, user_id)
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM OBJECTIFS WHERE user_id=%s ORDER BY Statut, Date_Cible",
                    (user_id,)
                )
            rows = cur.fetchall()
        return [_canon_dict(r) for r in rows]

    def get_objectifs_v2(self, user_id: int, type_obj: Optional[str] = None) -> List[Dict]:
        with self.connexion() as conn:
            if type_obj:
                cur = conn.execute(
                    "SELECT * FROM OBJECTIFS WHERE Type=%s AND Statut!='ABANDONNE' AND user_id=%s ORDER BY Date_Cible",
                    (type_obj, user_id)
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM OBJECTIFS WHERE Statut!='ABANDONNE' AND user_id=%s ORDER BY Type, Date_Cible",
                    (user_id,)
                )
            rows = cur.fetchall()
        return [_canon_dict(r) for r in rows]

    def abandonner_objectif(self, objectif_id: int, user_id: int) -> None:
        with self.connexion() as conn:
            conn.execute(
                "UPDATE OBJECTIFS SET Statut='ABANDONNE' WHERE id=%s AND user_id=%s",
                (objectif_id, user_id)
            )

    def supprimer_objectif(self, objectif_id: int, user_id: int) -> None:
        with self.connexion() as conn:
            conn.execute(
                "DELETE FROM OBJECTIFS WHERE id=%s AND user_id=%s",
                (objectif_id, user_id)
            )

    # ─────────────────────────────────────────────────────────────────────────
    # BUDGETS MENSUELS
    # ─────────────────────────────────────────────────────────────────────────

    def set_budget_mensuel(self, mois: str, categorie: str, sous_categorie: str,
                           plafond: float, user_id: int) -> None:
        with self.connexion() as conn:
            conn.execute(
                """INSERT INTO BUDGETS_MENSUELS (Mois, Categorie, Sous_Categorie, Plafond, user_id)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (Mois, Categorie, Sous_Categorie, user_id)
                   DO UPDATE SET Plafond = EXCLUDED.Plafond""",
                (mois.strip(), categorie.strip(), sous_categorie.strip(),
                 round(float(plafond),2), user_id)
            )

    def get_plafond_effectif(self, mois: str, categorie: str,
                              sous_categorie: str, user_id: int) -> float:
        with self.connexion() as conn:
            row_m = conn.execute(
                """SELECT Plafond FROM BUDGETS_MENSUELS
                   WHERE Mois=%s AND Categorie=%s AND Sous_Categorie=%s AND user_id=%s""",
                (mois, categorie, sous_categorie, user_id)
            ).fetchone()
            if row_m:
                return float(row_m[0])
            row_c = conn.execute(
                "SELECT Plafond FROM CATEGORIES WHERE Categorie=%s AND Sous_Categorie=%s",
                (categorie, sous_categorie)
            ).fetchone()
        return float(row_c[0]) if row_c else 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # JOURNAL
    # ─────────────────────────────────────────────────────────────────────────

    def ajouter_note_journal(self, date_entree: str, note: str, user_id: int,
                              tags: str = "", humeur: str = "",
                              id_transaction: str = "") -> int:
        with self.connexion() as conn:
            cur = conn.execute(
                """INSERT INTO JOURNAL (Date_Entree, Note, Tags, Humeur, ID_Transaction, user_id)
                   VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                (date_entree, note.strip(), tags.strip(),
                 humeur.strip(), id_transaction.strip(), user_id)
            )
            return cur.fetchone()[0]

    def get_journal(self, user_id: int, limit: int = 100) -> List[Dict]:
        with self.connexion() as conn:
            cur = conn.execute(
                """SELECT * FROM JOURNAL WHERE user_id=%s
                   ORDER BY Date_Entree DESC, id DESC LIMIT %s""",
                (user_id, limit)
            )
            rows = cur.fetchall()
        return [_canon_dict(r) for r in rows]

    def supprimer_note_journal(self, note_id: int, user_id: int) -> None:
        with self.connexion() as conn:
            conn.execute(
                "DELETE FROM JOURNAL WHERE id=%s AND user_id=%s",
                (note_id, user_id)
            )

    # ─────────────────────────────────────────────────────────────────────────
    # PLAFONDS CATÉGORIES (partagés)
    # ─────────────────────────────────────────────────────────────────────────

    def get_plafonds_categories(self) -> List[Dict]:
        with self.connexion() as conn:
            cur = conn.execute(
                """SELECT c.Categorie, c.Sous_Categorie, c.Plafond
                   FROM CATEGORIES c
                   JOIN REFERENTIEL r ON c.Categorie=r.Categorie AND c.Sous_Categorie=r.Sous_Categorie
                   WHERE r.Sens='OUT'
                   ORDER BY c.Categorie, c.Sous_Categorie"""
            )
            rows = cur.fetchall()
        # Postgres lowercases unquoted identifiers; rebuild dicts with the
        # canonical casing that views expect.
        return [
            {"Categorie": r[0], "Sous_Categorie": r[1], "Plafond": r[2]}
            for r in rows
        ]

    def set_plafond_categorie(self, categorie: str, sous_categorie: str,
                               plafond: float) -> None:
        with self.connexion() as conn:
            conn.execute(
                "UPDATE CATEGORIES SET Plafond=%s WHERE Categorie=%s AND Sous_Categorie=%s",
                (round(float(plafond),2), categorie, sous_categorie)
            )

    # ─────────────────────────────────────────────────────────────────────────
    # STATS
    # ─────────────────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, int]:
        with self.connexion() as conn:
            nb_cat   = conn.execute("SELECT COUNT(*) FROM CATEGORIES").fetchone()[0]
            nb_dico  = conn.execute("SELECT COUNT(*) FROM DICO_MATCHING").fetchone()[0]
            nb_trans = conn.execute("SELECT COUNT(*) FROM TRANSACTIONS").fetchone()[0]
            nb_users = conn.execute("SELECT COUNT(*) FROM UTILISATEURS").fetchone()[0]
        return {"categories": nb_cat, "dico": nb_dico,
                "transactions": nb_trans, "utilisateurs": nb_users}
