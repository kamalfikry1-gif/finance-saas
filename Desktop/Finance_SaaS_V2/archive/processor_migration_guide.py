"""
GUIDE DE MIGRATION : processor.py → SQLite
============================================

Ce fichier montre les SEULES modifications nécessaires dans processor.py
pour passer de Google Sheets à SQLite. Le reste du code ne change PAS.

ÉTAPE 1 : Remplacer les imports (lignes 14-16)
ÉTAPE 2 : Utiliser SQLiteConnector au lieu de GoogleSheetsConnector
ÉTAPE 3 : (Optionnel) Supprimer les time.sleep() car SQLite est local

Le fichier processor.py complet avec SQLite est fourni ci-dessous.
"""

# ═══════════════════════════════════════════════════════════════════════════════
# MODIFICATIONS À FAIRE DANS processor.py
# ═══════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
# ÉTAPE 1 : REMPLACER CES IMPORTS (lignes 14-16 originales)
# ─────────────────────────────────────────────────────────────────────────────

# ❌ AVANT (Google Sheets) :
# import gspread
# from google.oauth2.service_account import Credentials

# ✅ APRÈS (SQLite) :
# from sqlite_connector import SQLiteConnector, SQLiteCell

# ─────────────────────────────────────────────────────────────────────────────
# ÉTAPE 2 : REMPLACER LA CLASSE GoogleSheetsConnector (lignes 130-188)
# ─────────────────────────────────────────────────────────────────────────────

# ❌ SUPPRIMER TOUT LE BLOC GoogleSheetsConnector (class GoogleSheetsConnector: ...)

# ✅ AJOUTER CET IMPORT À LA PLACE :
# from sqlite_connector import SQLiteConnector as GoogleSheetsConnector, SQLiteCell as Cell

# Ceci permet de garder le même nom de classe partout dans le code existant !

# ─────────────────────────────────────────────────────────────────────────────
# ÉTAPE 3 : MODIFIER L'INSTANCIATION (dans votre code Streamlit ou main)
# ─────────────────────────────────────────────────────────────────────────────

# ❌ AVANT :
# connector = GoogleSheetsConnector(
#     spreadsheet_id="1ABC...XYZ",
#     credentials_path="credentials.json"
# )

# ✅ APRÈS :
# connector = GoogleSheetsConnector("finance_saas.db")

# ─────────────────────────────────────────────────────────────────────────────
# ÉTAPE 4 : ADAPTER _maj_referentiel DANS ComptableBudget (ligne ~796)
# ─────────────────────────────────────────────────────────────────────────────

# ❌ AVANT (gspread.Cell) :
# ws.update_cells([
#     gspread.Cell(num_ligne, col_compteur, compteur_actuel + 1),
#     gspread.Cell(num_ligne, col_cumul, round(cumul_actuel + montant_abs, 2)),
# ])

# ✅ APRÈS (SQLiteCell importé du connector) :
# from sqlite_connector import SQLiteCell
# ws.update_cells([
#     SQLiteCell(num_ligne, col_compteur, compteur_actuel + 1),
#     SQLiteCell(num_ligne, col_cumul, round(cumul_actuel + montant_abs, 2)),
# ])

# ─────────────────────────────────────────────────────────────────────────────
# ÉTAPE 5 (OPTIONNEL) : SUPPRIMER LES time.sleep()
# ─────────────────────────────────────────────────────────────────────────────

# Les time.sleep(1.2) étaient nécessaires pour éviter les quotas Google API.
# Avec SQLite local, ils ne sont plus nécessaires → supprimer ou commenter.

# ❌ AVANT :
# time.sleep(1.2)  # Quota Google API 429

# ✅ APRÈS :
# (supprimer la ligne ou la commenter)


# ═══════════════════════════════════════════════════════════════════════════════
# FICHIER processor.py MODIFIÉ COMPLET — UNIQUEMENT LES CHANGEMENTS
# ═══════════════════════════════════════════════════════════════════════════════
"""
Voici les lignes modifiées à copier-coller dans processor.py :
"""

# --- DÉBUT DU BLOC À MODIFIER (remplace lignes 1-20 de processor.py) ---

