"""
migrate_referentiel.py — Script de migration unique.

Actions :
  1. Peuple REFERENTIEL avec le référentiel complet (ton vrai catalogue)
  2. Peuple CATEGORIES avec les mêmes paires (plafond = 0 par défaut)
  3. Met à jour DICO_MATCHING pour utiliser les bons noms de catégories

Usage :
    python migrate_referentiel.py
"""

import sqlite3
from config import DB_PATH

# ─────────────────────────────────────────────────────────────────────────────
# 1. RÉFÉRENTIEL COMPLET
# ─────────────────────────────────────────────────────────────────────────────

REFERENTIEL = [
    # IN — Revenus
    ("Revenu", "Salaire",                  "IN",  "Mensuel",   "ACTIF"),
    ("Revenu", "Vente",                    "IN",  "Ponctuel",  "ACTIF"),
    ("Revenu", "Remboursement",            "IN",  "Ponctuel",  "ACTIF"),
    ("Revenu", "Allocation Familiale",     "IN",  "Mensuel",   "ACTIF"),
    ("Revenu", "Freelance",                "IN",  "Ponctuel",  "ACTIF"),
    ("Revenu", "Loyer",                    "IN",  "Mensuel",   "ACTIF"),
    ("Revenu", "Dons",                     "IN",  "Ponctuel",  "ACTIF"),
    ("Revenu", "Bricolage",                "IN",  "Ponctuel",  "ACTIF"),
    ("Revenu", "Prime",                    "IN",  "Ponctuel",  "ACTIF"),
    ("Revenu", "Revenu_Autre",             "IN",  "Mensuel",   "ACTIF"),
    # OUT — Logement
    ("Logement", "Loyer",                  "OUT", "Mensuel",   "ACTIF"),
    ("Logement", "Logement_autre",         "OUT", "Ponctuel",  "ACTIF"),
    ("Logement", "Impôts",                 "OUT", "Annuel",    "ACTIF"),
    ("Logement", "Electricité & Eau",      "OUT", "Mensuel",   "ACTIF"),
    ("Logement", "Entretien & Maison",     "OUT", "Ponctuel",  "ACTIF"),
    # OUT — Vie Quotidienne
    ("Vie Quotidienne", "Courses maison",               "OUT", "Ponctuel", "ACTIF"),
    ("Vie Quotidienne", "Protéine",                     "OUT", "Ponctuel", "ACTIF"),
    ("Vie Quotidienne", "Alimentation",                 "OUT", "Ponctuel", "ACTIF"),
    ("Vie Quotidienne", "Fruits & légumes",             "OUT", "Ponctuel", "ACTIF"),
    ("Vie Quotidienne", "Snacks & Boissons",            "OUT", "Ponctuel", "ACTIF"),
    ("Vie Quotidienne", "Restaurant rapide & fast food","OUT", "Ponctuel", "ACTIF"),
    ("Vie Quotidienne", "Vie Quotidienne_Autre",        "OUT", "Ponctuel", "ACTIF"),
    # OUT — Transport
    ("Transport", "Carburant",             "OUT", "Ponctuel",  "ACTIF"),
    ("Transport", "Tramway & Bus",         "OUT", "Ponctuel",  "ACTIF"),
    ("Transport", "Taxi & Uber",           "OUT", "Ponctuel",  "ACTIF"),
    ("Transport", "Entretien & Lavage",    "OUT", "Ponctuel",  "ACTIF"),
    ("Transport", "Assurance & Vignette",  "OUT", "Annuel",    "ACTIF"),
    ("Transport", "Parking & Péage",       "OUT", "Ponctuel",  "ACTIF"),
    ("Transport", "Transport_Autre",       "OUT", "Ponctuel",  "ACTIF"),
    # OUT — Loisirs
    ("Loisirs", "Sorties & Shopping",      "OUT", "Ponctuel",  "ACTIF"),
    ("Loisirs", "Ciné & Culture",          "OUT", "Ponctuel",  "ACTIF"),
    ("Loisirs", "Voyages & Weekend",       "OUT", "Ponctuel",  "ACTIF"),
    ("Loisirs", "Sport & Hobby",           "OUT", "Ponctuel",  "ACTIF"),
    ("Loisirs", "Bien-être & Hygiène",     "OUT", "Ponctuel",  "ACTIF"),
    ("Loisirs", "Cadeaux & Dons",          "OUT", "Ponctuel",  "ACTIF"),
    ("Loisirs", "Loisirs_Autre",           "OUT", "Ponctuel",  "ACTIF"),
    # OUT — Abonnements
    ("Abonnements", "Télécom & Internet",  "OUT", "Mensuel",   "ACTIF"),
    ("Abonnements", "Streaming & TV",      "OUT", "Mensuel",   "ACTIF"),
    ("Abonnements", "Club & Gym",          "OUT", "Mensuel",   "ACTIF"),
    ("Abonnements", "Logiciels & Cloud",   "OUT", "Mensuel",   "ACTIF"),
    ("Abonnements", "Banque & Assur",      "OUT", "Mensuel",   "ACTIF"),
    ("Abonnements", "Abonnements_autre",   "OUT", "Mensuel",   "ACTIF"),
    # OUT — Santé
    ("Santé", "Pharmacie",                 "OUT", "Ponctuel",  "ACTIF"),
    ("Santé", "Consultations",             "OUT", "Ponctuel",  "ACTIF"),
    ("Santé", "Analyses & Radio",          "OUT", "Ponctuel",  "ACTIF"),
    ("Santé", "Optique",                   "OUT", "Ponctuel",  "ACTIF"),
    ("Santé", "Santé_autre",               "OUT", "Ponctuel",  "ACTIF"),
    # OUT — Finances & Crédits
    ("Finances & Crédits", "Crédit Conso ou Auto",      "OUT", "Mensuel",   "ACTIF"),
    ("Finances & Crédits", "Épargne",                   "OUT", "Mensuel",   "ACTIF"),
    ("Finances & Crédits", "Remboursement Dette",       "OUT", "Ponctuel",  "ACTIF"),
    ("Finances & Crédits", "Frais Bancaires",           "OUT", "Ponctuel",  "ACTIF"),
    ("Finances & Crédits", "EPARGNE INVESTISSEMENT",    "OUT", "Variable",  "ACTIF"),
    # OUT — Divers
    ("Divers", "Generale",                 "OUT", "Ponctuel",  "ACTIF"),
    ("Divers", "Frais de dossier",         "OUT", "Ponctuel",  "ACTIF"),
    ("Divers", "Amendes",                  "OUT", "Ponctuel",  "ACTIF"),
    ("Divers", "Administratif",            "OUT", "Ponctuel",  "ACTIF"),
    ("Divers", "Objets du quotidien",      "OUT", "Ponctuel",  "ACTIF"),
    ("Divers", "Divers_Autre",             "OUT", "Ponctuel",  "ACTIF"),
]

