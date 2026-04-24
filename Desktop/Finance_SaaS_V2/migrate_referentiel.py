"""
migrate_referentiel.py — Script de migration idempotent.

Actions :
  1. Peuple REFERENTIEL avec le référentiel simplifié (9 catégories, 40 sous-cat)
  2. Peuple CATEGORIES avec les mêmes paires (plafond = 0 par défaut)
  3. Met à jour DICO_MATCHING : redirige les anciens noms vers la nouvelle structure

Usage :
    python migrate_referentiel.py
"""

import sqlite3
from config import DB_PATH

# ─────────────────────────────────────────────────────────────────────────────
# 1. RÉFÉRENTIEL SIMPLIFIÉ — source unique de vérité
# ─────────────────────────────────────────────────────────────────────────────

REFERENTIEL = [
    # IN — Revenus (5 sous-catégories)
    ("Revenu", "Salaire",                           "IN",  "Mensuel",  "ACTIF"),
    ("Revenu", "Freelance & Activités",             "IN",  "Ponctuel", "ACTIF"),
    ("Revenu", "Aides & Allocations",               "IN",  "Ponctuel", "ACTIF"),
    ("Revenu", "Prime & Bonus",                     "IN",  "Ponctuel", "ACTIF"),
    ("Revenu", "Revenu_Autre",                      "IN",  "Ponctuel", "ACTIF"),

    # OUT — Logement (4 sous-catégories)
    ("Logement", "Loyer",                           "OUT", "Mensuel",  "ACTIF"),
    ("Logement", "Electricité & Eau",               "OUT", "Mensuel",  "ACTIF"),
    ("Logement", "Entretien & Maison",              "OUT", "Ponctuel", "ACTIF"),
    ("Logement", "Charges & Taxes",                 "OUT", "Annuel",   "ACTIF"),

    # OUT — Vie Quotidienne (5 sous-catégories)
    ("Vie Quotidienne", "Courses maison",           "OUT", "Ponctuel", "ACTIF"),
    ("Vie Quotidienne", "Alimentation",             "OUT", "Ponctuel", "ACTIF"),
    ("Vie Quotidienne", "Snacks & Boissons",        "OUT", "Ponctuel", "ACTIF"),
    ("Vie Quotidienne", "Restaurant rapide & fast food", "OUT", "Ponctuel", "ACTIF"),
    ("Vie Quotidienne", "Vie Quotidienne_Autre",    "OUT", "Ponctuel", "ACTIF"),

    # OUT — Transport (6 sous-catégories)
    ("Transport", "Carburant",                      "OUT", "Ponctuel", "ACTIF"),
    ("Transport", "Taxi & Transports",              "OUT", "Ponctuel", "ACTIF"),
    ("Transport", "Entretien & Réparation",         "OUT", "Ponctuel", "ACTIF"),
    ("Transport", "Assurance & Vignette",           "OUT", "Annuel",   "ACTIF"),
    ("Transport", "Parking & Péage",                "OUT", "Ponctuel", "ACTIF"),
    ("Transport", "Transport_Autre",                "OUT", "Ponctuel", "ACTIF"),

    # OUT — Loisirs (5 sous-catégories)
    ("Loisirs", "Sorties & Culture",                "OUT", "Ponctuel", "ACTIF"),
    ("Loisirs", "Voyages & Weekend",                "OUT", "Ponctuel", "ACTIF"),
    ("Loisirs", "Sport & Bien-être",                "OUT", "Ponctuel", "ACTIF"),
    ("Loisirs", "Cadeaux & Dons",                   "OUT", "Ponctuel", "ACTIF"),
    ("Loisirs", "Loisirs_Autre",                    "OUT", "Ponctuel", "ACTIF"),

    # OUT — Abonnements (4 sous-catégories)
    ("Abonnements", "Télécom & Internet",           "OUT", "Mensuel",  "ACTIF"),
    ("Abonnements", "Streaming & Apps",             "OUT", "Mensuel",  "ACTIF"),
    ("Abonnements", "Club & Gym",                   "OUT", "Mensuel",  "ACTIF"),
    ("Abonnements", "Abonnements_autre",            "OUT", "Mensuel",  "ACTIF"),

    # OUT — Santé (4 sous-catégories)
    ("Santé", "Pharmacie",                          "OUT", "Ponctuel", "ACTIF"),
    ("Santé", "Médecin & Examens",                  "OUT", "Ponctuel", "ACTIF"),
    ("Santé", "Optique",                            "OUT", "Ponctuel", "ACTIF"),
    ("Santé", "Santé_autre",                        "OUT", "Ponctuel", "ACTIF"),

    # OUT — Finances & Crédits (3 sous-catégories)
    ("Finances & Crédits", "Crédit & Remboursement",    "OUT", "Mensuel",  "ACTIF"),
    ("Finances & Crédits", "Épargne & Investissement",  "OUT", "Mensuel",  "ACTIF"),
    ("Finances & Crédits", "Frais Bancaires",            "OUT", "Ponctuel", "ACTIF"),

    # OUT — Divers (4 sous-catégories)
    ("Divers", "Administratif",                     "OUT", "Ponctuel", "ACTIF"),
    ("Divers", "Amendes",                           "OUT", "Ponctuel", "ACTIF"),
    ("Divers", "Objets du quotidien",               "OUT", "Ponctuel", "ACTIF"),
    ("Divers", "Divers_Autre",                      "OUT", "Ponctuel", "ACTIF"),
]

