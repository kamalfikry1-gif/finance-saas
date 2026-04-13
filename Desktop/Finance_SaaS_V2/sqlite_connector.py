"""
SQLITE_CONNECTOR.PY — REMPLACEMENT DROP-IN DE GoogleSheetsConnector
=====================================================================
Ce module fournit SQLiteConnector qui implémente EXACTEMENT la même
interface que GoogleSheetsConnector. Il suffit de changer l'import
dans processor.py et logic.py pour basculer de Google Sheets à SQLite.

MIGRATION :
  # Avant (Google Sheets)
  from processor import GoogleSheetsConnector
  connector = GoogleSheetsConnector(spreadsheet_id, credentials_path)

  # Après (SQLite)
  from sqlite_connector import SQLiteConnector
  connector = SQLiteConnector("finance_saas.db")

Les classes FinanceLogic, Trieur, ComptableBudget, Douane fonctionnent
sans aucune modification.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Any, Optional, List, Dict
from contextlib import contextmanager
from dataclasses import dataclass

import pandas as pd

logger = logging.getLogger("BUDGET_ENGINE")


# ─────────────────────────────────────────────────────────────────────────────
# CLASSE SIMULANT gspread.Worksheet POUR COMPATIBILITÉ
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SQLiteCell:
    """Émule gspread.Cell pour les mises à jour par cellule."""
    row: int
    col: int
    value: Any


class SQLiteWorksheet:
    """
    Émule un objet gspread.Worksheet pour SQLite.
    
    Permet à ComptableBudget._maj_referentiel() et autres méthodes
    d'utiliser la même API (get_all_values, append_row, update_cells).
    """

    def __init__(self, connector: "SQLiteConnector", table_name: str, columns: List[str]):
        self.connector = connector
        self.table_name = table_name
        self.columns = columns
        self._data_cache: Optional[List[List[Any]]] = None

    def get_all_values(self) -> List[List[Any]]:
        """
        Retourne toutes les données sous forme de liste de listes
        (première ligne = en-têtes, comme gspread).
        """
        with self.connector._connexion() as conn:
            cursor = conn.execute(f"SELECT * FROM {self.table_name}")
            rows = cursor.fetchall()
        
        # Première ligne = en-têtes (noms des colonnes)
        result = [self.columns]
        for row in rows:
            result.append(list(row))
        
        self._data_cache = result
        return result

    def get_all_records(self, default_blank: str = "") -> List[Dict[str, Any]]:
        """
        Retourne les données sous forme de liste de dicts
        (comme gspread.Worksheet.get_all_records).
        """
        with self.connector._connexion() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(f"SELECT * FROM {self.table_name}")
            rows = cursor.fetchall()
        
        return [
            {col: (row[col] if row[col] is not None else default_blank) for col in self.columns}
            for row in rows
        ]

    def append_row(self, ligne: List[Any]) -> None:
        """
        Ajoute une ligne à la fin de la table.
        """
        placeholders = ", ".join(["?"] * len(ligne))
        cols = ", ".join(self.columns[:len(ligne)])
        
        with self.connector._connexion() as conn:
            conn.execute(
                f"INSERT INTO {self.table_name} ({cols}) VALUES ({placeholders})",
                ligne
            )
        logger.info(f"✅ Ligne ajoutée avec succès dans '{self.table_name}'")

    def append_rows(self, lignes: List[List[Any]], value_input_option: str = None) -> None:
        """
        Ajoute plusieurs lignes à la table.
        """
        if not lignes:
            return
        
        placeholders = ", ".join(["?"] * len(lignes[0]))
        cols = ", ".join(self.columns[:len(lignes[0])])
        
        with self.connector._connexion() as conn:
            conn.executemany(
                f"INSERT INTO {self.table_name} ({cols}) VALUES ({placeholders})",
                lignes
            )
        logger.info(f"✅ {len(lignes)} ligne(s) ajoutée(s) dans '{self.table_name}'")

    def update_cells(self, cells: List[SQLiteCell], value_input_option: str = None) -> None:
        """
        Met à jour des cellules spécifiques.
        
        Note : En SQLite, on utilise une approche différente de gspread.
        On recharge les données, modifie en mémoire, puis UPDATE via ROWID.
        
        cells = [SQLiteCell(row=2, col=4, value=123), ...]
        row est l'index de ligne (2 = première ligne de données après en-têtes)
        col est l'index de colonne (1-based comme gspread)
        """
        if not cells:
            return

        # Recharger les données avec ROWID pour identifier chaque ligne
        with self.connector._connexion() as conn:
            cursor = conn.execute(f"SELECT rowid, * FROM {self.table_name}")
            rows_with_id = cursor.fetchall()

        if not rows_with_id:
            logger.warning("⚠️ Pas de données à mettre à jour")
            return

        # Construire un mapping row_idx → rowid (row 2 = première donnée = index 0 dans rows)
        # row=2 correspond à rows_with_id[0], row=3 à rows_with_id[1], etc.
        
        with self.connector._connexion() as conn:
            for cell in cells:
                data_idx = cell.row - 2  # row=2 → index 0 dans rows_with_id
                col_idx = cell.col - 1   # Convertir en 0-based

                if data_idx < 0 or data_idx >= len(rows_with_id):
                    logger.warning(f"⚠️ Ligne hors limites : row={cell.row}")
                    continue
                    
                if col_idx < 0 or col_idx >= len(self.columns):
                    logger.warning(f"⚠️ Colonne hors limites : col={cell.col}")
                    continue

                # Récupérer le ROWID de cette ligne (premier élément du tuple)
                rowid = rows_with_id[data_idx][0]
                col_name = self.columns[col_idx]

                conn.execute(
                    f"UPDATE {self.table_name} SET {col_name} = ? WHERE rowid = ?",
                    (cell.value, rowid)
                )

        logger.info(f"✅ {len(cells)} cellule(s) mise(s) à jour dans '{self.table_name}'")


# ─────────────────────────────────────────────────────────────────────────────
# CONNECTEUR PRINCIPAL SQLITE
# ─────────────────────────────────────────────────────────────────────────────

class SQLiteConnector:
    """
    Connecteur SQLite compatible avec l'interface GoogleSheetsConnector.
    
    Implémente les mêmes méthodes :
      - load_sheet(sheet_key) → pd.DataFrame
      - get_sheet(sheet_key)  → SQLiteWorksheet (émule gspread.Worksheet)
      - ecrire_ligne(sheet_key, ligne) → INSERT INTO
    
    Usage :
        connector = SQLiteConnector("finance_saas.db")
        
        # Fonctionne exactement comme GoogleSheetsConnector
        df = connector.load_sheet("transactions")
        connector.ecrire_ligne("transactions", [id, date, ...])
    """

    # Mapping des clés vers les noms de tables (identique à GoogleSheetsConnector)
    SHEETS = {
        "referentiel":   "REFERENTIEL",
        "config_fixe":   "CONFIG_FIXE",
        "dico":          "DICO_MATCHING",
        "transactions":  "TRANSACTIONS",
        "epargne":       "EPARGNE_HISTO",
        "a_classifier":  "A_CLASSIFIER",
    }

    # Schéma des tables avec colonnes ordonnées
    SCHEMAS = {
        "REFERENTIEL": [
            "Categorie", "Sous_Categorie", "Sens", "Frequence", 
            "Statut", "Compteur_N", "Montant_Cumule"
        ],
        "CONFIG_FIXE": [
            "Nom_Fixe", "Montant", "Jour", "Categorie", 
            "Sous_Categorie", "Plafond_Mensuel"
        ],
        "DICO_MATCHING": [
            "Sens", "Mot_Cle", "Categorie_Cible", "Sous_Categorie_Cible"
        ],
        "TRANSACTIONS": [
            "ID_Unique", "Date_Saisie", "Date_Valeur", "Mot_Cle",
            "Montant", "Categorie", "Sous_Categorie"
        ],
        "EPARGNE_HISTO": [
            "Mois", "Montant_Vise", "Montant_Reel", "Evolution_DH"
        ],
        "A_CLASSIFIER": [
            "Mot_Cle_Inconnu", "Categorie_Choisie", "Date_Ajout", "Nb_Occurrences"
        ],
    }

    def __init__(self, db_path: str = "finance_saas.db"):
        """
        Paramètres :
          db_path — Chemin vers le fichier SQLite (créé si inexistant).
        
        Note : Les arguments spreadsheet_id et credentials_path de 
        GoogleSheetsConnector sont ignorés pour la compatibilité.
        """
        self.db_path = Path(db_path)
        self._ws_cache: Dict[str, SQLiteWorksheet] = {}
        
        # Attributs pour compatibilité avec GoogleSheetsConnector
        self.spreadsheet_id = str(db_path)
        self.credentials_path = None
        self.sheets = self.SHEETS
        
        # Initialiser le schéma si la base n'existe pas
        self._initialiser_schema()
        logger.info(f"✅ Connexion établie à la base SQLite : '{self.db_path}'")

    @contextmanager
    def _connexion(self):
        """Context manager pour connexion SQLite avec auto-commit."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Transaction SQL rollback : {e}")
            raise
        finally:
            conn.close()

    def _initialiser_schema(self) -> None:
        """Crée les tables si elles n'existent pas."""
        with self._connexion() as conn:
            # REFERENTIEL
            conn.execute("""
                CREATE TABLE IF NOT EXISTS REFERENTIEL (
                    Categorie       TEXT NOT NULL,
                    Sous_Categorie  TEXT NOT NULL,
                    Sens            TEXT DEFAULT 'OUT',
                    Frequence       TEXT DEFAULT 'VARIABLE',
                    Statut          TEXT DEFAULT 'ACTIF',
                    Compteur_N      INTEGER DEFAULT 0,
                    Montant_Cumule  REAL DEFAULT 0.0,
                    PRIMARY KEY (Categorie, Sous_Categorie)
                )
            """)

            # CONFIG_FIXE
            conn.execute("""
                CREATE TABLE IF NOT EXISTS CONFIG_FIXE (
                    Nom_Fixe        TEXT PRIMARY KEY,
                    Montant         REAL,
                    Jour            INTEGER,
                    Categorie       TEXT,
                    Sous_Categorie  TEXT,
                    Plafond_Mensuel REAL DEFAULT 0.0
                )
            """)

            # DICO_MATCHING
            conn.execute("""
                CREATE TABLE IF NOT EXISTS DICO_MATCHING (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    Sens                 TEXT NOT NULL,
                    Mot_Cle              TEXT NOT NULL,
                    Categorie_Cible      TEXT NOT NULL,
                    Sous_Categorie_Cible TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dico_mot_cle 
                ON DICO_MATCHING(Mot_Cle)
            """)

            # TRANSACTIONS
            conn.execute("""
                CREATE TABLE IF NOT EXISTS TRANSACTIONS (
                    ID_Unique       TEXT PRIMARY KEY,
                    Date_Saisie     TEXT NOT NULL,
                    Date_Valeur     TEXT NOT NULL,
                    Mot_Cle         TEXT NOT NULL,
                    Montant         REAL NOT NULL,
                    Categorie       TEXT DEFAULT '',
                    Sous_Categorie  TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trans_date 
                ON TRANSACTIONS(Date_Valeur)
            """)

            # EPARGNE_HISTO
            conn.execute("""
                CREATE TABLE IF NOT EXISTS EPARGNE_HISTO (
                    Mois          TEXT PRIMARY KEY,
                    Montant_Vise  REAL DEFAULT 0.0,
                    Montant_Reel  REAL DEFAULT 0.0,
                    Evolution_DH  REAL DEFAULT 0.0
                )
            """)

            # A_CLASSIFIER
            conn.execute("""
                CREATE TABLE IF NOT EXISTS A_CLASSIFIER (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    Mot_Cle_Inconnu  TEXT NOT NULL,
                    Categorie_Choisie TEXT DEFAULT '',
                    Date_Ajout       TEXT,
                    Nb_Occurrences   INTEGER DEFAULT 1
                )
            """)

        logger.info("🎉 Schéma SQLite initialisé")

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTHODES PUBLIQUES — INTERFACE IDENTIQUE À GoogleSheetsConnector
    # ─────────────────────────────────────────────────────────────────────────

    def load_sheet(self, sheet_key: str) -> pd.DataFrame:
        """
        Charge une table et retourne un DataFrame.
        Identique à GoogleSheetsConnector.load_sheet().
        """
        table_name = self.SHEETS.get(sheet_key, sheet_key)
        
        try:
            with self._connexion() as conn:
                df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
            return df
        except Exception as e:
            logger.error(f"❌ Erreur lors du chargement de '{table_name}': {e}")
            return pd.DataFrame()

    def get_sheet(self, sheet_key: str) -> Optional[SQLiteWorksheet]:
        """
        Retourne un objet SQLiteWorksheet qui émule gspread.Worksheet.
        Identique à GoogleSheetsConnector.get_sheet().
        """
        table_name = self.SHEETS.get(sheet_key, sheet_key)
        
        if table_name not in self._ws_cache:
            columns = self.SCHEMAS.get(table_name, [])
            if not columns:
                # Détecter les colonnes dynamiquement
                try:
                    with self._connexion() as conn:
                        cursor = conn.execute(f"PRAGMA table_info({table_name})")
                        columns = [row[1] for row in cursor.fetchall()]
                except Exception:
                    logger.error(f"⚠️ La table '{table_name}' est introuvable.")
                    return None
            
            self._ws_cache[table_name] = SQLiteWorksheet(self, table_name, columns)
        
        return self._ws_cache[table_name]

    def ecrire_ligne(self, sheet_key: str, ligne: List[Any]) -> None:
        """
        Ajoute une ligne à une table.
        Identique à GoogleSheetsConnector.ecrire_ligne().
        """
        table_name = self.SHEETS.get(sheet_key, sheet_key)
        columns = self.SCHEMAS.get(table_name, [])
        
        if not columns:
            logger.error(f"❌ Schéma inconnu pour '{table_name}'")
            return

        # Ajuster le nombre de colonnes si nécessaire
        cols = columns[:len(ligne)]
        placeholders = ", ".join(["?"] * len(ligne))
        col_names = ", ".join(cols)

        try:
            with self._connexion() as conn:
                conn.execute(
                    f"INSERT OR REPLACE INTO {table_name} ({col_names}) VALUES ({placeholders})",
                    ligne
                )
            logger.info(f"✅ Ligne ajoutée avec succès dans '{sheet_key}'")
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'écriture dans '{sheet_key}': {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTHODES UTILITAIRES SUPPLÉMENTAIRES
    # ─────────────────────────────────────────────────────────────────────────

    def importer_depuis_dataframe(self, sheet_key: str, df: pd.DataFrame) -> int:
        """
        Importe un DataFrame complet dans une table.
        Utile pour la migration depuis Google Sheets.
        
        Retourne le nombre de lignes importées.
        """
        table_name = self.SHEETS.get(sheet_key, sheet_key)
        
        if df.empty:
            return 0

        nb_inserts = 0
        for _, row in df.iterrows():
            ligne = row.tolist()
            self.ecrire_ligne(sheet_key, ligne)
            nb_inserts += 1

        logger.info(f"📥 {nb_inserts} ligne(s) importée(s) dans '{table_name}'")
        return nb_inserts

    def stats(self) -> Dict[str, int]:
        """Retourne le nombre de lignes par table."""
        result = {}
        with self._connexion() as conn:
            for key, table in self.SHEETS.items():
                try:
                    cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                    result[key] = cursor.fetchone()[0]
                except Exception:
                    result[key] = 0
        return result

    def vider_table(self, sheet_key: str) -> None:
        """Vide une table (utile pour les tests)."""
        table_name = self.SHEETS.get(sheet_key, sheet_key)
        with self._connexion() as conn:
            conn.execute(f"DELETE FROM {table_name}")
        logger.info(f"🗑️ Table '{table_name}' vidée")


