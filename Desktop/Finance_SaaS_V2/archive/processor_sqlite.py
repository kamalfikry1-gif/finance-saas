"""
PROJET : GESTIONNAIRE DE BUDGET INTELLIGENT
BLOCS 0 à 3 : STRUCTURES, CONNEXION, NETTOYAGE & CLASSIFICATION
"""

import re
import logging
import time
import unicodedata
from datetime import datetime, date, timedelta
from typing import Any, Optional, List, Dict, Tuple
from dataclasses import dataclass, field

import pandas as pd
# ═══ MIGRATION SQLITE : Remplace gspread par sqlite_connector ═══
# import gspread  # Plus nécessaire
# from google.oauth2.service_account import Credentials  # Plus nécessaire
from sqlite_connector import SQLiteConnector, SQLiteCell
from rapidfuzz import fuzz, process as fuzz_process

# ─────────────────────────────────────────────────────────────────────────────
# BLOC 0 : CONFIGURATION ET DATACLASSES
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("BUDGET_ENGINE")

FUZZY_THRESHOLD      = 75
SANTE_SEUIL_DANGER   = 10
SANTE_SEUIL_OK       = 30
FANTOME_SEUIL_JOURS  = 30

@dataclass
class Transaction:
    date: datetime
    jour_prelevement: int
    mot_cle: str
    montant: float
    sous_categorie: str = ""
    categorie: str = ""
    id_unique: str = ""
    sens: str = "OUT"
    source: str = "SAISIE"

    def __post_init__(self):
        try:
            self.montant = abs(float(self.montant))
            if self.sens.upper() == "OUT":
                self.montant = -self.montant
        except (ValueError, TypeError):
            self.montant = 0.0
            logger.warning(f"⚠️ Montant invalide pour '{self.mot_cle}'")

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
    montant_cumule_dormant: float = 0.0

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
                f"← '{self.mot_cle_dico}' (score {self.score:.0f}%)")

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

# ─────────────────────────────────────────────────────────────────────────────
# BLOC 1 : CONNEXION — MIGRATION SQLITE
# ─────────────────────────────────────────────────────────────────────────────

# ═══ MIGRATION SQLITE : La classe GoogleSheetsConnector est remplacée par SQLiteConnector ═══
# L'alias permet de garder le même nom partout dans le code existant.
GoogleSheetsConnector = SQLiteConnector

# Note pour l'instanciation :
#   AVANT : connector = GoogleSheetsConnector(spreadsheet_id, credentials_path)
#   APRÈS : connector = GoogleSheetsConnector("finance_saas.db")

# ─────────────────────────────────────────────────────────────────────────────
# BLOC 2 : DOUANE
# ─────────────────────────────────────────────────────────────────────────────

class Douane:
    @staticmethod
    def supprimer_accents(texte: str) -> str:
        nfkd = unicodedata.normalize("NFKD", str(texte))
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    @classmethod
    def normaliser_texte(cls, texte: str) -> str:
        if pd.isna(texte) or not str(texte).strip(): return ""
        t = str(texte).strip().upper()
        t = cls.supprimer_accents(t)
        t = re.sub(r"[^\w\s\-\'\.\/]", " ", t)
        t = re.sub(r"\s+", " ", t)
        return t.strip()

    @staticmethod
    def normaliser_montant(valeur: Any) -> Optional[float]:
        if pd.isna(valeur) or str(valeur).strip() == "": return None
        s = str(valeur).strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
        if s.count(".") > 1:
            parts = s.rsplit(".", 1)
            s = parts[0].replace(".", "") + "." + parts[1]
        try: return round(float(s), 2)
        except ValueError: return None

    @staticmethod
    def normaliser_date(valeur: Any) -> Optional[date]:
        if pd.isna(valeur) or str(valeur).strip() == "": return None
        s = str(valeur).strip()
        formats = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d.%m.%Y", "%Y/%m/%d"]
        for fmt in formats:
            try: return datetime.strptime(s, fmt).date()
            except ValueError: continue
        return None

    @classmethod
    def nettoyer_dataframe(cls, df: pd.DataFrame, mapping_colonnes: Dict[str, str]) -> pd.DataFrame:
        df = df.copy()
        for col, type_col in mapping_colonnes.items():
            if col not in df.columns: continue
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
                    if t in ("IN", "ENTREE", "REVENU", "+"): return "IN"
                    if t in ("OUT", "SORTIE", "DEPENSE", "-"): return "OUT"
                    return ""
                df[col] = df[col].apply(parse_sens)
                
        df.dropna(how="all", inplace=True)
        return df

    @classmethod
    def charger_referentiel(cls, df_brut: pd.DataFrame) -> pd.DataFrame:
        mapping = {
            "Categorie":      "texte",
            "Sous_Categorie": "texte",
            "Sens":           "sens",
            "Frequence":      "texte",
            "Statut":         "texte",
        }
        return cls.nettoyer_dataframe(df_brut, mapping)

    @classmethod
    def charger_dico(cls, df_brut: pd.DataFrame) -> pd.DataFrame:
        mapping = {
            "Sens":                 "sens",
            "Mot_Cle":              "texte",
            "Categorie_Cible":      "texte",
            "Sous_Categorie_Cible": "texte",
        }
        df = cls.nettoyer_dataframe(df_brut, mapping)
        return df[df["Mot_Cle"].str.len() > 0].copy()

    @classmethod
    def charger_config_fixe(cls, df_brut: pd.DataFrame) -> List["DepenseFixe"]:
        """
        Charge et valide la feuille CONFIG_FIXE.
        Colonnes : Nom_Fixe | Montant | Jour | Categorie | Sous_Categorie | Plafond_Mensuel
        Retourne une liste de DepenseFixe (lignes invalides ignorées avec warning).
        """
        mapping = {
            "Nom_Fixe":        "texte",
            "Categorie":       "texte",
            "Sous_Categorie":  "texte",
            "Montant":         "montant",
            "Plafond_Mensuel": "montant",
        }
        df = cls.nettoyer_dataframe(df_brut, mapping)
        items: List["DepenseFixe"] = []
        for _, row in df.iterrows():
            nom = str(row.get("Nom_Fixe", "")).strip()
            if not nom:
                continue
            try:
                jour = int(float(str(row.get("Jour", 1) or 1)))
            except (ValueError, TypeError):
                logger.warning(f"⚠️ CONFIG_FIXE — Jour invalide pour '{nom}', ignoré.")
                continue
            montant = row.get("Montant")
            if montant is None or pd.isna(montant):
                logger.warning(f"⚠️ CONFIG_FIXE — Montant manquant pour '{nom}', ignoré.")
                continue
            plafond = row.get("Plafond_Mensuel")
            plafond = float(plafond) if (plafond is not None and not pd.isna(plafond)) else 0.0
            items.append(DepenseFixe(
                nom_fixe        = nom,
                montant         = float(montant),
                jour            = jour,
                categorie       = str(row.get("Categorie", "")).strip(),
                sous_categorie  = str(row.get("Sous_Categorie", "")).strip(),
                plafond_mensuel = plafond,
            ))
        logger.info(f"✅ CONFIG_FIXE — {len(items)} dépense(s) fixe(s) chargée(s).")
        return items