# ─────────────────────────────────────────────────────────────────────────────
# 2. MAPPING DICO_MATCHING : anciens noms → nouvelle structure
# Inclut toutes les simplifications appliquées depuis v1.
# ─────────────────────────────────────────────────────────────────────────────

MAPPING = {
    # (old_cat, old_sous)                                : (new_cat, new_sous)

    # Anciens noms pre-v1
    ("Alimentation", "Epicerie"):       ("Vie Quotidienne",    "Courses maison"),
    ("Alimentation", "Livraison"):      ("Vie Quotidienne",    "Alimentation"),
    ("Alimentation", "Marche"):         ("Vie Quotidienne",    "Alimentation"),
    ("Alimentation", "Restaurant"):     ("Vie Quotidienne",    "Restaurant rapide & fast food"),
    ("Alimentation", "Supermarche"):    ("Vie Quotidienne",    "Alimentation"),
    ("Epargne",      "AV"):             ("Finances & Crédits", "Épargne & Investissement"),
    ("Epargne",      "Livret"):         ("Finances & Crédits", "Épargne & Investissement"),
    ("Logement",     "Assurance"):      ("Abonnements",        "Abonnements_autre"),
    ("Logement",     "Energie"):        ("Logement",           "Electricité & Eau"),
    ("Logement",     "Loyer"):          ("Logement",           "Loyer"),
    ("Logement",     "Telecom"):        ("Abonnements",        "Télécom & Internet"),
    ("Loisirs",      "Shopping"):       ("Loisirs",            "Sorties & Culture"),
    ("Loisirs",      "Sorties"):        ("Loisirs",            "Sorties & Culture"),
    ("Loisirs",      "Streaming"):      ("Abonnements",        "Streaming & Apps"),
    ("Loisirs",      "Voyage"):         ("Loisirs",            "Voyages & Weekend"),
    ("Sante",        "Consultation"):   ("Santé",              "Médecin & Examens"),
    ("Sante",        "Pharmacie"):      ("Santé",              "Pharmacie"),
    ("Transport",    "Carburant"):      ("Transport",          "Carburant"),
    ("Transport",    "Train"):          ("Transport",          "Taxi & Transports"),
    ("Transport",    "VTC"):            ("Transport",          "Taxi & Transports"),

    # Simplification v2 — Vie Quotidienne
    ("Vie Quotidienne", "Protéine"):         ("Vie Quotidienne", "Alimentation"),
    ("Vie Quotidienne", "Fruits & légumes"): ("Vie Quotidienne", "Alimentation"),

    # Simplification v2 — toutes catégories
    ("Revenu",            "Vente"):               ("Revenu",            "Freelance & Activités"),
    ("Revenu",            "Freelance"):            ("Revenu",            "Freelance & Activités"),
    ("Revenu",            "Bricolage"):            ("Revenu",            "Freelance & Activités"),
    ("Revenu",            "Allocation Familiale"): ("Revenu",            "Aides & Allocations"),
    ("Revenu",            "Remboursement"):        ("Revenu",            "Aides & Allocations"),
    ("Revenu",            "Dons"):                 ("Revenu",            "Aides & Allocations"),
    ("Revenu",            "Prime"):                ("Revenu",            "Prime & Bonus"),
    ("Revenu",            "Loyer"):                ("Revenu",            "Revenu_Autre"),
    ("Logement",          "Impôts"):               ("Logement",          "Charges & Taxes"),
    ("Logement",          "Logement_autre"):        ("Logement",          "Charges & Taxes"),
    ("Transport",         "Tramway & Bus"):         ("Transport",         "Taxi & Transports"),
    ("Transport",         "Taxi & Uber"):           ("Transport",         "Taxi & Transports"),
    ("Transport",         "Entretien & Lavage"):    ("Transport",         "Entretien & Réparation"),
    ("Loisirs",           "Sorties & Shopping"):    ("Loisirs",           "Sorties & Culture"),
    ("Loisirs",           "Ciné & Culture"):        ("Loisirs",           "Sorties & Culture"),
    ("Loisirs",           "Sport & Hobby"):         ("Loisirs",           "Sport & Bien-être"),
    ("Loisirs",           "Bien-être & Hygiène"):   ("Loisirs",           "Sport & Bien-être"),
    ("Abonnements",       "Streaming & TV"):        ("Abonnements",       "Streaming & Apps"),
    ("Abonnements",       "Logiciels & Cloud"):     ("Abonnements",       "Streaming & Apps"),
    ("Abonnements",       "Banque & Assur"):        ("Abonnements",       "Abonnements_autre"),
    ("Santé",             "Consultations"):         ("Santé",             "Médecin & Examens"),
    ("Santé",             "Analyses & Radio"):      ("Santé",             "Médecin & Examens"),
    ("Finances & Crédits","Crédit Conso ou Auto"):  ("Finances & Crédits","Crédit & Remboursement"),
    ("Finances & Crédits","Remboursement Dette"):   ("Finances & Crédits","Crédit & Remboursement"),
    ("Finances & Crédits","Épargne"):               ("Finances & Crédits","Épargne & Investissement"),
    ("Finances & Crédits","EPARGNE INVESTISSEMENT"):("Finances & Crédits","Épargne & Investissement"),
    ("Divers",            "Frais de dossier"):      ("Divers",            "Administratif"),
    ("Divers",            "Generale"):              ("Divers",            "Administratif"),
}