# ─────────────────────────────────────────────────────────────────────────────
# 2. MAPPING DICO_MATCHING : ancien → nouveau
# ─────────────────────────────────────────────────────────────────────────────

MAPPING = {
    # (old_cat, old_sous)                       : (new_cat, new_sous)
    ("Alimentation", "Epicerie"):               ("Vie Quotidienne",    "Courses maison"),
    ("Alimentation", "Livraison"):              ("Vie Quotidienne",    "Alimentation"),
    ("Alimentation", "Marche"):                 ("Vie Quotidienne",    "Fruits & légumes"),
    ("Alimentation", "Restaurant"):             ("Vie Quotidienne",    "Restaurant rapide & fast food"),
    ("Alimentation", "Supermarche"):            ("Vie Quotidienne",    "Alimentation"),
    ("Epargne",      "AV"):                     ("Finances & Crédits", "Épargne"),
    ("Epargne",      "Livret"):                 ("Finances & Crédits", "Épargne"),
    ("Logement",     "Assurance"):              ("Abonnements",        "Banque & Assur"),
    ("Logement",     "Energie"):                ("Logement",           "Electricité & Eau"),
    ("Logement",     "Loyer"):                  ("Logement",           "Loyer"),
    ("Logement",     "Telecom"):                ("Abonnements",        "Télécom & Internet"),
    ("Loisirs",      "Shopping"):               ("Loisirs",            "Sorties & Shopping"),
    ("Loisirs",      "Sorties"):                ("Loisirs",            "Sorties & Shopping"),
    ("Loisirs",      "Streaming"):              ("Abonnements",        "Streaming & TV"),
    ("Loisirs",      "Voyage"):                 ("Loisirs",            "Voyages & Weekend"),
    ("Sante",        "Consultation"):           ("Santé",              "Consultations"),
    ("Sante",        "Pharmacie"):              ("Santé",              "Pharmacie"),
    ("Transport",    "Carburant"):              ("Transport",          "Carburant"),
    ("Transport",    "Train"):                  ("Transport",          "Tramway & Bus"),
    ("Transport",    "VTC"):                    ("Transport",          "Taxi & Uber"),
}