# ─────────────────────────────────────────────────────────────────────────────
# BLOC 3 : TRIEUR
# ─────────────────────────────────────────────────────────────────────────────

SEUIL_AUTO              = 85
SEUIL_FUZZY_MIN         = 50
SEUIL_FUSION_INCONNU    = 90
MIN_LETTRES_PARTIEL     = 5
NB_CANDIDATS_FUZZY      = 3
BLACKLIST_PARTIEL       = {"MARKET", "SHOP", "STORE", "ACHAT", "PAIEMENT", "PAYMENT", "ONLINE", "WEB", "APP", "SERVICE"}

NOM_FEUILLE_DICO         = "dico"          
NOM_FEUILLE_A_CLASSIFIER = "a_classifier"  

class Trieur:
    def __init__(
        self,
        df_dico: pd.DataFrame,
        df_referentiel: pd.DataFrame,
        connexion=None,
        seuil_auto: int = SEUIL_AUTO,
        seuil_fuzzy_min: int = SEUIL_FUZZY_MIN,
        on_nouveau_mot_cle=None,
    ):
        """
        Paramètres :
          connexion        — GoogleSheetsConnector (optionnel : si None, persistence désactivée)
          on_nouveau_mot_cle — callback(ligne: List) appelé lors d'un apprentissage.
                              Prioritaire sur connexion si fourni. Utile pour les tests.
        """
        self.seuil_auto       = seuil_auto
        self.seuil_fuzzy_min  = seuil_fuzzy_min
        self.connexion        = connexion
        self._on_nouveau_mot_cle = on_nouveau_mot_cle
        self._construire_index(df_dico, df_referentiel)
        self._cache_a_classifier: List[Dict[str, Any]] = []
        self._charger_cache_a_classifier()

    def __enter__(self) -> "Trieur": return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.flush_a_classifier()
        return False

    def _construire_index(self, df_dico: pd.DataFrame, df_ref: pd.DataFrame):
        # Dico fuzzy  : {(mot_norm, sens): (cat, scat)}  — mots >= 4 chars
        # Dico exact  : {(mot_norm, sens): (cat, scat)}  — mots <  4 chars (acronymes)
        self._dico:       Dict[Tuple[str, str], Tuple[str, str]] = {}
        self._dico_exact: Dict[Tuple[str, str], Tuple[str, str]] = {}
        self._sens_map:   Dict[Tuple[str, str], str] = {}

        for _, row in df_ref.iterrows():
            cat = str(row.get("Categorie", "")).strip()
            sub = str(row.get("Sous_Categorie", "")).strip()
            sens = str(row.get("Sens", "OUT")).strip().upper()
            if cat:
                self._sens_map[(cat, sub)] = sens if sens in ("IN", "OUT") else "OUT"

        for _, row in df_dico.iterrows():
            mot_brut = str(row.get("Mot_Cle", "")).strip()
            cat = str(row.get("Categorie_Cible", "")).strip()
            sub = str(row.get("Sous_Categorie_Cible", "")).strip()
            sens_dico = str(row.get("Sens", "")).strip().upper()

            # Le sens du référentiel prime TOUJOURS sur le sens saisi dans le DICO
            sens_ref = self._sens_map.get((cat, sub), "")
            if sens_ref in ("IN", "OUT"):
                sens_dico = sens_ref
            elif sens_dico not in ("IN", "OUT"):
                sens_dico = "OUT"

            mot_norm = Douane.normaliser_texte(mot_brut)
            if not mot_norm or not cat:
                continue
            if len(mot_norm) >= 4:
                self._dico[(mot_norm, sens_dico)] = (cat, sub)
            else:
                # Acronyme court → matching exact uniquement, jamais dans le fuzzy
                self._dico_exact[(mot_norm, sens_dico)] = (cat, sub)

    def classifier(self, mot_cle: str, sens_transaction: str = "OUT") -> ResultatClassification:
        mot_norm = Douane.normaliser_texte(mot_cle)
        sens_transaction = sens_transaction.upper()

        if not mot_norm:
            return self._repli_inconnu(mot_cle, "", sens_transaction)

        # 🟢 LE FILTRE MAGIQUE : On ne regarde QUE le bon tiroir
        dico_autorise = {
            m: (cat, scat) 
            for (m, s), (cat, scat) in self._dico.items() 
            if s == sens_transaction
        }
        mots_cibles = list(dico_autorise.keys())

        # 1. EXACT long (>= 4 chars, tiroir autorisé)
        if mot_norm in dico_autorise:
            cat, scat = dico_autorise[mot_norm]
            return ResultatClassification(cat, scat, "EXACT", 100.0, sens_transaction, "AUTO", [], mot_cle)

        # 1b. EXACT court (< 4 chars — acronymes, jamais dans le fuzzy)
        #     L'acronyme doit être un MOT ENTIER dans la transaction (pas une sous-chaîne)
        mots_transaction = set(mot_norm.split())
        for (acronyme, s), (cat, scat) in self._dico_exact.items():
            if s == sens_transaction and acronyme in mots_transaction:
                return ResultatClassification(cat, scat, "EXACT_COURT", 100.0, sens_transaction, "AUTO", [], mot_cle)

        # 2. NEAR-AUTO (uniquement parmi les mots autorisés)
        if mots_cibles:
            res_near = fuzz_process.extract(mot_norm, mots_cibles, scorer=fuzz.WRatio, limit=1)
            if res_near and res_near[0][1] >= self.seuil_auto:
                cle_trouvee, score, _ = res_near[0]
                cat, scat = dico_autorise[cle_trouvee]
                return ResultatClassification(cat, scat, "NEAR_AUTO", score, sens_transaction, "AUTO", [], mot_cle)

        # 3. PARTIEL (Restauré avec le dico_autorise)
        res_partiel = self._matching_partiel(mot_norm, mot_cle, dico_autorise, sens_transaction)
        if res_partiel: return res_partiel

        # 4. FUZZY → repli selon le sens
        if mots_cibles:
            candidats = []
            res_fuzzy = fuzz_process.extract(mot_norm, mots_cibles, scorer=fuzz.WRatio, limit=NB_CANDIDATS_FUZZY)
            for rang, (cle, score, _) in enumerate(res_fuzzy, start=1):
                if score >= self.seuil_fuzzy_min:
                    cat, scat = dico_autorise[cle]
                    candidats.append(CandidatClassification(rang, cle, cat, scat, sens_transaction, float(score)))
            if candidats:
                if sens_transaction == "IN":
                    # IN + FUZZY → repli automatique Revenu/Revenu_autre
                    return ResultatClassification("Revenu", "Revenu_autre", "AUTO_IN", 100.0, "IN", "AUTO", [], mot_cle)
                else:
                    # OUT + FUZZY → Divers/Divers_Autre + ajout A_CLASSIFIER
                    self._ajouter_ou_fusionner_a_classifier(mot_cle)
                    return ResultatClassification("Divers", "Divers_Autre", "FUZZY", candidats[0].score, "OUT", "AUTO", candidats, mot_cle)

        # 5. REPLI (Auto Revenu pour IN, A_CLASSIFIER pour OUT)
        return self._repli_inconnu(mot_cle, mot_norm, sens_transaction)

    def confirmer(self, resultat: ResultatClassification, index_choix: Optional[int] = None) -> ResultatClassification:
        if index_choix is not None and 0 <= index_choix < len(resultat.candidats):
            choix = resultat.candidats[index_choix]
            self.apprendre(resultat.mot_cle_original, choix.categorie, choix.sous_categorie, choix.sens)
            return ResultatClassification(choix.categorie, choix.sous_categorie, "FUZZY_VALIDÉ", choix.score, choix.sens, "AUTO", [], resultat.mot_cle_original)
        
        return self._repli_inconnu(resultat.mot_cle_original, "", resultat.sens)

    def apprendre(self, mot_cle: str, categorie: str, sous_categorie: str, sens: str = "OUT"):
        mot_norm = Douane.normaliser_texte(mot_cle)
        if not mot_norm: return

        # Mise à jour du dictionnaire en mémoire
        self._dico[(mot_norm, sens)] = (categorie, sous_categorie)

        # Persistence : callback prioritaire, sinon connexion directe
        ligne = [sens, mot_cle, categorie, sous_categorie]
        if self._on_nouveau_mot_cle:
            self._on_nouveau_mot_cle(ligne)
        elif self.connexion:
            self.connexion.ecrire_ligne(NOM_FEUILLE_DICO, ligne)

    def _matching_partiel(self, mot_norm: str, mot_cle_original: str, dico_autorise: dict, sens_transaction: str) -> Optional[ResultatClassification]:
        tokens_saisis = set(mot_norm.split()) | {mot_norm}
        meilleur_cle_dico = None
        meilleur_longueur = 0

        for token in tokens_saisis:
            if len(token) < MIN_LETTRES_PARTIEL or token in BLACKLIST_PARTIEL: continue
            for cle_dico in dico_autorise.keys():
                if len(cle_dico) < MIN_LETTRES_PARTIEL or cle_dico in BLACKLIST_PARTIEL: continue
                if (token in cle_dico or cle_dico in token) and len(cle_dico) > meilleur_longueur:
                    meilleur_longueur = len(cle_dico)
                    meilleur_cle_dico = cle_dico

        if meilleur_cle_dico:
            cat, sub = dico_autorise[meilleur_cle_dico]
            return ResultatClassification(cat, sub, "PARTIEL", 90.0, sens_transaction, "AUTO", [], mot_cle_original)
        return None

    def _repli_inconnu(self, mot_cle_original: str, mot_norm: str, sens_transaction: str = "OUT") -> ResultatClassification:
        if sens_transaction == "IN":
            return ResultatClassification("Revenu", "Revenu_autre", "AUTO_IN", 100.0, "IN", "AUTO", [], mot_cle_original)

        self._ajouter_ou_fusionner_a_classifier(mot_cle_original)
        return ResultatClassification("MOT_CLE_INCONNU", "A_CLASSIFIER", "INCONNU", 0.0, sens_transaction, "INCONNU", [], mot_cle_original)

    def _ajouter_ou_fusionner_a_classifier(self, mot_cle: str):
        today = date.today().strftime("%d/%m/%Y")
        if self._cache_a_classifier:
            mots_cache = [e["mot_cle"] for e in self._cache_a_classifier]
            res = fuzz_process.extract(mot_cle, mots_cache, scorer=fuzz.WRatio, limit=1)
            if res and res[0][1] >= SEUIL_FUSION_INCONNU:
                for entry in self._cache_a_classifier:
                    if entry["mot_cle"] == res[0][0]:
                        entry["nb_occurrences"] += 1
                        entry["_dirty"] = True
                        return
        self._cache_a_classifier.append({
            "mot_cle": mot_cle, "categorie_choisie": "", "date_ajout": today,
            "nb_occurrences": 1, "ligne_index": 0, "_dirty": True, "_new": True
        })

    def _charger_cache_a_classifier(self):
        if not self.connexion: return
        sheet = self.connexion.get_sheet(NOM_FEUILLE_A_CLASSIFIER)
        if not sheet: return
        try:
            records = sheet.get_all_records(default_blank="")
            for idx, row in enumerate(records, start=2):
                mot = str(row.get("Mot_Cle_Inconnu", "")).strip()
                if mot:
                    self._cache_a_classifier.append({
                        "mot_cle": mot, "categorie_choisie": str(row.get("Categorie_Choisie", "")).strip(),
                        "date_ajout": str(row.get("Date_Ajout", "")).strip(),
                        "nb_occurrences": int(row.get("Nb_Occurrences", 1) or 1),
                        "ligne_index": idx, "_dirty": False, "_new": False
                    })
        except Exception as e:
            logger.warning(f"Erreur chargement A_CLASSIFIER: {e}")

    def flush_a_classifier(self):
        dirty = [e for e in self._cache_a_classifier if e["_dirty"]]
        if not dirty: return
        if not self.connexion: return

        sheet = self.connexion.get_sheet(NOM_FEUILLE_A_CLASSIFIER)
        if not sheet: return

        nouvelles = [e for e in dirty if e["_new"]]
        modifiees = [e for e in dirty if not e["_new"]]

        try:
            if nouvelles:
                rows = [[e["mot_cle"], e["categorie_choisie"], e["date_ajout"], e["nb_occurrences"]] for e in nouvelles]
                sheet.append_rows(rows, value_input_option="USER_ENTERED")
                for e in nouvelles: e["_dirty"] = e["_new"] = False
            
            if modifiees:
                cells = [SQLiteCell(row=e["ligne_index"], col=4, value=e["nb_occurrences"]) for e in modifiees]
                sheet.update_cells(cells, value_input_option="USER_ENTERED")
                for e in modifiees: e["_dirty"] = False
        except Exception as e:
            logger.error(f"❌ flush_a_classifier échoué : {e}")

    def stats_cache(self) -> Dict[str, int]:
        total = len(self._cache_a_classifier)
        dirty = sum(1 for e in self._cache_a_classifier if e["_dirty"])
        nouvelles = sum(1 for e in self._cache_a_classifier if e["_new"])
        return {"total": total, "dirty": dirty, "nouvelles_a_ecrire": nouvelles}

