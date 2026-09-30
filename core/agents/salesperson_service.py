"""
Service de gestion des commerciaux M Move et synchronisation Google Sheets.
Récupère les informations des commerciaux depuis la feuille Google Sheets :
https://docs.google.com/spreadsheets/d/1oB26N_hjCeYSqD1sAqAypWRbu48Vq4K6zDan7yly6mY/export?format=csv&gid=1940796205
"""

import os
import csv
import io
import re
import urllib.request
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# URL d'export CSV de la feuille des commerciaux
GOOGLE_SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/1oB26N_hjCeYSqD1sAqAypWRbu48Vq4K6zDan7yly6mY/export?format=csv&gid=1940796205"
)

# Rôles administrateurs (peuvent voir tous les dossiers et filtrer par commercial)
ADMIN_INITIALS = {"CH", "ADMIN"}

# Profils par défaut de secours (si pas de réseau)
DEFAULT_SALESPEOPLE = [
    {
        "id": "DR",
        "initials": "DR",
        "name": "David Rossomme",
        "phone": "+32 477 38 40 20",
        "email": "david@mediasee.be",
        "is_admin": False
    },
    {
        "id": "JF",
        "initials": "JF",
        "name": "Jean-François Golinvaux",
        "phone": "+32 475 38 04 07",
        "email": "jf@mediasee.be",
        "is_admin": False
    },
    {
        "id": "MM",
        "initials": "MM",
        "name": "Michel Mauléon",
        "phone": "+32 496 522 648",
        "email": "mauleon.2xm@outlook.com",
        "is_admin": False
    },
    {
        "id": "CH",
        "initials": "CH",
        "name": "Corentin Hubert",
        "phone": "+32 497 04 36 48",
        "email": "corentin@mediasee.be",
        "is_admin": True
    },
    {
        "id": "ES",
        "initials": "ES",
        "name": "Eddy Simon",
        "phone": "",
        "email": "edsimon@pt.lu",
        "is_admin": False
    },
    {
        "id": "PG",
        "initials": "PG",
        "name": "Pierre Gasparoly",
        "phone": "",
        "email": "",
        "is_admin": False
    },
    {
        "id": "ADMIN",
        "initials": "ADMIN",
        "name": "Direction M Move",
        "phone": "+32 (0)81 22 22 22",
        "email": "info@mediasee.be",
        "is_admin": True
    }
]


def clean_phone(phone: str) -> str:
    """Nettoie les caractères parasites unicode (LRO, PDF, etc.) et normalise les espaces."""
    if not phone:
        return ""
    # Supprime les caractères invisibles RTL/LTR unicode
    cleaned = re.sub(r"[\u202a-\u202e\u200e\u200f]", "", phone)
    return " ".join(cleaned.strip().split())


class SalespersonService:
    """Gère le référentiel des commerciaux M Move et leurs privilèges."""

    def __init__(self, sheet_url: str = GOOGLE_SHEET_CSV_URL):
        self.sheet_url = sheet_url
        self._salespeople_cache: Dict[str, Dict[str, Any]] = {}
        self.reload()

    def reload(self) -> List[Dict[str, Any]]:
        """Recharge les données depuis Google Sheets ou utilise le cache local."""
        loaded: Dict[str, Dict[str, Any]] = {}

        try:
            import ssl
            ssl_ctx = ssl._create_unverified_context()
            req = urllib.request.Request(
                self.sheet_url,
                headers={"User-Agent": "MmoveApp/1.0 (info@mediasee.be)"}
            )
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=5) as response:
                content = response.read().decode("utf-8", errors="ignore")
                reader = csv.DictReader(io.StringIO(content))
                for row in reader:
                    name = (row.get("Nom") or "").strip()
                    if not name:
                        continue
                    initials = (row.get("Initiales-com") or "").strip().upper()
                    if not initials:
                        # Déduction des initiales si manquantes
                        parts = name.split()
                        initials = "".join(p[0].upper() for p in parts[:2])

                    phone = clean_phone(row.get("Téléphone") or "")
                    email = (row.get("Mail-com") or "").strip()
                    is_admin = initials in ADMIN_INITIALS

                    loaded[initials] = {
                        "id": initials,
                        "initials": initials,
                        "name": name,
                        "phone": phone,
                        "email": email,
                        "is_admin": is_admin
                    }

            # S'assurer que le profil ADMIN direction est toujours disponible
            if "ADMIN" not in loaded:
                loaded["ADMIN"] = {
                    "id": "ADMIN",
                    "initials": "ADMIN",
                    "name": "Direction M Move",
                    "phone": "+32 (0)81 22 22 22",
                    "email": "info@mediasee.be",
                    "is_admin": True
                }

            self._salespeople_cache = loaded
            logger.info("Synchronisation Google Sheets réussie : %d commerciaux chargés", len(loaded))
        except Exception as e:
            logger.warning("Échec synchro Google Sheets (%s), utilisation des données par défaut", e)
            if not self._salespeople_cache:
                for sp in DEFAULT_SALESPEOPLE:
                    self._salespeople_cache[sp["initials"]] = sp.copy()

        return self.get_all()

    def get_all(self) -> List[Dict[str, Any]]:
        """Renvoie la liste ordonnée de tous les profils commerciaux."""
        if not self._salespeople_cache:
            for sp in DEFAULT_SALESPEOPLE:
                self._salespeople_cache[sp["initials"]] = sp.copy()

        # Met l'Admin en dernier et trie les commerciaux
        res = list(self._salespeople_cache.values())
        return sorted(res, key=lambda x: (x["initials"] == "ADMIN", x["name"]))

    def get(self, user_id_or_initials: Optional[str]) -> Dict[str, Any]:
        """Récupère un commercial par ses initiales ou ID. Si introuvable, renvoie un profil par défaut."""
        if not user_id_or_initials:
            return self._salespeople_cache.get("DR") or DEFAULT_SALESPEOPLE[0]

        key = str(user_id_or_initials).strip().upper()
        if key in self._salespeople_cache:
            return self._salespeople_cache[key]

        # Recherche par début de nom
        for sp in self._salespeople_cache.values():
            if sp["name"].lower().startswith(key.lower()) or key.lower() in sp["name"].lower():
                return sp

        return self._salespeople_cache.get("DR") or DEFAULT_SALESPEOPLE[0]

    def is_admin(self, user_id_or_initials: Optional[str]) -> bool:
        """Vérifie si le profil a les droits Administrateur / Superviseur."""
        sp = self.get(user_id_or_initials)
        return bool(sp.get("is_admin", False))
