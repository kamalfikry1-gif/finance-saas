"""
reset_db.py -- Reinitialisation propre de la base de donnees Finance SaaS.

Usage:
    python reset_db.py            # menu interactif
    python reset_db.py --full     # supprime tout et recree le schema
    python reset_db.py --data     # supprime seulement les transactions/snapshots
    python reset_db.py --seed     # injecte des donnees de test realistes
    python reset_db.py --stats    # affiche les stats actuelles de la DB
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
import random

from config import DB_PATH as _DB_PATH_STR

DB_PATH = Path(_DB_PATH_STR)


# ----------------------------------------------------------
# Connexion
# ----------------------------------------------------------

def get_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        print(f"[INFO] DB not found at {DB_PATH} -- will be created.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ----------------------------------------------------------
# Stats
# ----------------------------------------------------------

def show_stats():
    if not DB_PATH.exists():
        print("[WARN] Aucune DB trouvee.")
        return

    conn = get_conn()
    tables_db = ["TRANSACTIONS", "CATEGORIES", "PREFERENCES", "OBJECTIFS", "BUDGETS_MENSUELS"]
    tables_audit = ["AUDIT_LOG", "SNAPSHOTS"]  # creees par AuditMiddleware

    print("\n--- Etat de la base de donnees ---")
    for t in tables_db:
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t:<25} {n:>6} lignes")
        except Exception:
            print(f"  {t:<25}    n/a")
    for t in tables_audit:
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t:<25} {n:>6} lignes")
        except Exception:
            print(f"  {t:<25}    n/a  (sera cree au 1er lancement)")
    print("----------------------------------\n")
    conn.close()


# ----------------------------------------------------------
# Reset complet
# ----------------------------------------------------------

def reset_full():
    """Supprime la DB et recree le schema propre via db_manager."""
    print("[RESET FULL] Suppression de la base de donnees...")
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"  [OK] {DB_PATH} supprime.")

    from db_manager import DatabaseManager
    db = DatabaseManager(str(DB_PATH))
    db.initialiser_schema()
    print("  [OK] Schema recree (tables + preferences par defaut).")
    show_stats()


# ----------------------------------------------------------
# Reset donnees uniquement (garde preferences/objectifs/budgets)
# ----------------------------------------------------------

TABLES_DONNEES = [
    "TRANSACTIONS",
    "AUDIT_LOG",   # cree par AuditMiddleware.__init__ au premier lancement
    "SNAPSHOTS",   # idem
]

def reset_data():
    """Vide les tables de donnees -- conserve config/preferences."""
    print("[RESET DATA] Vidage des tables de donnees...")
    conn = get_conn()
    for t in TABLES_DONNEES:
        try:
            conn.execute(f"DELETE FROM {t}")
            print(f"  [OK] {t} vide.")
        except Exception as e:
            print(f"  [ERR] {t} -- {e}")
    conn.commit()
    conn.close()
    show_stats()


# ----------------------------------------------------------
# Seed -- donnees de test realistes (3 mois)
# ----------------------------------------------------------

SEED_TRANSACTIONS = [
    # (libelle, montant_abs, sens, categorie, sous_cat, jour_du_mois)
    # sens: "IN" = entree, "OUT" = sortie (schema reel)
    # -- Revenus --
    ("Virement salaire",       8500, "IN",  "Revenus",       "Salaire",       1),
    ("Freelance design",       1200, "IN",  "Revenus",       "Freelance",     8),
    ("Remboursement ami",       300, "IN",  "Revenus",       "Autre",        15),

    # -- Logement --
    ("Loyer appartement",      2800, "OUT", "Logement",      "Loyer",         2),
    ("EDF electricite",         180, "OUT", "Logement",      "Energie",       5),
    ("Internet fibre",           60, "OUT", "Logement",      "Telecom",       5),
    ("Assurance habitation",     45, "OUT", "Logement",      "Assurance",     6),

    # -- Alimentation --
    ("Carrefour courses",       320, "OUT", "Alimentation",  "Supermarche",   3),
    ("Marche bio Thiais",        85, "OUT", "Alimentation",  "Marche",        7),
    ("Lidl courses",            210, "OUT", "Alimentation",  "Supermarche",  14),
    ("Restaurant La Bonne",      95, "OUT", "Alimentation",  "Restaurant",   11),
    ("Deliveroo commande",       38, "OUT", "Alimentation",  "Livraison",    18),
    ("Franprix express",         62, "OUT", "Alimentation",  "Supermarche",  22),

    # -- Transport --
    ("SNCF billet TGV",        145, "OUT", "Transport",     "Train",          4),
    ("Essence Total",            90, "OUT", "Transport",     "Carburant",     10),
    ("Uber trajet",              24, "OUT", "Transport",     "VTC",           17),

    # -- Loisirs --
    ("Netflix abonnement",       17, "OUT", "Loisirs",       "Streaming",      5),
    ("Spotify Premium",          10, "OUT", "Loisirs",       "Streaming",      5),
    ("Cinema UGC",               28, "OUT", "Loisirs",       "Sorties",       13),
    ("Amazon Prime",             49, "OUT", "Loisirs",       "Shopping",       5),

    # -- Sante --
    ("Pharmacie ordonnance",     45, "OUT", "Sante",         "Pharmacie",      9),
    ("Medecin generaliste",      30, "OUT", "Sante",         "Consultation",  16),

    # -- Epargne --
    ("Virement epargne LDD",    500, "OUT", "Epargne",       "Livret",         3),
    ("Assurance vie versement", 300, "OUT", "Epargne",       "AV",             3),
]

def seed_data(nb_mois: int = 3):
    """Injecte des donnees de test realistes pour nb_mois mois consecutifs."""
    import uuid
    import pandas as pd

    print(f"[SEED] Injection de {nb_mois} mois de donnees de test...")

    from db_manager import DatabaseManager
    db = DatabaseManager(str(DB_PATH))
    db.initialiser_schema()

    today = datetime.now()
    rows = []

    for m in range(nb_mois - 1, -1, -1):
        mois_dt = today.replace(day=1) - timedelta(days=30 * m)

        for libelle, montant_base, sens, cat, sous_cat, jour_offset in SEED_TRANSACTIONS:
            variation = random.uniform(0.90, 1.10)
            montant = round(montant_base * variation, 2)

            jour = min(jour_offset, 28)
            try:
                date_tx = mois_dt.replace(day=jour)
            except ValueError:
                date_tx = mois_dt.replace(day=28)

            date_str = date_tx.strftime("%Y-%m-%d")
            rows.append({
                "ID_Unique":      str(uuid.uuid4()),
                "Date_Saisie":    date_str,
                "Date_Valeur":    date_str,
                "Libelle":        libelle,
                "Montant":        montant,
                "Sens":           sens,
                "Categorie":      cat,
                "Sous_Categorie": sous_cat,
            })

    df = pd.DataFrame(rows)
    total = db.importer_transactions_df(df)

    # Les transactions seed ont deja une categorie -> marquer VALIDE
    conn2 = get_conn()
    conn2.execute(
        "UPDATE TRANSACTIONS SET Statut = 'VALIDE' WHERE Categorie != '' AND Sous_Categorie != ''"
    )
    conn2.commit()
    conn2.close()

    try:
        db.creer_objectif("Vacances Portugal", 3000.0, "2026-08-01")
        db.creer_objectif("Fonds urgence 6 mois", 15000.0, "2026-12-31")
        db.maj_objectif_actuel(1, 850.0)
        print("  [OK] 2 objectifs crees (Vacances Portugal, Fonds urgence).")
    except Exception as e:
        print(f"  [WARN] Objectifs -- {e}")

    print(f"  [OK] {total} transactions injectees sur {nb_mois} mois.")
    show_stats()


# ----------------------------------------------------------
# Menu interactif
# ----------------------------------------------------------

MENU = """
+----------------------------------------------+
|    Finance SaaS -- Gestion de la DB          |
+----------------------------------------------+
|  1. Afficher les stats                       |
|  2. Reset DATA (transactions + logs)         |
|  3. Reset FULL (supprime toute la DB)        |
|  4. Seed donnees de test (3 mois)            |
|  5. Reset DATA + Seed (cycle complet)        |
|  0. Quitter                                  |
+----------------------------------------------+
"""

def menu_interactif():
    print(MENU)
    choix = input("Votre choix > ").strip()

    if choix == "1":
        show_stats()
    elif choix == "2":
        confirm = input("[!] Supprimer toutes les transactions/logs ? (oui/non) > ").strip().lower()
        if confirm == "oui":
            reset_data()
        else:
            print("Annule.")
    elif choix == "3":
        confirm = input("[!] SUPPRIMER TOUTE LA BASE DE DONNEES ? (oui/non) > ").strip().lower()
        if confirm == "oui":
            reset_full()
        else:
            print("Annule.")
    elif choix == "4":
        seed_data(nb_mois=3)
    elif choix == "5":
        confirm = input("[!] Reset data + seed 3 mois ? (oui/non) > ").strip().lower()
        if confirm == "oui":
            reset_data()
            seed_data(nb_mois=3)
        else:
            print("Annule.")
    elif choix == "0":
        print("Au revoir.")
        sys.exit(0)
    else:
        print("Choix invalide.")


# ----------------------------------------------------------
# Entry point
# ----------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestion de la base Finance SaaS")
    parser.add_argument("--full",  action="store_true", help="Reset complet (supprime la DB)")
    parser.add_argument("--data",  action="store_true", help="Vide seulement les donnees")
    parser.add_argument("--seed",  action="store_true", help="Injecte donnees de test (3 mois)")
    parser.add_argument("--stats", action="store_true", help="Affiche les stats de la DB")
    args = parser.parse_args()

    if args.full:
        reset_full()
    elif args.data:
        reset_data()
    elif args.seed:
        seed_data(nb_mois=3)
    elif args.stats:
        show_stats()
    else:
        menu_interactif()
