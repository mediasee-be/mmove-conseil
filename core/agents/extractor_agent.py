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
from datetime import datetime
from typing import Dict, Any, Optional

DEFAULT_API_KEY = os.environ.get("GEMINI_API_KEY", "")

EXTRACTION_SYSTEM_PROMPT = """Tu es l'agent extracteur NLU haute vitesse du réseau d'affichage publicitaire M Move (Wallonie, Belgique).
Ta mission est d'analyser le message non structuré d'un utilisateur et d'extraire TOUS les paramètres de recherche sous forme d'un objet JSON STRICT, sans texte superflu.

Année de référence : 2026 (les dates sans année font référence à 2026, ou 2027 si explicitement indiqué).

### RÈGLES D'EXTRACTION :
1. "intent" :
   - "set_client_name" : définition ou mise à jour du nom du client (ex: "le client est Greenrobot", "client : Brico", "au nom de Marjorie Thomas")
   - "campaign_proposal" : proposition d'un plan de campagne publicitaire / multi-faces (ex: "propose-moi une campagne de 5 faces autour de Gembloux en janvier", "plan média", "sélection de campagne")
   - "search_panels" : demande de remorques / recherche géographique simple
   - "check_availability" : question sur quand un panneau ou un lieu est libre (ex: "quand est libre le 114 ?")
   - "identify_panel" : identification (ex: "c'est quel panneau près de la clinique ?")
   - "creative_advice" : conseil sur le visuel, les slogans, la charte graphique
   - "technical_specs" : formats de fichiers, bâche 390x200, délais
   - "admin_debug" : si l'utilisateur dit être "Corentin" ou demande le "mode debug"
   - "general_chat" : salutation ou question générale sans rapport avec une recherche

2. "client_name" : Nom de l'entreprise, marque, commerce ou personne cliente pour qui la campagne / devis est préparé (ex: "client : Greenrobot" -> "Greenrobot", "pour Greenrobot" -> "Greenrobot", "campagne pour Brico" -> "Brico", "au nom de Immo Toma" -> "Immo Toma"). Si aucun nom de client n'est mentionné, laisser null.

3. "target_id" : ID numérique de remorque si mentionné (ex: "#114" -> "114", "panneau 102" -> "102")

4. "locations" : Villes, communes, villages, zonings, adresses belges (ex: ["Wierde", "Naninne", "Sclayn", "Namur", "Wavre", "Gembloux", "Chaussée de Tirlemont"]). Ne pas mettre le nom du client ici si c'est déjà client_name.

5. "axes" : Axes routiers mentionnés (ex: ["N4", "E411", "E42", "N25", "N29", "N89", "N90"])

6. "target_periods" : Liste des mois au format "AAAA-MM".
   - Nous sommes actuellement fin 2026.
   - Les mois futurs de début d'année (janvier à septembre) sont en 2027 : "janvier" -> ["2027-01"], "mars" -> ["2027-03"].
   - Les mois de fin d'année en cours : "octobre" -> ["2026-10"], "novembre" -> ["2026-11"], "décembre" -> ["2026-12"].
   - Si plusieurs mois sont mentionnés (ex: "Mars, Avril, Mai", "de mars à mai", "sur 3 mois à partir de mars"), liste TOUS les mois ordonnés chronologiquement (ex: ["2027-03", "2027-04", "2027-05"]).
   - Si aucune date n'est précisée, laisser [].

7. "province" : Province wallonne ("Liège", "Namur", "Hainaut", "Luxembourg", "Brabant-Wallon") si mentionnée

8. "sector" : Secteur d'activité du client (ex: "bricolage", "concessionnaire automobile", "immobilier", "restauration")

9. "contexte_pref" : Contexte de visibilité recherché (ex: "zoning", "rond-point", "bouchons", "ralentissement", "centre commercial")

10. "count_requested" : Nombre de faces ou panneaux souhaités (ex: "5 face" -> 5, "3 panneaux" -> 3, par défaut 3)

11. "is_admin" : true si l'utilisateur mentionne "Corentin", "admin" ou "debug"

### FORMAT DE SORTIE JSON STRICT :
{
  "intent": "search_panels",
  "client_name": null,
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

def extract_client_name_regex(text: str) -> Optional[str]:
    """Extrait le nom du client depuis le message s'il est spécifié."""
    patterns = [
        r"(?:au nom de|pour le client|pour la société|pour l'entreprise)\s+([A-Za-z0-9À-ÿ\s&'.-]+?)(?:\s+(?:en|sur|pour|avec|au|de|à|dans)\b|[.,;!]|$)",
        r"(?:le client est|nom du client\s*:?)\s*([A-Za-z0-9À-ÿ\s&'.-]+?)(?:\s+(?:en|sur|pour|avec|au|de|à|dans)\b|[.,;!]|$)",
        r"(?:^|\b)(?:client|société|entreprise)\s*:\s*([A-Za-z0-9À-ÿ\s&'.-]+?)(?:\s+(?:en|sur|pour|avec|au|de|à|dans)\b|[.,;!]|$)",
        r"(?:devis|plan|campagne)\s+pour\s+([A-Za-z0-9À-ÿ\s&'.-]+?)(?:\s+(?:en|sur|de|à|dans)\b|[.,;!]|$)",
        r"^pour\s+([A-Za-z0-9À-ÿ\s&'.-]+?)(?:\s+(?:en|sur|de|à|dans)\b|[.,;!]|$)",
    ]
    for p in patterns:
        m = re.search(p, text.strip(), re.IGNORECASE)
        if m:
            val = m.group(1).strip().strip("'\"«»")
            val_lower = val.lower()
            stop_words = ["mois", "face", "faces", "panneau", "panneaux", "remorque", "remorques",
                          "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
                          "septembre", "octobre", "novembre", "décembre", "2026", "2027",
                          "moi", "nous", "vous", "lui", "ce", "cette", "mon", "ma", "mes"]
            if not any(w == val_lower or val_lower.startswith(w + " ") for w in stop_words):
                if len(val) >= 2:
                    return val.title() if val.islower() else val
    return None

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

        # Détection rapide du nom de client
        client_fast = extract_client_name_regex(msg_clean)

        # Fast-path admin
        is_admin = any(k in lower for k in ["corentin", "admin corentin", "mode debug"])
        if is_admin and len(msg_clean.split()) <= 4:
            return {
                "intent": "admin_debug",
                "client_name": client_fast,
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

        # Fast-path indication exclusive du nom du client (ex: "Le client est Greenrobot" ou "Client : Brico")
        if client_fast and len(msg_clean.split()) <= 7 and not any(w in lower for w in ["face", "faces", "panneau", "remorque", "cherche", "dispo", "campagne", "plan"]):
            return {
                "intent": "set_client_name",
                "client_name": client_fast,
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

        # Fast-path ID direct (ex: "panneau #114" ou "dispo du 114")
        id_match = re.search(r"(?:panneau|remorque)?\s*#?([1-5]\d{2})\b", lower)
        target_id = id_match.group(1) if id_match else None
        if target_id and ("dispo" in lower or "libre" in lower or "quand" in lower):
            return {
                "intent": "check_availability",
                "client_name": client_fast,
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
                "client_name": client_fast,
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
                "client_name": client_fast,
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
                    if client_fast and not extracted.get("client_name"):
                        extracted["client_name"] = client_fast
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
        month_order = [
            ("janvier", "01"), ("février", "02"), ("fevrier", "02"), ("mars", "03"), ("avril", "04"),
            ("mai", "05"), ("juin", "06"), ("juillet", "07"), ("août", "08"), ("aout", "08"),
            ("septembre", "09"), ("octobre", "10"), ("novembre", "11"), ("décembre", "12"), ("decembre", "12")
        ]
        now = datetime.now()
        cur_year = now.year
        cur_month = now.month

        # 1. Trouver tous les mois mentionnés avec leur position
        found_months = []
        for m_name, m_num in month_order:
            for match in re.finditer(r"\b" + m_name + r"\b", lower):
                m_int = int(m_num)
                y = cur_year + 1 if m_int < cur_month else cur_year
                found_months.append((match.start(), f"{y}-{m_num}", m_int, y))

        found_months.sort(key=lambda x: x[0])

        # 2. Vérifier si un intervalle est mentionné (ex: "de mars à mai", "entre mars et mai")
        range_match = re.search(r"(?:de|entre|du)\s+([a-zà-ÿ]+)\s+(?:à|au|et|jusqu\'à)\s+([a-zà-ÿ]+)", lower)
        # 3. Vérifier si une durée en mois est mentionnée (ex: "pendant 3 mois", "sur 2 mois", "pour 3 mois")
        dur_match = re.search(r"(?:pendant|sur|pour|durant)\s+(\d+)\s+mois", lower)

        if range_match and len(found_months) >= 2:
            m1_int, y1 = found_months[0][2], found_months[0][3]
            m2_int, y2 = found_months[1][2], found_months[1][3]
            cy, cm = y1, m1_int
            while (cy < y2) or (cy == y2 and cm <= m2_int):
                periods.append(f"{cy}-{cm:02d}")
                cm += 1
                if cm > 12:
                    cm = 1
                    cy += 1
        elif dur_match and len(found_months) >= 1:
            n_months = int(dur_match.group(1))
            m1_int, y1 = found_months[0][2], found_months[0][3]
            cy, cm = y1, m1_int
            for _ in range(n_months):
                periods.append(f"{cy}-{cm:02d}")
                cm += 1
                if cm > 12:
                    cm = 1
                    cy += 1
        else:
            seen = set()
            for _, p, _, _ in found_months:
                if p not in seen:
                    seen.add(p)
                    periods.append(p)

        count = 3
        c_match = re.search(r"(\d+)\s*(?:panneaux|panneau|remorques|remorque|faces|face|emplacements|emplacement|spots|spot)", lower)
        if c_match:
            try:
                count = int(c_match.group(1))
            except ValueError:
                pass

        # Détection d'une intention de proposition de campagne
        is_campaign = (
            any(k in lower for k in ["campagne", "plan média", "plan media", "pack", "selection", "sélection"])
            or ("face" in lower and count > 1)
            or (count >= 3 and len(periods) > 0)
        )

        client_name = extract_client_name_regex(msg)

        if is_campaign:
            intent = "campaign_proposal"
        elif client_name and not locations and not periods and not axes and len(msg.strip().split()) <= 6:
            intent = "set_client_name"
        elif any(k in lower for k in ["dispo", "disponibilité", "disponibilites", "libre", "quand", "prochaine"]):
            intent = "check_availability"
        else:
            intent = "search_panels"

        return {
            "intent": intent,
            "client_name": client_name,
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
