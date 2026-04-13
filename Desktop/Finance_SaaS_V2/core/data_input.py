"""
core/data_input.py — Logique centralisée de saisie et d'enregistrement.

Ce module isole toutes les opérations d'écriture (transactions, budgets, objectifs)
pour les rendre testables et réutilisables indépendamment de l'interface.

Exports principaux :
    enregistrer_transaction()   → appelle audit.recevoir() avec validation
    sauvegarder_budgets()       → écrit une liste de budgets en base
    onboarding_complet()        → marque l'onboarding comme terminé
    est_onboarding_fait()       → True si l'utilisateur a déjà configuré ses budgets
    lister_categories()         → lit toutes les catégories OUT de la BDD
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# TRANSACTIONS
# ─────────────────────────────────────────────────────────────────────────────

def enregistrer_transaction(
    audit,
    libelle: str,
    montant: float,
    sens: str,
    date_valeur: date,
    forcer: bool = False,
    source: str = "SAISIE",
) -> Dict[str, Any]:
    """
    Enregistre une transaction via l'AuditMiddleware.

    Retourne le dict résultat avec les clés :
        action  : "OK" | "CONFIRMER" | "BLOQUER" | "ERREUR"
        message : texte lisible
        categorie, sous_categorie, methode, score (si action == "OK")
    """
    libelle = libelle.strip()
    if not libelle:
        return {"action": "ERREUR", "erreur": "Libellé vide."}
    if montant <= 0:
        return {"action": "ERREUR", "erreur": "Montant doit être > 0."}
    if sens not in ("IN", "OUT"):
        return {"action": "ERREUR", "erreur": "Sens invalide (IN ou OUT)."}

    return audit.recevoir(libelle, montant, sens, date_valeur, forcer=forcer, source=source)


def enregistrer_transaction_categorisee(
    audit,
    libelle: str,
    montant: float,
    sens: str,
    categorie: str,
    sous_categorie: str,
    date_valeur: date,
    source: str = "ONBOARDING",
) -> None:
    """
    Écrit une transaction directement en base avec la catégorie connue,
    sans passer par le Trieur (classifier). Utilisé pour l'onboarding
    où catégorie et sous-catégorie sont déjà déterminées par le formulaire.
    """
    import uuid

    montant_abs   = abs(float(montant))
    montant_signe = -montant_abs if sens.upper() == "OUT" else montant_abs
    now           = datetime.now()
    id_unique     = f"{now.strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:6]}"

    with audit.db.connexion() as conn:
        conn.execute(
            """INSERT INTO TRANSACTIONS
               (ID_Unique, Date_Saisie, Date_Valeur, Libelle, Montant,
                Sens, Categorie, Sous_Categorie, Statut, Source, user_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT (ID_Unique, user_id) DO NOTHING""",
            (
                id_unique,
                now.strftime("%Y-%m-%d %H:%M:%S"),
                date_valeur.strftime("%Y-%m-%d"),
                libelle.strip(),
                montant_signe,
                sens.upper(),
                categorie.strip(),
                sous_categorie.strip(),
                "VALIDE",
                source,
                audit.user_id,
            )
        )


# ─────────────────────────────────────────────────────────────────────────────
# BUDGETS & ONBOARDING
# ─────────────────────────────────────────────────────────────────────────────

PREF_ONBOARDING_KEY = "onboarding_done"


def est_onboarding_fait(audit) -> bool:
    """
    Retourne True si l'utilisateur a déjà complété l'onboarding.
    Stocké dans PREFERENCES sous la clé 'onboarding_done'.
    """
    return audit.get_preference(PREF_ONBOARDING_KEY, "0") == "1"


def marquer_onboarding_fait(audit) -> None:
    """Persiste le flag d'onboarding terminé."""
    audit.set_preference(PREF_ONBOARDING_KEY, "1")


def sauvegarder_budgets(
    audit,
    budgets: List[Dict[str, Any]],
    mois: Optional[str] = None,
) -> int:
    """
    Enregistre une liste de budgets en base.

    Paramètres :
        audit   — instance AuditMiddleware
        budgets — liste de dicts :
                  [{"categorie": str, "sous_categorie": str, "plafond": float}, ...]
        mois    — format "MM/YYYY". Si None, écrit dans CATEGORIES (plafond permanent).
                  Si fourni, écrit dans BUDGETS_MENSUELS (plafond du mois uniquement).

    Retourne le nombre de lignes écrites.
    """
    count = 0
    for b in budgets:
        cat    = str(b.get("categorie", "")).strip()
        sous   = str(b.get("sous_categorie", "")).strip()
        plafond = float(b.get("plafond", 0.0))

        if not cat or not sous or plafond < 0:
            continue

        if mois:
            audit.db.set_budget_mensuel(mois, cat, sous, plafond, audit.user_id)
        else:
            # Plafond permanent dans CATEGORIES
            with audit.db.connexion() as conn:
                conn.execute(
                    "UPDATE CATEGORIES SET Plafond = ? WHERE Categorie = ? AND Sous_Categorie = ?",
                    (round(plafond, 2), cat, sous)
                )
        count += 1

    return count


def lister_categories(audit) -> List[Dict[str, Any]]:
    """
    Retourne toutes les catégories de dépenses (Sens=OUT).

    Stratégie en cascade :
      1. CATEGORIES + REFERENTIEL (si peuplés)
      2. Sinon : paires distinctes depuis DICO_MATCHING (toujours présent)

    Format retourné :
        [{"categorie": str, "sous_categorie": str, "plafond_actuel": float}, ...]
    """
    try:
        with audit.db.connexion() as conn:
            # Tentative 1 — tables CATEGORIES + REFERENTIEL
            nb_cat = conn.execute("SELECT COUNT(*) FROM CATEGORIES").fetchone()[0]
            nb_ref = conn.execute("SELECT COUNT(*) FROM REFERENTIEL").fetchone()[0]

            if nb_cat > 0 and nb_ref > 0:
                rows = conn.execute(
                    """
                    SELECT c.Categorie, c.Sous_Categorie, c.Plafond
                    FROM CATEGORIES c
                    JOIN REFERENTIEL r
                      ON c.Categorie = r.Categorie
                     AND c.Sous_Categorie = r.Sous_Categorie
                    WHERE r.Sens = 'OUT'
                    ORDER BY c.Categorie, c.Sous_Categorie
                    """
                ).fetchall()
                return [
                    {
                        "categorie":      r[0],
                        "sous_categorie": r[1],
                        "plafond_actuel": float(r[2] or 0.0),
                    }
                    for r in rows
                ]

            # Tentative 2 — DICO_MATCHING (fallback universel)
            rows = conn.execute(
                """
                SELECT DISTINCT
                    dm.Categorie_Cible      AS Categorie,
                    dm.Sous_Categorie_Cible AS Sous_Categorie,
                    COALESCE(c.Plafond, 0.0) AS Plafond
                FROM DICO_MATCHING dm
                LEFT JOIN CATEGORIES c
                  ON c.Categorie = dm.Categorie_Cible
                 AND c.Sous_Categorie = dm.Sous_Categorie_Cible
                WHERE dm.Sens = 'OUT'
                  AND dm.Categorie_Cible   != ''
                  AND dm.Sous_Categorie_Cible != ''
                ORDER BY dm.Categorie_Cible, dm.Sous_Categorie_Cible
                """
            ).fetchall()
            return [
                {
                    "categorie":      r[0],
                    "sous_categorie": r[1],
                    "plafond_actuel": float(r[2] or 0.0),
                }
                for r in rows
            ]
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# OBJECTIFS
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# REVENUS
# ─────────────────────────────────────────────────────────────────────────────

def sauvegarder_revenus(
    audit,
    salaire: float,
    extras: list,          # [{"nom": str, "montant": float}, ...]
) -> None:
    """
    Persiste les revenus mensuels attendus dans PREFERENCES.

    Clés utilisées :
        revenu_salaire        — float (DH)
        revenu_extras_json    — JSON list [{"nom": str, "montant": float}]
        revenu_total_attendu  — float, somme totale (utile pour le Coach)
    """
    import json
    total = salaire + sum(float(e.get("montant", 0)) for e in extras)
    audit.set_preference("revenu_salaire",       str(round(salaire, 2)))
    audit.set_preference("revenu_extras_json",   json.dumps(extras, ensure_ascii=False))
    audit.set_preference("revenu_total_attendu", str(round(total, 2)))


def lire_revenus(audit) -> dict:
    """
    Retourne les revenus configurés.

    Format :
        {
            "salaire":  float,
            "extras":   [{"nom": str, "montant": float}, ...],
            "total":    float,
        }
    """
    import json
    salaire = float(audit.get_preference("revenu_salaire", "0") or 0)
    try:
        extras = json.loads(audit.get_preference("revenu_extras_json", "[]") or "[]")
    except Exception:
        extras = []
    total = float(audit.get_preference("revenu_total_attendu", "0") or 0)
    return {"salaire": salaire, "extras": extras, "total": total}


def creer_objectif(
    audit,
    nom: str,
    montant_cible: float,
    date_cible: str,
) -> Dict[str, Any]:
    """
    Crée un objectif d'épargne et retourne le résultat d'audit.

    Paramètres :
        nom           — nom de l'objectif (ex: "Vacances Portugal")
        montant_cible — montant cible en DH
        date_cible    — format "MM/YYYY" ou "YYYY-MM-DD"
    """
    nom = nom.strip()
    if not nom:
        return {"erreur": "Nom d'objectif vide."}
    if montant_cible <= 0:
        return {"erreur": "Montant cible doit être > 0."}

    try:
        return audit.creer_objectif(nom, montant_cible, date_cible)
    except Exception as e:
        return {"erreur": str(e)}