def run():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("─" * 60)
    print("MIGRATION RÉFÉRENTIEL — Finance SaaS v2")
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
    print(f"  REFERENTIEL   — {nb_ref} entrees")

    # ── Étape 2 : CATEGORIES ──────────────────────────────────────────────────
    nb_cat = 0
    for cat, sous, sens, freq, statut in REFERENTIEL:
        conn.execute("""
            INSERT OR IGNORE INTO CATEGORIES (Categorie, Sous_Categorie, Plafond)
            VALUES (?, ?, 0.0)
        """, (cat, sous))
        nb_cat += 1
    print(f"  CATEGORIES    — {nb_cat} paires (plafond 0 par defaut)")

    # ── Étape 3 : DICO_MATCHING ───────────────────────────────────────────────
    nb_dico = 0
    for (old_cat, old_sous), (new_cat, new_sous) in MAPPING.items():
        cur = conn.execute("""
            UPDATE DICO_MATCHING
            SET Categorie_Cible = ?, Sous_Categorie_Cible = ?
            WHERE Categorie_Cible = ? AND Sous_Categorie_Cible = ?
        """, (new_cat, new_sous, old_cat, old_sous))
        if cur.rowcount:
            print(f"   DICO: {old_cat}/{old_sous} -> {new_cat}/{new_sous}  ({cur.rowcount})")
            nb_dico += cur.rowcount
    print(f"  DICO_MATCHING — {nb_dico} mots-cles harmonises")

    # ── Étape 4 : nettoyer les vieilles entrées REFERENTIEL / CATEGORIES ──────
    valides = {(cat, sous) for cat, sous, *_ in REFERENTIEL}
    old_ref = conn.execute("SELECT Categorie, Sous_Categorie FROM REFERENTIEL").fetchall()
    nb_del = 0
    for row in old_ref:
        if (row[0], row[1]) not in valides:
            conn.execute("DELETE FROM REFERENTIEL WHERE Categorie=? AND Sous_Categorie=?",
                         (row[0], row[1]))
            conn.execute("DELETE FROM CATEGORIES WHERE Categorie=? AND Sous_Categorie=?",
                         (row[0], row[1]))
            nb_del += 1
    if nb_del:
        print(f"  Obsoletes supprimes : {nb_del}")

    conn.commit()
    conn.close()
    print("Migration terminee.")


if __name__ == "__main__":
    run()