# ─────────────────────────────────────────────────────────────────────────────
# BLOC 4 : COMPTABLE
# ─────────────────────────────────────────────────────────────────────────────

NOM_FEUILLE_TRANSACTIONS  = "transactions"
NOM_FEUILLE_REFERENTIEL   = "referentiel"
NOM_FEUILLE_EPARGNE       = "epargne"
FENETRE_DOUBLON_SECONDES  = 120   # Anti-double clic : 2 minutes
TTL_CACHE_TRANSACTIONS    = 30    # Secondes — durée de vie du cache doublon

# Fallback hardcodé — utilisé UNIQUEMENT si la ligne est introuvable dans REFERENTIEL
# (Douane.normaliser_texte des valeurs réelles du Google Sheet)
_CAT_EPARGNE_FALLBACK  = "FINANCES CREDITS"       # normaliser_texte("Finances & Crédits")
_SCAT_EPARGNE_FALLBACK = "EPARGNE INVESTISSEMENT" # normaliser_texte("Épargne & Investissement")

# ── 7 colonnes EXACTES — ordre strict, aucune colonne supplémentaire ────────
COL_TRANSACTIONS = [
    "ID_Unique",      # 1
    "Date_Saisie",    # 2  timestamp système
    "Date_Valeur",    # 3  date choisie par l'utilisateur
    "Mot_Cle",        # 4  description nettoyée
    "Montant",        # 5  nombre pur signé (- dépense, + revenu)
    "Categorie",      # 6
    "Sous_Categorie", # 7
]