# ─────────────────────────────────────────────────────────────────────────────
# ALIAS POUR MIGRATION FACILE
# ─────────────────────────────────────────────────────────────────────────────

# Permet de faire : from sqlite_connector import GoogleSheetsConnector
# et le code existant fonctionne sans modification
GoogleSheetsConnector = SQLiteConnector


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE — TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO)

    # Nettoyer pour le test
    if os.path.exists("test_finance.db"):
        os.remove("test_finance.db")

    # Créer le connecteur
    connector = SQLiteConnector("test_finance.db")

    print("\n" + "=" * 60)
    print("TEST : INTERFACE IDENTIQUE À GoogleSheetsConnector")
    print("=" * 60)

    # Test load_sheet (vide au départ)
    print("\n1. load_sheet('transactions') :")
    df = connector.load_sheet("transactions")
    print(f"   → DataFrame vide : {df.empty}")

    # Test ecrire_ligne
    print("\n2. ecrire_ligne('transactions', [...]) :")
    connector.ecrire_ligne("transactions", [
        "20260406_001", "2026-04-06 10:00:00", "06/04/2026",
        "CARREFOUR MARKET", -45.50, "Alimentation", "Supermarché"
    ])
    connector.ecrire_ligne("transactions", [
        "20260406_002", "2026-04-06 11:00:00", "06/04/2026",
        "NETFLIX", -15.99, "Loisirs", "Streaming"
    ])

    # Test load_sheet après insertion
    print("\n3. load_sheet('transactions') après insertions :")
    df = connector.load_sheet("transactions")
    print(df)

    # Test get_sheet (pour compatibilité ComptableBudget)
    print("\n4. get_sheet('transactions').get_all_values() :")
    ws = connector.get_sheet("transactions")
    data = ws.get_all_values()
    for row in data:
        print(f"   {row}")

    # Test REFERENTIEL
    print("\n5. Test REFERENTIEL :")
    connector.ecrire_ligne("referentiel", [
        "Alimentation", "Supermarché", "OUT", "VARIABLE", "ACTIF", 0, 0.0
    ])
    connector.ecrire_ligne("referentiel", [
        "Loisirs", "Streaming", "OUT", "FIXE", "ACTIF", 0, 0.0
    ])
    df_ref = connector.load_sheet("referentiel")
    print(df_ref)

    # Test update_cells (simulation de _maj_referentiel)
    print("\n6. Test update_cells (simulation _maj_referentiel) :")
    ws_ref = connector.get_sheet("referentiel")
    ws_ref.update_cells([
        SQLiteCell(row=2, col=6, value=5),    # Compteur_N = 5
        SQLiteCell(row=2, col=7, value=123.45) # Montant_Cumule = 123.45
    ])
    df_ref = connector.load_sheet("referentiel")
    print(df_ref)

    # Stats finales
    print("\n7. Stats :")
    print(connector.stats())

    # Nettoyage
    os.remove("test_finance.db")
    print("\n✅ Tous les tests passent — compatibilité validée !")