def run():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("─" * 60)
    print("MIGRATION RÉFÉRENTIEL — Finance SaaS")
    print("─" * 60)

    # ── Étape 1 : REFERENTIEL ─────────────────────────────────────────────────
    nb_ref = 0
    for cat, sous, sens, freq, statut in REFERENTIEL:
        conn.execute("""
            INSERT OR REPLACE INTO REFERENTIEL
                (Categorie, Sous_Categorie, Sens, Frequence, Statut, Compteur_N, Montant_Cumule)
            VALUES (?, ?, ?, ?, ?, 0, 0.0)
        """, (cat, sous, sens, freq, statut))
        nb_ref += 1
    print(f"✅ REFERENTIEL — {nb_ref} entrées insérées/mises à jour")

    # ── Étape 2 : CATEGORIES ──────────────────────────────────────────────────
    nb_cat = 0
    for cat, sous, sens, freq, statut in REFERENTIEL:
        conn.execute("""
            INSERT OR IGNORE INTO CATEGORIES (Categorie, Sous_Categorie, Plafond)
            VALUES (?, ?, 0.0)
        """, (cat, sous))
        nb_cat += 1
    print(f"✅ CATEGORIES  — {nb_cat} paires insérées (plafond = 0 par défaut)")

    # ── Étape 3 : DICO_MATCHING — mise à jour des noms ───────────────────────
    nb_dico = 0
    for (old_cat, old_sous), (new_cat, new_sous) in MAPPING.items():
        cur = conn.execute("""
            UPDATE DICO_MATCHING
            SET Categorie_Cible      = ?,
                Sous_Categorie_Cible = ?
            WHERE Categorie_Cible      = ?
              AND Sous_Categorie_Cible = ?
        """, (new_cat, new_sous, old_cat, old_sous))
        if cur.rowcount:
            print(f"   {old_cat}/{old_sous}  →  {new_cat}/{new_sous}  ({cur.rowcount} mots-clés)")
            nb_dico += cur.rowcount
    print(f"✅ DICO_MATCHING — {nb_dico} mots-clés harmonisés")

    conn.commit()
    conn.close()

    # ── Résumé final ──────────────────────────────────────────────────────────
    print()
    print("─" * 60)
    print("Vérification finale :")
    conn2 = sqlite3.connect(DB_PATH)
    print(f"  REFERENTIEL : {conn2.execute('SELECT COUNT(*) FROM REFERENTIEL').fetchone()[0]} lignes")
    print(f"  CATEGORIES  : {conn2.execute('SELECT COUNT(*) FROM CATEGORIES').fetchone()[0]} lignes")
    print(f"  DICO_MATCH  : {conn2.execute('SELECT COUNT(*) FROM DICO_MATCHING').fetchone()[0]} mots-clés")
    rows = conn2.execute("""
        SELECT DISTINCT Categorie_Cible, COUNT(*) as n FROM DICO_MATCHING
        WHERE Sens='OUT' GROUP BY Categorie_Cible ORDER BY Categorie_Cible
    """).fetchall()
    print("\n  Catégories dans DICO_MATCHING (OUT) :")
    for r in rows:
        print(f"    {r[0]} ({r[1]} mots-clés)")
    conn2.close()
    print("─" * 60)
    print("Migration terminée ✅")


if __name__ == "__main__":
    run()
