"""
DB_MANAGER.PY — GESTIONNAIRE POSTGRESQL (Supabase)
====================================================
Migration SQLite → PostgreSQL pour le déploiement cloud.
Version : 2.1 — DICO CRUD, EPARGNE_HISTO, admin methods, audit log.

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
    # DARETS
    "Montant_Mensuel", "Nb_Membres", "Membres_JSON", "Tour_Actuel",
    "Date_Debut", "Notes",
    # EPARGNE_HISTO
    "Montant_Vise", "Montant_Reel", "Evolution_DH", "Cumul_Total",
    # A_CLASSIFIER
    "Mot_Cle_Inconnu", "Categorie_Auto", "Sous_Categorie_Auto",
    "Nb_Occurrences", "Date_Ajout", "Enrichi",
    # REGLES_UTILISATEUR
    "Categorie_Cible", "Sous_Categorie_Cible",
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

    # Pool : évite le handshake TCP + TLS + auth Postgres à chaque requête.
    # Sur Supabase en remote c'est 100-300ms par connexion — multipliez par
    # 10-15 requêtes par page et vous avez les 1-4s de latence que les
    # testeurs ressentent. Le pool réutilise les sockets.
    _POOL_MIN = 1
    _POOL_MAX = 10

    def __init__(self, database_url: str):
        self.database_url = database_url
        try:
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=self._POOL_MIN,
                maxconn=self._POOL_MAX,
                dsn=database_url,
                # TCP keepalives : détecte les connexions fermées côté serveur
                # (Supabase coupe les idles), évite le premier query qui plante.
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=3,
            )
        except Exception as e:
            logger.error(f"❌ Pool PostgreSQL init échouée : {e}")
            raise
        logger.info(
            f"DatabaseManager PostgreSQL initialisé "
            f"(pool {self._POOL_MIN}-{self._POOL_MAX})"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # CONNEXION
    # ─────────────────────────────────────────────────────────────────────────

    @contextmanager
    def connexion(self):
        """
        Context manager — emprunte une connexion au pool, commit/rollback, rend.

        · Sur succès  : putconn(conn)           → remis dans le pool
        · Sur erreur  : putconn(conn, close=1)  → détruit (peut être corrompu)
        """
        conn = self._pool.getconn()
        proxy = _ConnProxy(conn)
        broken = False
        try:
            yield proxy
            conn.commit()
        except Exception as e:
            broken = True
            try:
                conn.rollback()
            except Exception:
                pass
            logger.error(f"Transaction rollback : {e}")
            raise
        finally:
            try:
                self._pool.putconn(conn, close=broken)
            except Exception:
                logger.exception("putconn failed")

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

            # ── DARETS placeholder (actual creation in _ensure_darets below) ──
            logger.debug("DARETS creation deferred to _ensure_darets()")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS DARETS (
                    id              SERIAL PRIMARY KEY,
                    Nom             TEXT NOT NULL,
                    Montant_Mensuel NUMERIC NOT NULL,
                    Nb_Membres      INTEGER NOT NULL,
                    Membres_JSON    TEXT NOT NULL DEFAULT '[]',
                    Tour_Actuel     INTEGER DEFAULT 0,
                    Date_Debut      TEXT NOT NULL,
                    Statut          TEXT DEFAULT 'ACTIF',
                    Notes           TEXT DEFAULT '',
                    user_id         INTEGER NOT NULL REFERENCES UTILISATEURS(id) ON DELETE CASCADE
                )
            """)
            logger.info("✅ DARETS")

        logger.info("🎉 Schéma PostgreSQL initialisé")
        self._ensure_darets()
        self._ensure_transaction_columns()
        self.ensure_regles_sous_categorie()
        self._ensure_admin_column()
        self._ensure_profile_columns()
        self._ensure_daret_v2_columns()
        self._auto_seed_dico()
        self._purger_referentiel_obsolete()

    def _ensure_transaction_columns(self) -> None:
        """Add Tags and Contact columns to TRANSACTIONS if they don't exist yet.
        Production DBs created before these columns were added need this."""
        try:
            with self.connexion() as conn:
                conn.execute("""
                    ALTER TABLE TRANSACTIONS
                        ADD COLUMN IF NOT EXISTS Tags    TEXT DEFAULT '',
                        ADD COLUMN IF NOT EXISTS Contact TEXT DEFAULT ''
                """)
            logger.info("✅ TRANSACTIONS.Tags/Contact (ensure)")
        except Exception:
            logger.exception("_ensure_transaction_columns failed")

    def _ensure_darets(self) -> None:
        """Create DARETS table if it doesn't exist — runs in its own transaction
        so it works even when the DB was initialised before this table was added."""
        try:
            with self.connexion() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS DARETS (
                        id              SERIAL PRIMARY KEY,
                        Nom             TEXT NOT NULL,
                        Montant_Mensuel NUMERIC NOT NULL,
                        Nb_Membres      INTEGER NOT NULL,
                        Membres_JSON    TEXT,
                        Tour_Actuel     INTEGER DEFAULT 0,
                        Date_Debut      TEXT,
                        Statut          TEXT DEFAULT 'ACTIF',
                        Notes           TEXT,
                        user_id         INTEGER NOT NULL
                                        REFERENCES UTILISATEURS(id) ON DELETE CASCADE
                    )
                """)
            logger.info("✅ DARETS (ensure)")
        except Exception:
            logger.exception("_ensure_darets failed")

    def _purger_referentiel_obsolete(self) -> None:
        """Remove rows from REFERENTIEL/CATEGORIES not in the canonical v2 list.
        Uses a single NOT IN bulk-delete — atomic and fast."""
        _VALIDES = [
            ("Revenu","Salaire"), ("Revenu","Freelance & Activités"),
            ("Revenu","Aides & Allocations"), ("Revenu","Prime & Bonus"),
            ("Revenu","Revenu_Autre"),
            ("Logement","Loyer"), ("Logement","Electricité & Eau"),
            ("Logement","Entretien & Maison"), ("Logement","Charges & Taxes"),
            ("Vie Quotidienne","Courses maison"), ("Vie Quotidienne","Alimentation"),
            ("Vie Quotidienne","Snacks & Boissons"),
            ("Vie Quotidienne","Restaurant rapide & fast food"),
            ("Vie Quotidienne","Vie Quotidienne_Autre"),
            ("Transport","Carburant"), ("Transport","Taxi & Transports"),
            ("Transport","Entretien & Réparation"), ("Transport","Assurance & Vignette"),
            ("Transport","Parking & Péage"), ("Transport","Transport_Autre"),
            ("Loisirs","Sorties & Culture"), ("Loisirs","Voyages & Weekend"),
            ("Loisirs","Sport & Bien-être"), ("Loisirs","Cadeaux & Dons"),
            ("Loisirs","Loisirs_Autre"),
            ("Abonnements","Télécom & Internet"), ("Abonnements","Streaming & Apps"),
            ("Abonnements","Club & Gym"), ("Abonnements","Abonnements_autre"),
            ("Santé","Pharmacie"), ("Santé","Médecin & Examens"),
            ("Santé","Optique"), ("Santé","Santé_autre"),
            ("Finances & Crédits","Crédit & Remboursement"),
            ("Finances & Crédits","Épargne & Investissement"),
            ("Finances & Crédits","Frais Bancaires"),
            ("Divers","Administratif"), ("Divers","Amendes"),
            ("Divers","Objets du quotidien"), ("Divers","Divers_Autre"),
            ("Revenu","Autre Revenu"),  # safety alias
        ]
        try:
            with self.connexion() as conn:
                # Build VALUES list for NOT IN check
                placeholders = ",".join(["(%s,%s)"] * len(_VALIDES))
                flat = [v for pair in _VALIDES for v in pair]
                r1 = conn.execute(
                    f"DELETE FROM REFERENTIEL WHERE (Categorie, Sous_Categorie) NOT IN ({placeholders})",
                    flat,
                )
                r2 = conn.execute(
                    f"DELETE FROM CATEGORIES WHERE (Categorie, Sous_Categorie) NOT IN ({placeholders})",
                    flat,
                )
                del1 = r1.rowcount if hasattr(r1, "rowcount") else "?"
                del2 = r2.rowcount if hasattr(r2, "rowcount") else "?"
                if (del1 and del1 != "?") or (del2 and del2 != "?"):
                    logger.info(
                        f"🧹 Purge référentiel — REFERENTIEL: {del1} ligne(s), "
                        f"CATEGORIES: {del2} ligne(s) supprimée(s)"
                    )
        except Exception:
            logger.exception("_purger_referentiel_obsolete failed — DB might have old schema")

    def _auto_seed_dico(self) -> None:
        """Peuple DICO_MATCHING si vide (première exécution)."""
        with self.connexion() as conn:
            nb = conn.execute("SELECT COUNT(*) FROM DICO_MATCHING").fetchone()[0]
            if nb > 0:
                return
        _DICO_SEED = [
            # ── Revenus (IN) ──────────────────────────────────────────────────
            ("IN","SALAIRE",         "Revenu","Salaire"),
            ("IN","VIREMENT SALAIRE","Revenu","Salaire"),
            ("IN","PAIE",            "Revenu","Salaire"),
            ("IN","VENTE",           "Revenu","Freelance & Activités"),
            ("IN","FREELANCE",       "Revenu","Freelance & Activités"),
            ("IN","MISSION",         "Revenu","Freelance & Activités"),
            ("IN","BRICOLAGE",       "Revenu","Freelance & Activités"),
            ("IN","CNSS",            "Revenu","Aides & Allocations"),
            ("IN","ALLOCATION",      "Revenu","Aides & Allocations"),
            ("IN","REMBOURSEMENT",   "Revenu","Aides & Allocations"),
            ("IN","DON",             "Revenu","Aides & Allocations"),
            ("IN","PRIME",           "Revenu","Prime & Bonus"),
            ("IN","BONUS",           "Revenu","Prime & Bonus"),
            ("IN","LOYER RECU",      "Revenu","Revenu_Autre"),
            # ── Logement (OUT) ────────────────────────────────────────────────
            ("OUT","LOYER",          "Logement","Loyer"),
            ("OUT","LYDEC",          "Logement","Electricité & Eau"),
            ("OUT","REDAL",          "Logement","Electricité & Eau"),
            ("OUT","AMENDIS",        "Logement","Electricité & Eau"),
            ("OUT","ONEE",           "Logement","Electricité & Eau"),
            ("OUT","ELECTRICITE",    "Logement","Electricité & Eau"),
            ("OUT","EAU",            "Logement","Electricité & Eau"),
            ("OUT","PLOMBIER",       "Logement","Entretien & Maison"),
            ("OUT","ELECTROMENAGER", "Logement","Entretien & Maison"),
            ("OUT","IKEA",           "Logement","Entretien & Maison"),
            ("OUT","KITEA",          "Logement","Entretien & Maison"),
            ("OUT","SYNDIC",         "Logement","Charges & Taxes"),
            ("OUT","IMPOT",          "Logement","Charges & Taxes"),
            ("OUT","TAXE",           "Logement","Charges & Taxes"),
            # ── Vie Quotidienne (OUT) ─────────────────────────────────────────
            ("OUT","MARJANE",        "Vie Quotidienne","Courses maison"),
            ("OUT","CARREFOUR",      "Vie Quotidienne","Courses maison"),
            ("OUT","ACIMA",          "Vie Quotidienne","Courses maison"),
            ("OUT","ASWAK ASSALAM",  "Vie Quotidienne","Courses maison"),
            ("OUT","BIM",            "Vie Quotidienne","Courses maison"),
            ("OUT","LABEL VIE",      "Vie Quotidienne","Courses maison"),
            ("OUT","ATACADAO",       "Vie Quotidienne","Courses maison"),
            ("OUT","SUPERMARCHE",    "Vie Quotidienne","Courses maison"),
            ("OUT","COURSES",        "Vie Quotidienne","Courses maison"),
            ("OUT","EPICERIE",       "Vie Quotidienne","Courses maison"),
            ("OUT","HANOUT",         "Vie Quotidienne","Courses maison"),
            ("OUT","BOUCHERIE",      "Vie Quotidienne","Alimentation"),
            ("OUT","POULET",         "Vie Quotidienne","Alimentation"),
            ("OUT","VIANDE",         "Vie Quotidienne","Alimentation"),
            ("OUT","POISSON",        "Vie Quotidienne","Alimentation"),
            ("OUT","SOUK",           "Vie Quotidienne","Alimentation"),
            ("OUT","LEGUMES",        "Vie Quotidienne","Alimentation"),
            ("OUT","FRUITS",         "Vie Quotidienne","Alimentation"),
            ("OUT","PRIMEUR",        "Vie Quotidienne","Alimentation"),
            ("OUT","CAFE",           "Vie Quotidienne","Snacks & Boissons"),
            ("OUT","SNACK",          "Vie Quotidienne","Snacks & Boissons"),
            ("OUT","PATISSERIE",     "Vie Quotidienne","Snacks & Boissons"),
            ("OUT","BOULANGERIE",    "Vie Quotidienne","Snacks & Boissons"),
            ("OUT","STARBUCKS",      "Vie Quotidienne","Snacks & Boissons"),
            ("OUT","PAUL",           "Vie Quotidienne","Snacks & Boissons"),
            ("OUT","MCDONALD",       "Vie Quotidienne","Restaurant rapide & fast food"),
            ("OUT","MCDO",           "Vie Quotidienne","Restaurant rapide & fast food"),
            ("OUT","BURGER KING",    "Vie Quotidienne","Restaurant rapide & fast food"),
            ("OUT","KFC",            "Vie Quotidienne","Restaurant rapide & fast food"),
            ("OUT","PIZZA",          "Vie Quotidienne","Restaurant rapide & fast food"),
            ("OUT","TACOS",          "Vie Quotidienne","Restaurant rapide & fast food"),
            ("OUT","RESTAURANT",     "Vie Quotidienne","Restaurant rapide & fast food"),
            ("OUT","RESTO",          "Vie Quotidienne","Restaurant rapide & fast food"),
            ("OUT","LIVRAISON",      "Vie Quotidienne","Restaurant rapide & fast food"),
            ("OUT","GLOVO",          "Vie Quotidienne","Restaurant rapide & fast food"),
            # ── Transport (OUT) ───────────────────────────────────────────────
            ("OUT","ESSENCE",        "Transport","Carburant"),
            ("OUT","GASOIL",         "Transport","Carburant"),
            ("OUT","STATION",        "Transport","Carburant"),
            ("OUT","AFRIQUIA",       "Transport","Carburant"),
            ("OUT","SHELL",          "Transport","Carburant"),
            ("OUT","TOTAL",          "Transport","Carburant"),
            ("OUT","CARBURANT",      "Transport","Carburant"),
            ("OUT","TRAMWAY",        "Transport","Taxi & Transports"),
            ("OUT","TRAM",           "Transport","Taxi & Transports"),
            ("OUT","ALSA",           "Transport","Taxi & Transports"),
            ("OUT","TAXI",           "Transport","Taxi & Transports"),
            ("OUT","UBER",           "Transport","Taxi & Transports"),
            ("OUT","INDRIVER",       "Transport","Taxi & Transports"),
            ("OUT","CAREEM",         "Transport","Taxi & Transports"),
            ("OUT","LAVAGE",         "Transport","Entretien & Réparation"),
            ("OUT","VIDANGE",        "Transport","Entretien & Réparation"),
            ("OUT","MECANICIEN",     "Transport","Entretien & Réparation"),
            ("OUT","GARAGE",         "Transport","Entretien & Réparation"),
            ("OUT","PNEU",           "Transport","Entretien & Réparation"),
            ("OUT","ASSURANCE AUTO", "Transport","Assurance & Vignette"),
            ("OUT","VIGNETTE",       "Transport","Assurance & Vignette"),
            ("OUT","VISITE TECHNIQUE","Transport","Assurance & Vignette"),
            ("OUT","PARKING",        "Transport","Parking & Péage"),
            ("OUT","PEAGE",          "Transport","Parking & Péage"),
            ("OUT","AUTOROUTE",      "Transport","Parking & Péage"),
            # ── Loisirs (OUT) ─────────────────────────────────────────────────
            ("OUT","ZARA",           "Loisirs","Sorties & Culture"),
            ("OUT","H&M",            "Loisirs","Sorties & Culture"),
            ("OUT","DECATHLON",      "Loisirs","Sorties & Culture"),
            ("OUT","SHOPPING",       "Loisirs","Sorties & Culture"),
            ("OUT","VETEMENT",       "Loisirs","Sorties & Culture"),
            ("OUT","CHAUSSURE",      "Loisirs","Sorties & Culture"),
            ("OUT","CINEMA",         "Loisirs","Sorties & Culture"),
            ("OUT","MEGARAMA",       "Loisirs","Sorties & Culture"),
            ("OUT","IMAX",           "Loisirs","Sorties & Culture"),
            ("OUT","LIVRE",          "Loisirs","Sorties & Culture"),
            ("OUT","VOYAGE",         "Loisirs","Voyages & Weekend"),
            ("OUT","HOTEL",          "Loisirs","Voyages & Weekend"),
            ("OUT","RIAD",           "Loisirs","Voyages & Weekend"),
            ("OUT","AIRBNB",         "Loisirs","Voyages & Weekend"),
            ("OUT","RYANAIR",        "Loisirs","Voyages & Weekend"),
            ("OUT","ROYAL AIR MAROC","Loisirs","Voyages & Weekend"),
            ("OUT","ONCF",           "Loisirs","Voyages & Weekend"),
            ("OUT","TRAIN",          "Loisirs","Voyages & Weekend"),
            ("OUT","SPORT",          "Loisirs","Sport & Bien-être"),
            ("OUT","SALLE DE SPORT", "Loisirs","Sport & Bien-être"),
            ("OUT","PISCINE",        "Loisirs","Sport & Bien-être"),
            ("OUT","FOOTBALL",       "Loisirs","Sport & Bien-être"),
            ("OUT","COIFFEUR",       "Loisirs","Sport & Bien-être"),
            ("OUT","BARBIER",        "Loisirs","Sport & Bien-être"),
            ("OUT","HAMMAM",         "Loisirs","Sport & Bien-être"),
            ("OUT","PARFUM",         "Loisirs","Sport & Bien-être"),
            ("OUT","COSMETIQUE",     "Loisirs","Sport & Bien-être"),
            ("OUT","CADEAU",         "Loisirs","Cadeaux & Dons"),
            ("OUT","ANNIVERSAIRE",   "Loisirs","Cadeaux & Dons"),
            ("OUT","MARIAGE",        "Loisirs","Cadeaux & Dons"),
            # ── Abonnements (OUT) ─────────────────────────────────────────────
            ("OUT","MAROC TELECOM",  "Abonnements","Télécom & Internet"),
            ("OUT","INWI",           "Abonnements","Télécom & Internet"),
            ("OUT","ORANGE",         "Abonnements","Télécom & Internet"),
            ("OUT","INTERNET",       "Abonnements","Télécom & Internet"),
            ("OUT","WIFI",           "Abonnements","Télécom & Internet"),
            ("OUT","FORFAIT",        "Abonnements","Télécom & Internet"),
            ("OUT","RECHARGE",       "Abonnements","Télécom & Internet"),
            ("OUT","NETFLIX",        "Abonnements","Streaming & Apps"),
            ("OUT","SPOTIFY",        "Abonnements","Streaming & Apps"),
            ("OUT","YOUTUBE",        "Abonnements","Streaming & Apps"),
            ("OUT","DISNEY",         "Abonnements","Streaming & Apps"),
            ("OUT","APPLE MUSIC",    "Abonnements","Streaming & Apps"),
            ("OUT","CHATGPT",        "Abonnements","Streaming & Apps"),
            ("OUT","CLAUDE",         "Abonnements","Streaming & Apps"),
            ("OUT","GITHUB",         "Abonnements","Streaming & Apps"),
            ("OUT","ADOBE",          "Abonnements","Streaming & Apps"),
            ("OUT","MICROSOFT",      "Abonnements","Streaming & Apps"),
            ("OUT","GOOGLE ONE",     "Abonnements","Streaming & Apps"),
            ("OUT","ICLOUD",         "Abonnements","Streaming & Apps"),
            ("OUT","GYM",            "Abonnements","Club & Gym"),
            ("OUT","FITNESS",        "Abonnements","Club & Gym"),
            ("OUT","CLUB",           "Abonnements","Club & Gym"),
            ("OUT","BANQUE",         "Abonnements","Abonnements_autre"),
            ("OUT","ASSURANCE",      "Abonnements","Abonnements_autre"),
            ("OUT","CIH",            "Abonnements","Abonnements_autre"),
            ("OUT","BMCE",           "Abonnements","Abonnements_autre"),
            ("OUT","ATTIJARIWAFA",   "Abonnements","Abonnements_autre"),
            ("OUT","BANQUE POPULAIRE","Abonnements","Abonnements_autre"),
            # ── Santé (OUT) ───────────────────────────────────────────────────
            ("OUT","PHARMACIE",      "Santé","Pharmacie"),
            ("OUT","MEDICAMENT",     "Santé","Pharmacie"),
            ("OUT","PARAPHARMACIE",  "Santé","Pharmacie"),
            ("OUT","MEDECIN",        "Santé","Médecin & Examens"),
            ("OUT","DOCTEUR",        "Santé","Médecin & Examens"),
            ("OUT","DENTISTE",       "Santé","Médecin & Examens"),
            ("OUT","CLINIQUE",       "Santé","Médecin & Examens"),
            ("OUT","HOPITAL",        "Santé","Médecin & Examens"),
            ("OUT","ANALYSE",        "Santé","Médecin & Examens"),
            ("OUT","RADIO",          "Santé","Médecin & Examens"),
            ("OUT","SCANNER",        "Santé","Médecin & Examens"),
            ("OUT","LABO",           "Santé","Médecin & Examens"),
            ("OUT","LUNETTES",       "Santé","Optique"),
            ("OUT","OPTICIEN",       "Santé","Optique"),
            ("OUT","LENTILLES",      "Santé","Optique"),
            # ── Finances & Crédits (OUT) ──────────────────────────────────────
            ("OUT","CREDIT",         "Finances & Crédits","Crédit & Remboursement"),
            ("OUT","ECHEANCE",       "Finances & Crédits","Crédit & Remboursement"),
            ("OUT","MENSUALITE",     "Finances & Crédits","Crédit & Remboursement"),
            ("OUT","DETTE",          "Finances & Crédits","Crédit & Remboursement"),
            ("OUT","EPARGNE",        "Finances & Crédits","Épargne & Investissement"),
            ("OUT","INVESTISSEMENT", "Finances & Crédits","Épargne & Investissement"),
            ("OUT","FRAIS BANCAIRES","Finances & Crédits","Frais Bancaires"),
            ("OUT","COMMISSION",     "Finances & Crédits","Frais Bancaires"),
            # ── Divers (OUT) ──────────────────────────────────────────────────
            ("OUT","AMENDE",         "Divers","Amendes"),
            ("OUT","CONTRAVENTION",  "Divers","Amendes"),
            ("OUT","TIMBRE",         "Divers","Administratif"),
            ("OUT","NOTAIRE",        "Divers","Administratif"),
            ("OUT","DOSSIER",        "Divers","Administratif"),
            ("OUT","TELEPHONE",      "Divers","Objets du quotidien"),
            ("OUT","SAMSUNG",        "Divers","Objets du quotidien"),
            ("OUT","APPLE",          "Divers","Objets du quotidien"),
            ("OUT","IPHONE",         "Divers","Objets du quotidien"),
        ]
        with self.connexion() as conn:
            for sens, mot, cat, scat in _DICO_SEED:
                conn.execute(
                    """INSERT INTO DICO_MATCHING (Sens, Mot_Cle, Categorie_Cible, Sous_Categorie_Cible)
                       VALUES (%s,%s,%s,%s) ON CONFLICT (Sens, Mot_Cle) DO NOTHING""",
                    (sens, mot, cat, scat),
                )
        logger.info(f"DICO_MATCHING auto-seeded: {len(_DICO_SEED)} keywords")

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
    # DICO_MATCHING — admin CRUD
    # ─────────────────────────────────────────────────────────────────────────

    def get_all_dico(self, search: str = "") -> List[Dict]:
        sql = ("SELECT id, Sens, Mot_Cle, Categorie_Cible, Sous_Categorie_Cible"
               " FROM DICO_MATCHING")
        params: tuple = ()
        if search.strip():
            sql += " WHERE UPPER(Mot_Cle) LIKE %s"
            params = (f"%{search.upper().strip()}%",)
        sql += " ORDER BY Sens, Mot_Cle"
        with self.connexion() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_canon_dict(r) for r in rows]

    def add_dico_entry(self, sens: str, mot_cle: str,
                       categorie: str, sous_categorie: str) -> bool:
        try:
            with self.connexion() as conn:
                conn.execute(
                    """INSERT INTO DICO_MATCHING
                       (Sens, Mot_Cle, Categorie_Cible, Sous_Categorie_Cible)
                       VALUES (%s,%s,%s,%s)
                       ON CONFLICT (Sens, Mot_Cle) DO NOTHING""",
                    (sens.upper(), mot_cle.strip().upper(),
                     categorie.strip(), sous_categorie.strip()),
                )
            return True
        except Exception:
            logger.exception("add_dico_entry failed")
            return False

    def update_dico_entry(self, entry_id: int, categorie: str,
                          sous_categorie: str) -> None:
        with self.connexion() as conn:
            conn.execute(
                """UPDATE DICO_MATCHING
                   SET Categorie_Cible=%s, Sous_Categorie_Cible=%s
                   WHERE id=%s""",
                (categorie.strip(), sous_categorie.strip(), entry_id),
            )

    def delete_dico_entry(self, entry_id: int) -> None:
        with self.connexion() as conn:
            conn.execute("DELETE FROM DICO_MATCHING WHERE id=%s", (entry_id,))

    # ─────────────────────────────────────────────────────────────────────────
    # RÉFÉRENTIEL — admin read
    # ─────────────────────────────────────────────────────────────────────────

    def get_referentiel(self) -> List[Dict]:
        with self.connexion() as conn:
            rows = conn.execute(
                """SELECT Categorie, Sous_Categorie, Sens, Frequence,
                          Compteur_N, Montant_Cumule, Statut
                   FROM REFERENTIEL ORDER BY Categorie, Sous_Categorie"""
            ).fetchall()
        return [_canon_dict(r) for r in rows]

    # ─────────────────────────────────────────────────────────────────────────
    # A_CLASSIFIER — global admin view
    # ─────────────────────────────────────────────────────────────────────────

    def get_audit_log(self, user_id: Optional[int] = None,
                      limit: int = 200) -> List[Dict]:
        """Global audit log for admin. Pass user_id to filter by user."""
        sql = (
            "SELECT a.id, a.Timestamp, a.Role, a.Action, a.Methode,"
            " a.Score, a.Statut, u.username"
            " FROM AUDIT_LOG a"
            " LEFT JOIN UTILISATEURS u ON u.id = a.user_id"
        )
        params: tuple = ()
        if user_id is not None:
            sql += " WHERE a.user_id=%s"
            params = (user_id,)
        sql += " ORDER BY a.Timestamp DESC LIMIT %s"
        params = params + (limit,)
        with self.connexion() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_canon_dict(r) for r in rows]

    def get_all_a_classifier_global(self) -> List[Dict]:
        with self.connexion() as conn:
            rows = conn.execute(
                """SELECT a.Mot_Cle_Inconnu, a.Sens, a.Categorie_Auto,
                          a.Sous_Categorie_Auto, a.Nb_Occurrences,
                          a.Date_Ajout, u.username
                   FROM A_CLASSIFIER a
                   JOIN UTILISATEURS u ON u.id = a.user_id
                   WHERE a.Enrichi = 0
                   ORDER BY a.Nb_Occurrences DESC"""
            ).fetchall()
        return [_canon_dict(r) for r in rows]

    def promote_to_dico(self, mot_cle: str, sens: str,
                        categorie: str, sous_categorie: str) -> None:
        """Promote an A_CLASSIFIER keyword to DICO_MATCHING (shared dict)."""
        self.add_dico_entry(sens, mot_cle, categorie, sous_categorie)
        with self.connexion() as conn:
            conn.execute(
                "UPDATE A_CLASSIFIER SET Enrichi=1"
                " WHERE Mot_Cle_Inconnu=%s AND Sens=%s",
                (mot_cle, sens),
            )

    # ─────────────────────────────────────────────────────────────────────────
    # SPARKLINE — 7-day net flux for hero chart
    # ─────────────────────────────────────────────────────────────────────────

    def get_solde_7j(self, user_id: int) -> list:
        """Return daily net flux (IN-OUT) for last 7 days — sparkline data."""
        from datetime import date, timedelta
        sql = """
            SELECT DATE(Date) as jour,
                   SUM(CASE WHEN Sens='IN' THEN Montant ELSE -Montant END) as flux
            FROM TRANSACTIONS
            WHERE user_id = %s
              AND DATE(Date) >= CURRENT_DATE - INTERVAL '6 days'
            GROUP BY DATE(Date)
            ORDER BY jour ASC
        """
        try:
            with self.connexion() as conn:
                rows = conn.execute(sql, (user_id,)).fetchall()
            today = date.today()
            flux_by_day = {}
            for r in rows:
                jour = r["jour"] if isinstance(r["jour"], date) else date.fromisoformat(str(r["jour"])[:10])
                flux_by_day[jour] = float(r["flux"] or 0)
            return [flux_by_day.get(today - timedelta(days=6 - i), 0.0) for i in range(7)]
        except Exception:
            return []

    def get_solde_mensuel_histo(self, user_id: int, nb_mois: int = 6) -> list:
        """
        Return monthly net flux (revenus - dépenses) for last N months.
        Used to upgrade hero sparkline from 7-day to monthly view.
        Always returns nb_mois entries (0 for empty months), oldest first.
        """
        from datetime import date
        sql = """
            SELECT DATE_TRUNC('month', Date)::date AS mois,
                   SUM(CASE WHEN Sens='IN' THEN Montant ELSE -Montant END) AS flux
            FROM TRANSACTIONS
            WHERE user_id = %s
              AND Date >= (CURRENT_DATE - INTERVAL '%s months')
            GROUP BY DATE_TRUNC('month', Date)
            ORDER BY mois ASC
        """
        try:
            with self.connexion() as conn:
                rows = conn.execute(sql, (user_id, nb_mois)).fetchall()
            flux_by_month = {}
            for r in rows:
                m = r["mois"] if isinstance(r["mois"], date) else date.fromisoformat(str(r["mois"])[:10])
                flux_by_month[(m.year, m.month)] = float(r["flux"] or 0)
            today = date.today()
            result = []
            for i in range(nb_mois):
                offset = nb_mois - 1 - i
                yr = today.year
                mo = today.month - offset
                while mo <= 0:
                    mo += 12
                    yr -= 1
                result.append(flux_by_month.get((yr, mo), 0.0))
            return result
        except Exception:
            return []

    def get_cashflow_mensuel(self, user_id: int, nb_mois: int = 6) -> list:
        """
        Return per-month {mois, revenus, depenses, solde_net} for last N months.
        Used by Tendances page (up/down monthly bars chart + KPI strip).
        Always returns nb_mois entries (0 for empty months), oldest first.
        """
        from datetime import date
        sql = """
            SELECT DATE_TRUNC('month', Date)::date AS mois,
                   SUM(CASE WHEN Sens='IN'  THEN Montant ELSE 0 END) AS revenus,
                   SUM(CASE WHEN Sens='OUT' THEN Montant ELSE 0 END) AS depenses
            FROM TRANSACTIONS
            WHERE user_id = %s
              AND Date >= (CURRENT_DATE - INTERVAL '%s months')
            GROUP BY DATE_TRUNC('month', Date)
            ORDER BY mois ASC
        """
        try:
            with self.connexion() as conn:
                rows = conn.execute(sql, (user_id, nb_mois)).fetchall()
            data_by_month = {}
            for r in rows:
                m = r["mois"] if isinstance(r["mois"], date) else date.fromisoformat(str(r["mois"])[:10])
                rv = float(r["revenus"] or 0)
                dp = float(r["depenses"] or 0)
                data_by_month[(m.year, m.month)] = (rv, dp)
            today = date.today()
            result = []
            for i in range(nb_mois):
                offset = nb_mois - 1 - i
                yr = today.year
                mo = today.month - offset
                while mo <= 0:
                    mo += 12
                    yr -= 1
                rv, dp = data_by_month.get((yr, mo), (0.0, 0.0))
                result.append({
                    "mois":      f"{mo:02d}/{yr}",
                    "year":      yr,
                    "month":     mo,
                    "revenus":   rv,
                    "depenses":  dp,
                    "solde_net": rv - dp,
                })
            return result
        except Exception:
            return []

    # EPARGNE_HISTO — user savings register
    # ─────────────────────────────────────────────────────────────────────────

    def get_epargne_mois(self, user_id: int, mois: str) -> Optional[Dict]:
        with self.connexion() as conn:
            cur = conn.execute(
                "SELECT Mois, Montant_Vise, Montant_Reel, Cumul_Total"
                " FROM EPARGNE_HISTO WHERE user_id=%s AND Mois=%s",
                (user_id, mois),
            )
            row = cur.fetchone()
        return _canon_dict(row) if row else None

    def get_epargne_histo(self, user_id: int, nb_mois: int = 12) -> List[Dict]:
        with self.connexion() as conn:
            rows = conn.execute(
                """SELECT Mois, Montant_Vise, Montant_Reel, Cumul_Total
                   FROM EPARGNE_HISTO
                   WHERE user_id=%s
                   ORDER BY Mois DESC LIMIT %s""",
                (user_id, nb_mois),
            ).fetchall()
        return [_canon_dict(r) for r in rows]

    def get_cumul_epargne(self, user_id: int) -> float:
        """Cumulative savings total — MAX(Cumul_Total) from EPARGNE_HISTO."""
        try:
            with self.connexion() as conn:
                row = conn.execute(
                    "SELECT MAX(Cumul_Total) FROM EPARGNE_HISTO WHERE user_id = %s",
                    (user_id,),
                ).fetchone()
            return float(row[0] or 0) if row else 0.0
        except Exception:
            return 0.0

    def export_user_data(self, user_id: int) -> dict:
        """
        Build a complete export of all user-scoped data as a serializable dict.
        Used for the data-export trust signal in Mon compte.

        Returns: {
            "exported_at": ISO timestamp,
            "user": {username, nom, email, member_since},
            "transactions": [...],
            "objectifs": [...],
            "epargne_histo": [...],
            "darets": [...],
            "preferences": {key: value},
            "budgets_mensuels": [...],
            "journal_humeur": [...],
        }
        """
        from datetime import datetime as _dt

        def _rows(table: str) -> list:
            try:
                with self.connexion() as conn:
                    rows = conn.execute(
                        f"SELECT * FROM {table} WHERE user_id = %s", (user_id,)
                    ).fetchall()
                return [dict(r) if hasattr(r, "keys") else dict(zip(r._fields, r)) for r in rows]
            except Exception:
                return []

        # Stringify dates / datetimes / Decimals for JSON-safety
        def _serialize(obj):
            if isinstance(obj, list):
                return [_serialize(x) for x in obj]
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            if hasattr(obj, "isoformat"):
                return obj.isoformat()
            try:
                from decimal import Decimal
                if isinstance(obj, Decimal):
                    return float(obj)
            except ImportError:
                pass
            return obj

        profile = self.get_user_profile(user_id)
        date_creation = self.get_user_date_creation(user_id)

        # Preferences as a flat key→value dict
        try:
            with self.connexion() as conn:
                pref_rows = conn.execute(
                    "SELECT Cle, Valeur FROM PREFERENCES WHERE user_id = %s",
                    (user_id,),
                ).fetchall()
            prefs = {
                (r["Cle"] if "Cle" in r else r[0]): (r["Valeur"] if "Valeur" in r else r[1])
                for r in pref_rows
            }
        except Exception:
            prefs = {}

        export = {
            "exported_at":      _dt.now().isoformat(timespec="seconds"),
            "schema_version":   1,
            "user": {
                "username":     profile.get("username", ""),
                "nom":          profile.get("nom", ""),
                "email":        profile.get("email", ""),
                "member_since": date_creation.isoformat() if date_creation else None,
            },
            "transactions":     _rows("TRANSACTIONS"),
            "objectifs":        _rows("OBJECTIFS"),
            "epargne_histo":    _rows("EPARGNE_HISTO"),
            "darets":           _rows("DARETS"),
            "preferences":      prefs,
            "budgets_mensuels": _rows("BUDGETS_MENSUELS"),
            "journal_humeur":   _rows("JOURNAL_HUMEUR"),
        }

        return _serialize(export)

    def reset_user_data(self, user_id: int) -> dict:
        """
        DESTRUCTIVE: deletes all user-scoped data, keeps the UTILISATEURS row.
        Also resets date_creation = NOW() so the user appears truly fresh
        (first-week engagement grace applies again, etc.).
        Returns a dict with delete counts per table.

        Used by the admin reset button to start fresh as a new user
        (re-trigger onboarding flow).
        """
        counts = {}
        # Order matters for FK consistency; deletes are scoped per user_id.
        tables = [
            "TRANSACTIONS",
            "PREFERENCES",
            "OBJECTIFS",
            "DARETS",
            "BUDGETS_MENSUELS",
            "EPARGNE_HISTO",
            "A_CLASSIFIER",
            "JOURNAL_HUMEUR",
            "REGLES_UTILISATEUR",
            "AUDIT_LOG",
        ]
        with self.connexion() as conn:
            for table in tables:
                try:
                    cur = conn.execute(
                        f"DELETE FROM {table} WHERE user_id = %s", (user_id,)
                    )
                    counts[table] = cur.rowcount if cur.rowcount is not None else 0
                except Exception as e:
                    # Table might not exist or have user_id column — skip silently
                    counts[table] = f"skipped ({type(e).__name__})"
            # Reset signup date so user appears as fresh (re-enables first-week grace)
            try:
                conn.execute(
                    "UPDATE UTILISATEURS SET date_creation = NOW() WHERE id = %s",
                    (user_id,),
                )
                counts["_date_creation_reset"] = "ok"
            except Exception as e:
                counts["_date_creation_reset"] = f"skipped ({type(e).__name__})"
        return counts

    def delete_user_account(self, user_id: int) -> bool:
        """
        DESTRUCTIVE & IRREVERSIBLE: wipes all user data + deletes the UTILISATEURS row.
        Returns True if the account row was actually removed.

        Used by the 'Supprimer mon compte' flow in Mon compte. Caller is responsible
        for clearing session state and redirecting to login afterwards.
        """
        # First wipe all user-scoped tables (reuses reset_user_data, but skip
        # the date_creation reset since the row will be deleted anyway).
        try:
            self.reset_user_data(user_id)
        except Exception:
            logger.exception("delete_user_account: reset_user_data step failed")

        # Then delete the UTILISATEURS row itself.
        try:
            with self.connexion() as conn:
                cur = conn.execute(
                    "DELETE FROM UTILISATEURS WHERE id = %s", (user_id,)
                )
                return (cur.rowcount or 0) > 0
        except Exception:
            logger.exception("delete_user_account: UTILISATEURS delete failed")
            return False

    def get_user_date_creation(self, user_id: int):
        """Signup date of the user (returns date or None)."""
        try:
            with self.connexion() as conn:
                row = conn.execute(
                    "SELECT date_creation FROM UTILISATEURS WHERE id = %s",
                    (user_id,),
                ).fetchone()
            if not row or row[0] is None:
                return None
            val = row[0]
            return val.date() if hasattr(val, "date") else val
        except Exception:
            return None

    def sauvegarder_epargne_mois(self, user_id: int, mois: str,
                                  montant_reel: float,
                                  montant_vise: float = 0.0) -> None:
        with self.connexion() as conn:
            cum_row = conn.execute(
                "SELECT COALESCE(SUM(Montant_Reel),0) FROM EPARGNE_HISTO"
                " WHERE user_id=%s AND Mois != %s",
                (user_id, mois),
            ).fetchone()
            cumul = float(cum_row[0] or 0) + montant_reel
            conn.execute(
                """INSERT INTO EPARGNE_HISTO
                   (Mois, Montant_Vise, Montant_Reel, Cumul_Total, user_id)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (Mois, user_id) DO UPDATE
                   SET Montant_Reel=EXCLUDED.Montant_Reel,
                       Montant_Vise=EXCLUDED.Montant_Vise,
                       Cumul_Total=EXCLUDED.Cumul_Total""",
                (mois, montant_vise, montant_reel, cumul, user_id),
            )

    # ─────────────────────────────────────────────────────────────────────────
    # A_CLASSIFIER + REGLES_UTILISATEUR
    # ─────────────────────────────────────────────────────────────────────────

    def ensure_regles_sous_categorie(self) -> None:
        """Add Sous_Categorie_Cible to REGLES_UTILISATEUR if it was created without it."""
        try:
            with self.connexion() as conn:
                conn.execute(
                    "ALTER TABLE REGLES_UTILISATEUR"
                    " ADD COLUMN IF NOT EXISTS Sous_Categorie_Cible TEXT DEFAULT ''"
                )
        except Exception:
            logger.exception("ensure_regles_sous_categorie failed")

    def _ensure_admin_column(self) -> None:
        """Add is_admin to UTILISATEURS for DBs created before this column existed."""
        try:
            with self.connexion() as conn:
                conn.execute(
                    "ALTER TABLE UTILISATEURS"
                    " ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE"
                )
        except Exception:
            logger.exception("_ensure_admin_column failed")

    def _ensure_profile_columns(self) -> None:
        """Add nom + email to UTILISATEURS for DBs created before these existed."""
        try:
            with self.connexion() as conn:
                conn.execute(
                    "ALTER TABLE UTILISATEURS"
                    " ADD COLUMN IF NOT EXISTS nom TEXT DEFAULT '',"
                    " ADD COLUMN IF NOT EXISTS email TEXT DEFAULT ''"
                )
        except Exception:
            logger.exception("_ensure_profile_columns failed")

    def _ensure_daret_v2_columns(self) -> None:
        """Add Statuts_JSON + Tirage_Seed to DARETS for the manager dashboard.

        Statuts_JSON stores per-month per-member payment status:
            {"04/2026": {"Karim": "PAID", "Sara": "DECLARED", "Ali": "PENDING"}}
        Tirage_Seed records the random seed used for fair member ordering
        (audit trail — any member can verify the order wasn't manipulated).
        """
        try:
            with self.connexion() as conn:
                conn.execute(
                    "ALTER TABLE DARETS"
                    " ADD COLUMN IF NOT EXISTS Statuts_JSON TEXT DEFAULT '{}',"
                    " ADD COLUMN IF NOT EXISTS Tirage_Seed BIGINT DEFAULT NULL"
                )
        except Exception:
            logger.exception("_ensure_daret_v2_columns failed")

    def update_daret_statut(self, daret_id: int, mois: str, membre: str, statut: str) -> bool:
        """Update one cell of the Bloomberg-style status table.

        statut ∈ {'PAID', 'DECLARED', 'PENDING'} (or anything — caller validates).
        """
        import json
        try:
            with self.connexion() as conn:
                row = conn.execute(
                    "SELECT Statuts_JSON FROM DARETS WHERE id = %s",
                    (daret_id,),
                ).fetchone()
                if not row:
                    return False
                raw = (row["Statuts_JSON"] if "Statuts_JSON" in row else row[0]) or "{}"
                try:
                    statuts = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    statuts = {}
                statuts.setdefault(mois, {})[membre] = statut
                conn.execute(
                    "UPDATE DARETS SET Statuts_JSON = %s WHERE id = %s",
                    (json.dumps(statuts), daret_id),
                )
            return True
        except Exception:
            logger.exception("update_daret_statut failed")
            return False

    def get_daret_statuts(self, daret_id: int) -> dict:
        """Returns the per-month per-member status dict (or {} if none)."""
        import json
        try:
            with self.connexion() as conn:
                row = conn.execute(
                    "SELECT Statuts_JSON FROM DARETS WHERE id = %s",
                    (daret_id,),
                ).fetchone()
            if not row:
                return {}
            raw = (row["Statuts_JSON"] if "Statuts_JSON" in row else row[0]) or "{}"
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get_user_profile(self, user_id: int) -> dict:
        """Returns {username, nom, email} or empty dict if not found."""
        try:
            with self.connexion() as conn:
                row = conn.execute(
                    "SELECT username, nom, email FROM UTILISATEURS WHERE id = %s",
                    (user_id,),
                ).fetchone()
            if not row:
                return {}
            return {
                "username": row["username"] if "username" in row else row[0],
                "nom":      (row["nom"] if "nom" in row else row[1]) or "",
                "email":    (row["email"] if "email" in row else row[2]) or "",
            }
        except Exception:
            return {}

    def update_user_profile(self, user_id: int, nom: str, email: str) -> bool:
        try:
            with self.connexion() as conn:
                conn.execute(
                    "UPDATE UTILISATEURS SET nom = %s, email = %s WHERE id = %s",
                    (nom.strip(), email.strip().lower(), user_id),
                )
            return True
        except Exception:
            logger.exception("update_user_profile failed")
            return False

    def verify_password(self, user_id: int, password: str) -> bool:
        """Check that `password` matches the bcrypt hash stored for this user."""
        import bcrypt
        try:
            with self.connexion() as conn:
                row = conn.execute(
                    "SELECT password_hash FROM UTILISATEURS WHERE id = %s",
                    (user_id,),
                ).fetchone()
            if not row:
                return False
            stored = row["password_hash"] if "password_hash" in row else row[0]
            return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
        except Exception:
            logger.exception("verify_password failed")
            return False

    def set_password(self, user_id: int, new_password: str) -> bool:
        """Hash + persist a new password (no current-password check — caller verifies)."""
        import bcrypt
        try:
            new_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            with self.connexion() as conn:
                conn.execute(
                    "UPDATE UTILISATEURS SET password_hash = %s WHERE id = %s",
                    (new_hash, user_id),
                )
            return True
        except Exception:
            logger.exception("set_password failed")
            return False

    def is_admin(self, user_id: int) -> bool:
        with self.connexion() as conn:
            cur = conn.execute(
                "SELECT is_admin FROM UTILISATEURS WHERE id=%s", (user_id,)
            )
            row = cur.fetchone()
        return bool(row[0]) if row else False

    def get_mots_cles_inconnus(self, user_id: int) -> List[Dict]:
        with self.connexion() as conn:
            rows = conn.execute(
                """SELECT Mot_Cle_Inconnu, Sens, Categorie_Auto, Sous_Categorie_Auto,
                          Nb_Occurrences, Date_Ajout
                   FROM A_CLASSIFIER
                   WHERE user_id=%s AND Enrichi=0
                   ORDER BY Nb_Occurrences DESC""",
                (user_id,),
            ).fetchall()
        return [_canon_dict(r) for r in rows]

    def sauvegarder_regle(self, sens: str, mot_cle: str,
                          categorie: str, sous_categorie: str, user_id: int) -> None:
        with self.connexion() as conn:
            conn.execute(
                """INSERT INTO REGLES_UTILISATEUR
                   (Sens, Mot_Cle, Categorie_Cible, Sous_Categorie_Cible, user_id)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (Sens, Mot_Cle) DO UPDATE
                   SET Categorie_Cible=EXCLUDED.Categorie_Cible,
                       Sous_Categorie_Cible=EXCLUDED.Sous_Categorie_Cible""",
                (sens, mot_cle.strip(), categorie.strip(), sous_categorie.strip(), user_id),
            )

    def marquer_enrichi(self, mot_cle: str, sens: str, user_id: int) -> None:
        with self.connexion() as conn:
            conn.execute(
                "UPDATE A_CLASSIFIER SET Enrichi=1"
                " WHERE Mot_Cle_Inconnu=%s AND Sens=%s AND user_id=%s",
                (mot_cle, sens, user_id),
            )

    def reclassifier_par_mot_cle(self, mot_cle: str, sens: str,
                                  categorie: str, sous_categorie: str,
                                  user_id: int) -> int:
        """Re-classify VALIDE=A_CLASSIFIER transactions whose Libelle contains mot_cle."""
        with self.connexion() as conn:
            cur = conn.execute(
                """UPDATE TRANSACTIONS
                   SET Categorie=%s, Sous_Categorie=%s, Statut='VALIDE'
                   WHERE user_id=%s AND Sens=%s AND Statut='A_CLASSIFIER'
                     AND UPPER(Libelle) LIKE %s""",
                (categorie, sous_categorie, user_id, sens, f"%{mot_cle.upper()}%"),
            )
            return cur.rowcount or 0

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
                """SELECT c.Categorie AS categorie,
                          c.Sous_Categorie AS sous_categorie,
                          c.Plafond AS plafond
                   FROM CATEGORIES c
                   JOIN REFERENTIEL r ON c.Categorie=r.Categorie AND c.Sous_Categorie=r.Sous_Categorie
                   WHERE r.Sens='OUT'
                   ORDER BY c.Categorie, c.Sous_Categorie"""
            )
            rows = cur.fetchall()
        return [
            {"Categorie": r["categorie"],
             "Sous_Categorie": r["sous_categorie"],
             "Plafond": r["plafond"]}
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