PROCESSOR_PY_HEADER = '''
"""
PROJET : GESTIONNAIRE DE BUDGET INTELLIGENT
BLOCS 0 à 3 : STRUCTURES, CONNEXION, NETTOYAGE & CLASSIFICATION

VERSION SQLITE — Migration depuis Google Sheets
"""

import re
import logging
import time
import unicodedata
from datetime import datetime, date, timedelta
from typing import Any, Optional, List, Dict, Tuple
from dataclasses import dataclass, field

import pandas as pd

# ═══ MIGRATION SQLITE : Import du connecteur SQLite ═══
from sqlite_connector import SQLiteConnector as GoogleSheetsConnector, SQLiteCell

# Note : On garde l'alias "GoogleSheetsConnector" pour éviter de modifier
# tout le reste du code. Le changement est transparent.

from rapidfuzz import fuzz, process as fuzz_process
'''

# --- FIN DU BLOC HEADER ---

# --- BLOC À AJOUTER : Remplacer gspread.Cell par SQLiteCell (ligne ~796) ---

MAJ_REFERENTIEL_PATCH = '''
            # ═══ MIGRATION SQLITE : Utiliser SQLiteCell au lieu de gspread.Cell ═══
            ws.update_cells([
                SQLiteCell(num_ligne, col_compteur, compteur_actuel + 1),
                SQLiteCell(num_ligne, col_cumul,    round(cumul_actuel + montant_abs, 2)),
            ])
'''

# --- BLOC À AJOUTER : Idem pour _maj_epargne_histo (ligne ~860) ---

MAJ_EPARGNE_PATCH = '''
                # ═══ MIGRATION SQLITE : Utiliser SQLiteCell au lieu de gspread.Cell ═══
                ws.update_cells([
                    SQLiteCell(num_ligne, idx_reel + 1, nouveau_reel),
                    SQLiteCell(num_ligne, idx_evol + 1, evolution),
                ])
'''

# --- BLOC À SUPPRIMER : Les time.sleep() ne sont plus nécessaires ---

LIGNES_A_SUPPRIMER = '''
# Supprimer ces lignes (ou les commenter) :
time.sleep(1.2)  # Quota Google API 429
'''


# ═══════════════════════════════════════════════════════════════════════════════
# SCRIPT DE MIGRATION AUTOMATIQUE (optionnel)
# ═══════════════════════════════════════════════════════════════════════════════

def migrer_processor_py(input_path: str, output_path: str) -> None:
    """
    Applique automatiquement les modifications à processor.py.
    
    Usage :
        python processor_migration.py processor.py processor_sqlite.py
    """
    with open(input_path, "r", encoding="utf-8") as f:
        contenu = f.read()

    # 1. Remplacer les imports gspread
    contenu = contenu.replace(
        "import gspread\nfrom google.oauth2.service_account import Credentials",
        "from sqlite_connector import SQLiteConnector as GoogleSheetsConnector, SQLiteCell"
    )
    contenu = contenu.replace(
        "import gspread",
        "# import gspread  # Remplacé par sqlite_connector"
    )
    contenu = contenu.replace(
        "from google.oauth2.service_account import Credentials",
        "# from google.oauth2.service_account import Credentials  # Non nécessaire avec SQLite"
    )

    # 2. Remplacer gspread.Cell par SQLiteCell
    contenu = contenu.replace("gspread.Cell", "SQLiteCell")

    # 3. Commenter les time.sleep (optionnel — garde la compatibilité)
    contenu = contenu.replace(
        "time.sleep(1.2)  # Quota Google API 429",
        "# time.sleep(1.2)  # Quota Google API 429 — Non nécessaire avec SQLite"
    )

    # 4. Supprimer la classe GoogleSheetsConnector (elle est maintenant importée)
    import re
    pattern = r"class GoogleSheetsConnector:.*?(?=\n# ─{20,}|\nclass )"
    contenu = re.sub(pattern, "# GoogleSheetsConnector est maintenant importé depuis sqlite_connector\n\n", contenu, flags=re.DOTALL)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(contenu)

    print(f"✅ Migration effectuée : {output_path}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) == 3:
        migrer_processor_py(sys.argv[1], sys.argv[2])
    else:
        print(__doc__)
        print("\nUsage : python processor_migration.py <input.py> <output.py>")
