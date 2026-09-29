"""
Mmove Extractor Agent (NLU Query Parser)
Analyse les requêtes en langage naturel non structurées et extrait
les critères précis en format JSON structuré en < 500ms via Gemini Flash.
"""

import os
import re
import json
import ssl
import urllib.request
from typing import Dict, Any, Optional

DEFAULT_API_KEY = os.environ.get("GEMINI_API_KEY", "")

EXTRACTION_SYSTEM_PROMPT = """Tu es l'agent extracteur NLU haute vitesse du réseau d'affichage publicitaire M Move (Wallonie, Belgique).
Ta mission est d'analyser le message non structuré d'un utilisateur et d'extraire TOUS les paramètres de recherche sous forme d'un objet JSON STRICT, sans texte superflu.

Année de référence : 2026 (les dates sans année font référence à 2026, ou 2027 si explicitement indiqué).

### RÈGLES D'EXTRACTION :
1. "intent" :
   - "search_panels" : demande de remorques / recherche géographique / projet de campagne
   - "check_availability" : question sur quand un panneau ou un lieu est libre (ex: "quand est libre le 114 ?")
   - "identify_panel" : identification (ex: "c'est quel panneau près de la clinique ?")
   - "creative_advice" : conseil sur le visuel, les slogans, la charte graphique
   - "technical_specs" : formats de fichiers, bâche 390x200, délais
   - "admin_debug" : si l'utilisateur dit être "Corentin" ou demande le "mode debug"
   - "general_chat" : salutation ou question générale sans rapport avec une recherche

2. "target_id" : ID numérique de remorque si mentionné (ex: "#114" -> "114", "panneau 102" -> "102")

3. "locations" : Villes, communes, villages, zonings, adresses, ou noms d'entreprises / commerces belges (ex: ["Wierde", "Naninne", "Sclayn", "Namur", "Wavre", "Greenrobot", "Decathlon", "Chaussée de Tirlemont"]). Capture TOUJOURS le nom spécifique de l'entreprise, du commerce, du village ou de la rue.

4. "axes" : Axes routiers mentionnés (ex: ["N4", "E411", "E42", "N25", "N29", "N89", "N90"])

5. "target_periods" : Liste des mois au format "AAAA-MM".
   - "mai" -> ["2026-05"]
   - "fin d'année" ou "dernier trimestre" -> ["2026-10", "2026-11", "2026-12"]
   - "printemps" -> ["2026-03", "2026-04", "2026-05"]
   - "été" -> ["2026-06", "2026-07", "2026-08"]
   - Si aucune date n'est précisée, laisser []

6. "province" : Province wallonne ("Liège", "Namur", "Hainaut", "Luxembourg", "Brabant-Wallon") si mentionnée

7. "sector" : Secteur d'activité du client (ex: "bricolage", "concessionnaire automobile", "immobilier", "restauration")

8. "contexte_pref" : Contexte de visibilité recherché (ex: "zoning", "rond-point", "bouchons", "ralentissement", "centre commercial")

9. "count_requested" : Nombre de remorques souhaitées (ex: "3 panneaux" -> 3, par défaut 3)

10. "is_admin" : true si l'utilisateur mentionne "Corentin", "admin" ou "debug"

### FORMAT DE SORTIE JSON STRICT :
{
  "intent": "search_panels",
  "target_id": null,
  "locations": [],
  "axes": [],
  "target_periods": [],
  "province": null,
  "direction": null,
  "sector": null,
  "contexte_pref": null,
  "count_requested": 3,
  "is_admin": false
}
"""