@dataclass
class EcritureComptable:
    """Représente exactement une ligne de l'onglet TRANSACTIONS."""
    id_unique:      str
    date_saisie:    str
    date_valeur:    date
    mot_cle:        str
    montant:        float   # signé : négatif OUT, positif IN
    categorie:      str
    sous_categorie: str


class ComptableBudget:
    """
    BLOC 4 — Comptable Budget
    ─────────────────────────
    Reçoit (date_valeur, description_brute, montant, classification)
    et exécute les écritures dans Google Sheets.

    Responsabilités :
      · Génération ID unique  AAAAMMJJ_HHMMSS_XX
      · Vérification doublon  (fenêtre 2 min)
      · Écriture TRANSACTIONS (7 colonnes strictes)
      · Mise à jour REFERENTIEL  (Compteur_N + Montant_Cumule)
      · Récupération flux récent  get_flux_recent()
    """

    def __init__(self, connexion: GoogleSheetsConnector, referentiel_verrouille: bool = True):
        self.connexion = connexion
        self.referentiel_verrouille = referentiel_verrouille
        self._compteur_seconde: Dict[str, int] = {}
        # Cache TTL pour la détection doublon (évite un appel Sheets par transaction)
        self._cache_transactions: Optional[pd.DataFrame] = None
        self._cache_transactions_ts: float = 0.0
        # Identifiants épargne chargés dynamiquement depuis REFERENTIEL
        self._cat_epargne, self._scat_epargne = self._charger_ids_epargne()

    # ─────────────────────────────────────────────────────────────────────────
    # 1. GÉNÉRATION ID UNIQUE
    # ─────────────────────────────────────────────────────────────────────────

    def _generer_id(self, dt: Optional[datetime] = None) -> str:
        """Format AAAAMMJJ_HHMMSS_XX — XX s'incrémente à la même seconde.
        Le dict est réinitialisé à chaque nouvelle seconde : pas de fuite mémoire."""
        if dt is None:
            dt = datetime.now()
        base  = dt.strftime("%Y%m%d_%H%M%S")
        count = self._compteur_seconde.get(base, 0) + 1
        # On ne conserve QUE la seconde en cours — les anciennes clés sont purgées
        self._compteur_seconde = {base: count}
        return f"{base}_{count:02d}"

    # ─────────────────────────────────────────────────────────────────────────
    # 2. PRÉVENTION DOUBLON
    # ─────────────────────────────────────────────────────────────────────────

    def _get_transactions_cached(self) -> pd.DataFrame:
        """Retourne TRANSACTIONS depuis le cache en mémoire (TTL = TTL_CACHE_TRANSACTIONS s).
        Évite un appel Google Sheets à chaque vérification de doublon."""
        now = time.time()
        if (self._cache_transactions is None
                or (now - self._cache_transactions_ts) > TTL_CACHE_TRANSACTIONS):
            self._cache_transactions    = self.connexion.load_sheet(NOM_FEUILLE_TRANSACTIONS)
            self._cache_transactions_ts = now
        return self._cache_transactions

    def _invalider_cache_transactions(self):
        """À appeler après chaque écriture pour forcer un rechargement au prochain doublon."""
        self._cache_transactions    = None
        self._cache_transactions_ts = 0.0

    def _est_doublon(self, date_valeur: date, mot_cle: str, montant_abs: float) -> bool:
        """Retourne True si (Date_Valeur + Mot_Cle + |Montant|) est déjà présent
        dans la fenêtre des 2 dernières minutes."""
        df = self._get_transactions_cached()
        if df.empty:
            return False

        fenetre  = datetime.now() - timedelta(seconds=FENETRE_DOUBLON_SECONDES)
        mot_norm = Douane.normaliser_texte(mot_cle)

        for _, row in df.iterrows():
            dt_saisie = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
                try:
                    dt_saisie = datetime.strptime(str(row.get("Date_Saisie", "")).strip(), fmt)
                    break
                except ValueError:
                    continue
            if dt_saisie is None or dt_saisie < fenetre:
                continue

            dv_row  = Douane.normaliser_date(str(row.get("Date_Valeur", "")).strip())
            mot_row = Douane.normaliser_texte(str(row.get("Mot_Cle", "")))
            mnt_row = Douane.normaliser_montant(row.get("Montant", ""))

            if (dv_row == date_valeur
                    and mot_row == mot_norm
                    and mnt_row is not None
                    and abs(abs(mnt_row) - montant_abs) < 0.01):
                return True
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # 3. CONSTRUCTION LIGNE (7 colonnes strictes)
    # ─────────────────────────────────────────────────────────────────────────

    def _ligne_transaction(self, e: EcritureComptable) -> List[Any]:
        dv_str = (e.date_valeur.strftime("%d/%m/%Y")
                  if isinstance(e.date_valeur, date) else str(e.date_valeur))
        # Ordre strict : ID | Date_Saisie | Date_Valeur | Mot_Cle | Montant | Cat | S/Cat
        return [
            e.id_unique,
            e.date_saisie,
            dv_str,
            e.mot_cle,
            round(e.montant, 2),
            e.categorie,
            e.sous_categorie,
        ]

    # ─────────────────────────────────────────────────────────────────────────
    # 4. MISE À JOUR RÉFÉRENTIEL
    # ─────────────────────────────────────────────────────────────────────────

    def _maj_referentiel(self, sous_categorie: str, montant_abs: float, categorie: str = "", sens: str = "OUT"):
        """
        Trouve la ligne correspondant à sous_categorie dans REFERENTIEL et
        incrémente Compteur_N (+1) et Montant_Cumule (+montant_abs).
        Si la sous-catégorie est absente, une nouvelle ligne est ajoutée automatiquement.
        En cas d'échec, log une erreur sans faire planter le script.
        """
        try:
            ws = self.connexion.get_sheet(NOM_FEUILLE_REFERENTIEL)
            if ws is None:
                logger.error("❌ REFERENTIEL introuvable — mise à jour ignorée.")
                return

            # Lire toutes les données avec les en-têtes
            donnees   = ws.get_all_values()
            if not donnees:
                logger.error("❌ REFERENTIEL vide — mise à jour ignorée.")
                return

            en_tetes  = donnees[0]
            sous_cat_norm = Douane.normaliser_texte(sous_categorie)

            # Trouver les indices de colonnes par nom (robuste aux réorganisations)
            try:
                idx_sous_cat      = en_tetes.index("Sous_Categorie")
                idx_compteur      = en_tetes.index("Compteur_N")
                idx_montant_cumul = en_tetes.index("Montant_Cumule")
            except ValueError as e:
                logger.error(f"❌ Colonne manquante dans REFERENTIEL : {e}")
                return

            # Chercher la ligne correspondante (index base-1 pour gspread)
            ligne_trouvee = None
            for i, ligne in enumerate(donnees[1:], start=2):
                val_sc = Douane.normaliser_texte(ligne[idx_sous_cat] if idx_sous_cat < len(ligne) else "")
                if val_sc == sous_cat_norm:
                    ligne_trouvee = (i, ligne)
                    break

            if ligne_trouvee is None:
                if self.referentiel_verrouille:
                    logger.warning(
                        f"⚠️ REFERENTIEL verrouillé — '{sous_categorie}' absente, aucune création."
                    )
                    return
                nouvelle_ligne = [""] * len(en_tetes)
                mapping = {
                    "Categorie":      categorie,
                    "Sous_Categorie": sous_categorie,
                    "Sens":           sens,
                    "Frequence":      "VARIABLE",
                    "Statut":         "ACTIF",
                    "Compteur_N":     1,
                    "Montant_Cumule": round(montant_abs, 2),
                }
                for col, val in mapping.items():
                    if col in en_tetes:
                        nouvelle_ligne[en_tetes.index(col)] = val
                ws.append_row(nouvelle_ligne)
                logger.info(f"✅ REFERENTIEL — nouvelle entrée : '{categorie}' / '{sous_categorie}' | Compteur_N=1 | Montant_Cumule={round(montant_abs, 2)}")
                return

            num_ligne, data = ligne_trouvee

            # Lire les valeurs actuelles (défaut 0 si vide)
            try:
                compteur_actuel = int(float(data[idx_compteur] or 0))
            except (ValueError, IndexError):
                compteur_actuel = 0
            try:
                cumul_actuel = float(str(data[idx_montant_cumul] or 0).replace(",", "."))
            except (ValueError, IndexError):
                cumul_actuel = 0.0

            # Écriture atomique des deux cellules en un seul appel API
            col_compteur = idx_compteur      + 1  # base-1 pour gspread
            col_cumul    = idx_montant_cumul + 1

            ws.update_cells([
                SQLiteCell(num_ligne, col_compteur, compteur_actuel + 1),
                SQLiteCell(num_ligne, col_cumul,    round(cumul_actuel + montant_abs, 2)),
            ])

            logger.info(
                f"📊 REFERENTIEL mis à jour — '{sous_categorie}' : "
                f"Compteur_N={compteur_actuel + 1} | "
                f"Montant_Cumule={round(cumul_actuel + montant_abs, 2)}"
            )

        except Exception as e:
            logger.error(f"❌ Erreur _maj_referentiel pour '{sous_categorie}' : {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # 5. MISE À JOUR ÉPARGNE_HISTO
    # ─────────────────────────────────────────────────────────────────────────

    def _maj_epargne_histo(self, date_valeur: date, montant_abs: float):
        """
        Met à jour EPARGNE_HISTO quand une transaction Épargne & Investissement
        est enregistrée.
        Colonnes : Mois | Montant_Vise | Montant_Reel | Evolution_DH
          - Si le mois existe déjà : incrémente Montant_Reel et recalcule Evolution_DH
          - Sinon : crée une nouvelle ligne (Montant_Vise = 0 à compléter manuellement)
        Evolution_DH = Montant_Reel - Montant_Vise
        """
        try:
            ws = self.connexion.get_sheet(NOM_FEUILLE_EPARGNE)
            if ws is None:
                logger.error("❌ EPARGNE_HISTO introuvable — mise à jour ignorée.")
                return

            mois_str = date_valeur.strftime("%m/%Y")
            donnees  = ws.get_all_values()

            if not donnees:
                ws.append_row(["Mois", "Montant_Vise", "Montant_Reel", "Evolution_DH"])
                ws.append_row([mois_str, 0.0, round(montant_abs, 2), round(montant_abs, 2)])
                logger.info(f"📈 EPARGNE_HISTO — première ligne créée pour {mois_str}")
                return

            en_tetes = donnees[0]
            try:
                idx_mois = en_tetes.index("Mois")
                idx_vise = en_tetes.index("Montant_Vise")
                idx_reel = en_tetes.index("Montant_Reel")
                idx_evol = en_tetes.index("Evolution_DH")
            except ValueError as e:
                logger.error(f"❌ Colonne manquante dans EPARGNE_HISTO : {e}")
                return

            # Chercher si le mois existe déjà
            ligne_trouvee = None
            for i, ligne in enumerate(donnees[1:], start=2):
                if idx_mois < len(ligne) and ligne[idx_mois].strip() == mois_str:
                    ligne_trouvee = (i, ligne)
                    break

            if ligne_trouvee:
                num_ligne, data = ligne_trouvee
                try:
                    vise_actuel = float(str(data[idx_vise] or 0).replace(",", "."))
                except (ValueError, IndexError):
                    vise_actuel = 0.0
                try:
                    reel_actuel = float(str(data[idx_reel] or 0).replace(",", "."))
                except (ValueError, IndexError):
                    reel_actuel = 0.0

                nouveau_reel = round(reel_actuel + montant_abs, 2)
                evolution    = round(nouveau_reel - vise_actuel, 2)

                # Écriture atomique des deux cellules en un seul appel API
                ws.update_cells([
                    SQLiteCell(num_ligne, idx_reel + 1, nouveau_reel),
                    SQLiteCell(num_ligne, idx_evol + 1, evolution),
                ])
                logger.info(
                    f"📈 EPARGNE_HISTO mis à jour — {mois_str} : "
                    f"Montant_Reel={nouveau_reel} | Evolution_DH={evolution:+.2f}"
                )
            else:
                ws.append_row([mois_str, 0.0, round(montant_abs, 2), round(montant_abs, 2)])
                logger.info(f"📈 EPARGNE_HISTO — nouvelle ligne créée pour {mois_str}")

        except Exception as e:
            logger.error(f"❌ Erreur _maj_epargne_histo : {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # 6. CHARGEMENT DYNAMIQUE DES IDENTIFIANTS ÉPARGNE
    # ─────────────────────────────────────────────────────────────────────────

    def _charger_ids_epargne(self) -> Tuple[str, str]:
        """
        Cherche dans REFERENTIEL la ligne dont Sous_Categorie normalisée
        contient "EPARGNE" et "INVESTISSEMENT", et retourne (cat_norm, scat_norm).
        Fallback sur les constantes _CAT_EPARGNE_FALLBACK / _SCAT_EPARGNE_FALLBACK
        si la ligne est introuvable ou si le REFERENTIEL est vide.
        """
        try:
            df = self.connexion.load_sheet(NOM_FEUILLE_REFERENTIEL)
            if not df.empty and "Sous_Categorie" in df.columns and "Categorie" in df.columns:
                for _, row in df.iterrows():
                    scat = Douane.normaliser_texte(str(row.get("Sous_Categorie", "")))
                    if "EPARGNE" in scat and "INVESTISSEMENT" in scat:
                        cat = Douane.normaliser_texte(str(row.get("Categorie", "")))
                        logger.info(f"✅ IDs épargne chargés depuis REFERENTIEL : '{cat}' / '{scat}'")
                        return cat, scat
        except Exception as e:
            logger.warning(f"⚠️ _charger_ids_epargne — erreur lecture REFERENTIEL : {e}")

        logger.warning(
            f"⚠️ Ligne épargne introuvable dans REFERENTIEL — "
            f"fallback : '{_CAT_EPARGNE_FALLBACK}' / '{_SCAT_EPARGNE_FALLBACK}'"
        )
        return _CAT_EPARGNE_FALLBACK, _SCAT_EPARGNE_FALLBACK

    # ─────────────────────────────────────────────────────────────────────────
    # 7. POINT D'ENTRÉE PRINCIPAL : enregistrer_transaction()
    # ─────────────────────────────────────────────────────────────────────────

    def enregistrer_transaction(
        self,
        date_valeur:       date,
        description_brute: str,
        montant:           float,
        classification:    ResultatClassification,
    ) -> Dict[str, Any]:
        """
        Enregistre une transaction dans TRANSACTIONS puis met à jour REFERENTIEL.

        Paramètres :
          - date_valeur      : date du prélèvement réel (choisie par l'utilisateur).
          - description_brute: libellé brut (ex: 'Netflix_Avril').
          - montant          : valeur absolue — le signe est déduit du sens dans classification.
          - classification   : ResultatClassification issu du Trieur.

        Retourne :
          {id_unique, montant}           — transaction réussie
          {id_unique: None, montant, doublon: True, message}  — doublon bloqué
        """
        now          = datetime.now()
        date_saisie  = now.strftime("%Y-%m-%d %H:%M:%S")
        dv           = date_valeur or date.today()
        montant_abs  = abs(montant)
        montant_signe = -montant_abs if classification.sens == "OUT" else montant_abs

        # ── Vérification doublon ────────────────────────────────────────────
        if self._est_doublon(dv, description_brute, montant_abs):
            logger.warning(f"⚠️ Doublon bloqué : '{description_brute}' | {montant_abs:.2f} | {dv}")
            return {
                "id_unique": None,
                "montant":   montant_signe,
                "doublon":   True,
                "message":   (
                    f"⚠️ Doublon détecté : '{description_brute}' déjà enregistré "
                    f"dans les {FENETRE_DOUBLON_SECONDES // 60} dernières minutes."
                ),
            }

        # ── ID unique ───────────────────────────────────────────────────────
        id_unique = self._generer_id(now)

        # ── Construction de l'écriture (7 colonnes) ─────────────────────────
        ecriture = EcritureComptable(
            id_unique=id_unique,
            date_saisie=date_saisie,
            date_valeur=dv,
            mot_cle=description_brute,
            montant=montant_signe,
            categorie=classification.categorie,
            sous_categorie=classification.sous_categorie,
        )

        # ── Écriture dans TRANSACTIONS ──────────────────────────────────────
        self.connexion.ecrire_ligne(NOM_FEUILLE_TRANSACTIONS, self._ligne_transaction(ecriture))
        self._invalider_cache_transactions()  # forcer rechargement au prochain doublon
        # time.sleep(1.2)  # Quota Google API 429 — Non nécessaire avec SQLite local

        # ── Mise à jour REFERENTIEL ─────────────────────────────────────────
        self._maj_referentiel(classification.sous_categorie, montant_abs, classification.categorie, classification.sens)
        # time.sleep(1.2)  # Quota Google API 429 — Non nécessaire avec SQLite local

        # ── Mise à jour EPARGNE_HISTO si Épargne & Investissement ───────────
        if (Douane.normaliser_texte(classification.categorie)      == self._cat_epargne and
                Douane.normaliser_texte(classification.sous_categorie) == self._scat_epargne):
            self._maj_epargne_histo(dv, montant_abs)
            # time.sleep(1.2)  # Non nécessaire avec SQLite local

        logger.info(
            f"✅ [{id_unique}] '{description_brute}' → "
            f"{classification.categorie}/{classification.sous_categorie} | {montant_signe:+.2f}"
        )

        return {
            "id_unique": id_unique,
            "montant":   montant_signe,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # 8. RÉCUPÉRATION FLUX RÉCENT
    # ─────────────────────────────────────────────────────────────────────────

    def get_flux_recent(self, n: int = 10) -> List[Dict[str, Any]]:
        """
        Retourne les n dernières transactions, plus récentes en premier.
        Chaque élément : {heure_saisie, mot_cle, montant, categorie, sous_categorie, id_unique}
        """
        df = self.connexion.load_sheet(NOM_FEUILLE_TRANSACTIONS)
        if df.empty:
            return []

        flux = []
        for _, row in df.tail(n).iterrows():
            flux.append({
                "heure_saisie":   str(row.get("Date_Saisie", "")).strip(),
                "mot_cle":        str(row.get("Mot_Cle", "")).strip(),
                "montant":        Douane.normaliser_montant(row.get("Montant", 0)) or 0.0,
                "categorie":      str(row.get("Categorie", "")).strip(),
                "sous_categorie": str(row.get("Sous_Categorie", "")).strip(),
                "id_unique":      str(row.get("ID_Unique", "")).strip(),
            })

        return list(reversed(flux))  # plus récent en tête de liste


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    pass