class ExtractorAgent:
    """Agent NLU utilisant Gemini Flash pour extraire les paramètres de requêtes non structurées."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", DEFAULT_API_KEY)
        self.model = model
        self.ssl_ctx = ssl._create_unverified_context()

    def extract(self, user_message: str) -> Dict[str, Any]:
        """Extrait les entités et l'intention depuis le message utilisateur."""
        # 1. Vérification rapide locale (Fast Path) pour phrases triviales
        msg_clean = user_message.strip()
        lower = msg_clean.lower()

        # Fast-path admin
        is_admin = any(k in lower for k in ["corentin", "admin corentin", "mode debug"])
        if is_admin and len(msg_clean.split()) <= 4:
            return {
                "intent": "admin_debug",
                "target_id": None,
                "locations": [],
                "axes": [],
                "target_periods": [],
                "province": None,
                "direction": None,
                "sector": None,
                "contexte_pref": None,
                "count_requested": 3,
                "is_admin": True,
            }

        # Fast-path ID direct (ex: "panneau #114" ou "dispo du 114")
        id_match = re.search(r"(?:panneau|remorque)?\s*#?([1-5]\d{2})\b", lower)
        target_id = id_match.group(1) if id_match else None
        if target_id and ("dispo" in lower or "libre" in lower or "quand" in lower):
            return {
                "intent": "check_availability",
                "target_id": target_id,
                "locations": [],
                "axes": [],
                "target_periods": [],
                "province": None,
                "direction": None,
                "sector": None,
                "contexte_pref": None,
                "count_requested": 1,
                "is_admin": is_admin,
            }

        # Fast-path conseils créatifs purs
        if any(k in lower for k in ["conseil visuel", "conseils pour mon affiche", "charte graphique", "règle des 7 mots"]):
            return {
                "intent": "creative_advice",
                "target_id": None,
                "locations": [],
                "axes": [],
                "target_periods": [],
                "province": None,
                "direction": None,
                "sector": None,
                "contexte_pref": None,
                "count_requested": 3,
                "is_admin": is_admin,
            }

        # Fast-path technique pur
        if any(k in lower for k in ["format d'impression", "taille bâche", "390x200", "dpi", "wetransfer"]):
            return {
                "intent": "technical_specs",
                "target_id": None,
                "locations": [],
                "axes": [],
                "target_periods": [],
                "province": None,
                "direction": None,
                "sector": None,
                "contexte_pref": None,
                "count_requested": 3,
                "is_admin": is_admin,
            }

        # 2. Appel Gemini Flash pour extraction sémantique robuste
        candidate_models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]

        payload = {
            "system_instruction": {
                "parts": [{"text": EXTRACTION_SYSTEM_PROMPT}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"Message de l'utilisateur : \"{user_message}\""}]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
                "maxOutputTokens": 500,
            }
        }

        data_bytes = json.dumps(payload).encode("utf-8")

        for mod in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent?key={self.api_key}"
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=4) as response:
                    res_body = json.loads(response.read().decode("utf-8"))
                    text_out = res_body["candidates"][0]["content"]["parts"][0]["text"]
                    extracted = json.loads(text_out)
                    if is_admin:
                        extracted["is_admin"] = True
                    return extracted
            except Exception as e:
                print(f"Extractor warning with model {mod}: {e}")

        # Fallback déterministe d'urgence si l'API est indisponible
        return self._rule_based_fallback(user_message, is_admin)

    def _rule_based_fallback(self, msg: str, is_admin: bool) -> Dict[str, Any]:
        """Analyseur de secours par expressions régulières."""
        lower = msg.lower()
        locations = []
        # Extraction de points d'intérêt, entreprises ou commerces (ex: "proche de chez Greenrobot", "près de Decathlon")
        poi_match = re.search(
            r"(?:près|proche|autour|à côté|proximité)\s+de\s+(?:chez\s+)?([A-Za-z0-9À-ÿ\s'-]+?)(?:\s+(?:en|pour|dès|dans|avec|direction|vers|\?|\.|$)|$)",
            msg, re.IGNORECASE
        )
        if not poi_match:
            poi_match = re.search(
                r"de\s+chez\s+([A-Za-z0-9À-ÿ\s'-]+?)(?:\s+(?:en|pour|dès|dans|avec|direction|vers|\?|\.|$)|$)",
                msg, re.IGNORECASE
            )
        if poi_match:
            candidate_poi = poi_match.group(1).strip()
            candidate_poi = re.sub(r"^(?:la\s+|le\s+|l'|les\s+)", "", candidate_poi, flags=re.IGNORECASE).strip()
            if len(candidate_poi) >= 3 and candidate_poi.lower() not in ["namur", "wavre", "panneau", "remorque", "moi", "vous", "nous"]:
                locations.append(candidate_poi.title())

        for city in ["namur", "wavre", "nivelles", "ottignies", "liège", "charleroi", "mons", "gembloux", "perwez", "jodoigne", "ciney", "dinant"]:
            if city in lower and city.capitalize() not in locations:
                locations.append(city.capitalize())

        axes = []
        for ax in ["e411", "e42", "n4", "n25", "n29", "n89", "n90", "n5"]:
            if ax in lower:
                axes.append(ax.upper())

        periods = []
        month_dict = {
            "janvier": "01", "février": "02", "fevrier": "02", "mars": "03", "avril": "04",
            "mai": "05", "juin": "06", "juillet": "07", "août": "08", "aout": "08",
            "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12", "decembre": "12"
        }
        for m_name, m_num in month_dict.items():
            if m_name in lower:
                periods.append(f"2026-{m_num}")

        count = 3
        c_match = re.search(r"(\d+)\s*(?:panneaux|remorques)", lower)
        if c_match:
            try:
                count = int(c_match.group(1))
            except ValueError:
                pass

        intent = "search_panels"
        if any(k in lower for k in ["dispo", "disponibilité", "disponibilites", "libre", "quand", "prochaine"]):
            intent = "check_availability"

        return {
            "intent": intent,
            "target_id": None,
            "locations": locations,
            "axes": axes,
            "target_periods": periods,
            "province": None,
            "direction": None,
            "sector": None,
            "contexte_pref": "zoning" if "zoning" in lower else None,
            "count_requested": count,
            "is_admin": is_admin
        }
