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
from typing import Dict, Any, Optional, List

DEFAULT_API_KEY = os.environ.get("GEMINI_API_KEY", "")

EXTRACTION_SYSTEM_PROMPT = """Tu es l'agent extracteur NLU haute vitesse du réseau d'affichage publicitaire M Move (Wallonie, Belgique).
Ta mission est d'analyser le message non structuré d'un utilisateur et d'extraire TOUS les paramètres de recherche sous forme d'un objet JSON STRICT, sans texte superflu.

Année de référence : 2026 (les dates sans année font référence à 2026, ou 2027 si explicitement indiqué).

### RÈGLES D'EXTRACTION :
1. "intent" :
   - "check_availability" : question sur les disponibilités d'une zone ou d'un panneau (ex: "quelles sont les disponibilités autour de Ciney en novembre et décembre ?", "quand est libre le 114 ?", "qu'est-ce qui est libre en mars ?"). Doit être TOUJOURS prioritaire sur campaign_proposal pour toute question portant sur les dates, mois ou disponibilités d'emplacements. C'est un inventaire d'options pour que le client fasse sa sélection, ce n'est JAMAIS un plan média !
   - "campaign_proposal" : UNIQUEMENT quand l'utilisateur demande explicitement un plan de campagne, un plan média ou un pack de communication (ex: "propose-moi une campagne de 5 faces", "fais-moi un plan média pour Gembloux", "je veux une sélection de campagne multi-mois")
   - "refine_campaign" : sélection de faces par le client, validation, affinement ou modification (ex: "on retient la 309 et la 310", "on prend la 309 et 310", "je choisis #309 et #310", "garde la 108", "enlève le 323", "sans la 329", "passe à 4 faces")
   - "search_panels" : demande de remorques / recherche géographique simple
   - "identify_panel" : identification (ex: "c'est quel panneau près de la clinique ?")
   - "creative_advice" : conseil sur le visuel, les slogans, la charte graphique
   - "technical_specs" : formats de fichiers, bâche 390x200, délais
   - "coordinator_dialogue" : dialogue avec le coordinateur, questions sur la démarche, sur la prise en compte de l'annonceur, sur le profil du client, questions métas ou remarques conversationnelles du commercial (ex: "As-tu pris en compte l'annonceur avant de me proposer toutes ces faces ?", "Pourquoi me proposes-tu toute la Wallonie ?", "Est-ce adapté à son activité ?", "Qui est l'annonceur ?", "Que me conseilles-tu ?", "Comment tu choisis les faces ?"). Ne JAMAIS classifier en search_panels une question ou une remarque de dialogue !
   - "admin_debug" : si l'utilisateur dit être "Corentin" ou demande le "mode debug"
   - "general_chat" : salutation ou remerciement sans rapport avec une recherche (ex: "Bonjour", "Merci", "Super", "Qui es-tu")

2. "refinement_action" (uniquement si intent == "refine_campaign") :
   - "add_face" : ajout d'une ou plusieurs faces au plan média en cours (ex: "ajoute une face chaque mois près d'Éghezée", "ajoute 1 face à Éghezée", "ajoute 2 faces", "ajoute une face"). Extraire la commune ciblée dans "locations" (ex: ["Eghezée"]) et le nombre de faces à ajouter dans "count_requested" ou "delta_count" (ex: 1).
   - "pin_panel" : sélection ou validation d'une ou plusieurs remorques retenues par le client (ex: "on retient la 309 et la 310", "on prend la 309 et 310", "je choisis #309 et #310", "ok pour la 108", "garde la 108", "je prends la 108", "valide le 108"). Extraire TOUS les numéros de remorques dans "pinned_panel_ids".
   - "exclude_panel" : rejet d'un panneau (ex: "pas la 323", "enlève le 323", "sans la 323")
   - "expand_zone" : élargissement de la zone de recherche (ex: "élargis vers Wavre", "ajoute Wavre", "regarde aussi à Wavre", "et à Wavre ?")
   - "change_count" : modification du nombre total de faces par mois (ex: "passe à 6 faces", "avec 6 faces")
   - "change_period" : modification des mois de campagne

3. "is_regeneration" : true si l'utilisateur demande de régénérer, refaire ou mettre à jour la sélection avec les critères en cours (ex: "refais ma sélection", "mets à jour la sélection", "régénère le plan", "actualise la sélection")

4. "pinned_panel_ids" : Liste de TOUS les identifiants de remorques choisis, retenus ou validés par l'utilisateur (ex: ["309", "310"]).

5. "excluded_panel_ids" : Liste d'identifiants de remorques rejetés par l'utilisateur (ex: ["323"])

6. "client_name" : Nom de l'entreprise, marque, commerce ou personne cliente (ex: "client : Greenrobot" -> "Greenrobot"). Si aucun nom mentionné, laisser null.

7. "target_id" : ID numérique de remorque si mentionné (ex: "#114" -> "114", "panneau 108" -> "108")

8. "locations" : Villes, communes, villages, zonings, adresses belges (ex: ["Wierde", "Naninne", "Sclayn", "Namur", "Wavre", "Gembloux"]).

9. "axes" : Axes routiers mentionnés (ex: ["N4", "E411", "E42", "N25", "N29", "N89", "N90"])

10. "target_periods" : Liste des mois au format "AAAA-MM".
   - Nous sommes actuellement fin 2026.
   - Les mois futurs de début d'année (janvier à septembre) sont en 2027 : "janvier" -> ["2027-01"], "mars" -> ["2027-03"].
   - Les mois de fin d'année en cours : "octobre" -> ["2026-10"], "novembre" -> ["2026-11"], "décembre" -> ["2026-12"].
   - Si plusieurs mois sont mentionnés (ex: "Mars, Avril, Mai"), liste TOUS les mois ordonnés chronologiquement (ex: ["2027-03", "2027-04", "2027-05"]).
   - Si aucune date n'est précisée dans ce message précis, laisser [].

11. "province" : Province wallonne si mentionnée
12. "sector" : Secteur d'activité du client
13. "contexte_pref" : Contexte de visibilité recherché (ex: "zoning", "rond-point")
14. "count_requested" : Nombre de faces ou panneaux souhaités EXPLICITEMENT (ex: "3 faces" -> 3, "5 remorques" -> 5). Si l'utilisateur demande simplement les disponibilités sans préciser de quantité (ex: "quelles sont les disponibilités autour de Ciney ?"), laisser null afin de renvoyer TOUTES les disponibilités. Si c'est une demande de campagne explicite sans précision de nombre, mettre 5.
15. "is_admin" : true si mention de "Corentin", "admin" ou "debug"

### FORMAT DE SORTIE JSON STRICT :
{
  "intent": "search_panels",
  "refinement_action": null,
  "is_regeneration": false,
  "pinned_panel_ids": [],
  "excluded_panel_ids": [],
  "client_name": null,
  "target_id": null,
  "locations": [],
  "axes": [],
  "target_periods": [],
  "province": null,
  "direction": null,
  "sector": null,
  "contexte_pref": null,
  "count_requested": null,
  "is_admin": false
}
"""

def extract_client_name_regex(text: str) -> Optional[str]:
    """Extrait le nom du client depuis le message s'il est spécifié."""
    clean_text = text.strip()

    # 1. Détection directe des annonceurs connus dans l'écosystème M Move
    known_clients = [
        ("marjorie toma", "Marjorie Toma"),
        ("les maisons de marjorie", "Marjorie Toma"),
        ("toma", "Marjorie Toma"),
        ("greenrobot", "Greenrobot"),
        ("brico ciney", "Brico Ciney"),
        ("tournée générale", "Tournée Générale"),
        ("tournee generale", "Tournée Générale"),
        ("d'ieteren", "D'Ieteren"),
        ("quick", "Quick"),
        ("hubo", "Hubo"),
    ]
    for kc_pat, kc_name in known_clients:
        if re.search(r"\b" + re.escape(kc_pat) + r"\b", clean_text, re.IGNORECASE):
            return kc_name

    patterns = [
        r"(?:que|qu')\s*(?:proposerais|proposes|recommanderais|recommandes|conseillerais|conseilles)\s*-?\s*tu\s+pour\s+([A-Za-z0-9À-ÿ\s&'.-]+?)(?:\s+(?:en|sur|pour|avec|au|de|à|dans)\b|[.,;?!]|$)",
        r"(?:qu'est-ce\s+qu'on\s+(?:peut|pourrait)\s+(?:proposer|faire)|tu\s+(?:conseilles|recommandes|proposes)\s+quoi)\s+pour\s+([A-Za-z0-9À-ÿ\s&'.-]+?)(?:\s+(?:en|sur|pour|avec|au|de|à|dans)\b|[.,;?!]|$)",
        r"(?:quelle\s+stratégie|quelle\s+recommandation|fais-moi\s+une\s+proposition|une\s+idée)\s+pour\s+([A-Za-z0-9À-ÿ\s&'.-]+?)(?:\s+(?:en|sur|pour|avec|au|de|à|dans)\b|[.,;?!]|$)",
        r"(?:au nom de|pour le client|pour la société|pour l'entreprise|pour le compte de)\s+([A-Za-z0-9À-ÿ\s&'.-]+?)(?:\s+(?:en|sur|pour|avec|au|de|à|dans)\b|[.,;!]|$)",
        r"(?:(?:le|mon|notre)\s+client\s+est|nom du client\s*:?|c'est\s+pour\s+(?:le\s+client\s+)?|ce\s+serait\s+pour\s+)\s*([A-Za-z0-9À-ÿ\s&'.-]+?)(?:\s+(?:en|sur|pour|avec|au|de|à|dans)\b|[.,;!]|$)",
        r"(?:^|\b)(?:client|société|entreprise)\s*:\s*([A-Za-z0-9À-ÿ\s&'.-]+?)(?:\s+(?:en|sur|pour|avec|au|de|à|dans)\b|[.,;!]|$)",
        r"(?:devis|plan|campagne)\s+pour\s+([A-Za-z0-9À-ÿ\s&'.-]+?)(?:\s+(?:en|sur|de|à|dans)\b|[.,;!]|$)",
        r"^pour\s+([A-Za-z0-9À-ÿ\s&'.-]+?)(?:\s+(?:en|sur|de|à|dans)\b|[.,;!]|$)",
    ]
    for p in patterns:
        m = re.search(p, clean_text, re.IGNORECASE)
        if m:
            val = m.group(1).strip().strip("'\"«»?.,")
            val_lower = val.lower()
            stop_words = ["mois", "face", "faces", "panneau", "panneaux", "remorque", "remorques",
                          "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
                          "septembre", "octobre", "novembre", "décembre", "2026", "2027",
                          "moi", "nous", "vous", "lui", "elle", "ce", "cette", "mon", "ma", "mes",
                          "ce client", "cette cliente", "l'annonceur", "cet annonceur", "eux", "qui", "quoi"]
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

    def extract(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        active_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Extrait les entités et l'intention depuis le message utilisateur en tenant compte de l'historique."""
        # 1. Vérification rapide locale (Fast Path) pour phrases triviales
        msg_clean = user_message.strip()
        lower = msg_clean.lower()

        # Détection rapide du nom de client
        client_fast = extract_client_name_regex(msg_clean)

        # Fast-path Demande de motivation / explication de proposition (ex: "Motive-moi ta proposition ?", "Pourquoi ce choix ?")
        motivation_triggers = [
            "motive-moi ta proposition", "motive moi ta proposition", "motive ta proposition",
            "motive-moi tes choix", "motive moi tes choix", "motive tes choix", "motive cette proposition",
            "motive-moi", "motive moi", "motive ta", "motive tes", "motive",
            "pourquoi ce choix", "pourquoi ces choix", "pourquoi cette proposition",
            "pourquoi ces panneaux", "pourquoi ces remorques", "pourquoi ces faces", "pourquoi ces emplacements",
            "pourquoi ceux-là", "pourquoi ceux la", "pourquoi ceux ci", "pourquoi ceux-ci",
            "justifie ton choix", "justifie tes choix", "justifie ta proposition", "justifie cette sélection",
            "explique-moi tes choix", "explique moi tes choix", "explique tes choix", "explique ton choix",
            "explique-moi ta sélection", "explique moi ta sélection", "explique ta sélection",
            "explique cette sélection", "explique cette proposition", "explique la proposition",
            "argumente ta sélection", "argumente ta proposition", "peux-tu argumenter", "peux tu argumenter",
            "quelle est la logique", "pourquoi avoir choisi", "qu'est-ce qui motive", "qu est ce qui motive"
        ]
        if any(m in lower for m in motivation_triggers):
            return {
                "intent": "motivate_proposal",
                "is_regeneration": False,
                "is_open_consultation": False,
                "refinement_action": None,
                "pinned_panel_ids": [],
                "excluded_panel_ids": [],
                "client_name": client_fast,
                "target_id": None,
                "locations": [],
                "axes": [],
                "target_periods": [],
                "province": None,
                "direction": None,
                "sector": None,
                "contexte_pref": None,
                "count_requested": None,
                "is_admin": False
            }

        # Détection des pronoms désignant le client actif ("pour lui", "pour elle", "pour ce client", "pour l'annonceur")
        is_referring_to_active_client = bool(re.search(
            r"\b(pour lui|pour elle|pour ce client|pour cette cliente|pour l'annonceur|pour cet annonceur|son activit[ée]|sa zone|ses besoins)\b",
            lower
        ))

        # Fast-path Dialogue Coordinateur & Questions Méthode / Annonceur / Agents
        # (ex: "As-tu pris en compte l'annonceur avant de me proposer toutes ces faces ?", "Pourquoi me proposer toute la Wallonie ?", "Que me conseilles-tu ?")
        dialogue_triggers = [
            "pris en compte l'annonceur", "pris en compte le client", "tenu compte de l'annonceur", "tenu compte du client",
            "pris en compte son", "tenu compte de son", "pris en compte ce client", "tenu compte de ce client",
            "adapté à son activité", "adapte a son activite", "adapté pour lui", "adapte pour lui",
            "adapté pour elle", "adapte pour elle", "adapté à ce client", "adapte a ce client",
            "pourquoi me proposer tout", "pourquoi proposer tout", "pourquoi toute la wallonie",
            "pourquoi me proposer ces faces", "pourquoi proposer toutes ces faces", "pourquoi toutes ces faces",
            "pourquoi ces faces", "pourquoi ces remorques", "pourquoi ces panneaux", "pourquoi autant de faces",
            "qui est l'annonceur", "qui est le client", "quel est le client", "quel est l'annonceur",
            "que sais-tu sur", "que sait-on sur", "connais-tu ce client", "quel est son secteur",
            "que dit l'agent", "que propose l'agent", "comment travaillent tes agents", "qui sont tes agents",
            "comment est composé ton équipe", "comment est compose ton equipe",
            "que me conseilles-tu", "qu'est-ce que tu me conseilles", "que conseilles-tu",
            "comment on procède", "comment procéder", "qu'est-ce qu'on fait maintenant", "quelle est la suite", "quelle est la prochaine étape",
            "comment tu sélectionnes", "comment tu choisis", "comment sont calculés", "comment tu calcules"
        ]

        is_direct_dialogue = any(t in lower for t in dialogue_triggers)

        # Questions méta commençant par "as-tu", "est-ce que tu as", "tu as pris en compte", etc.
        is_meta_question = bool(re.search(
            r"^(as[- ]tu|est[- ]ce que tu|tu as (pensé|pris|vérifié|tenu)|pourquoi (as[- ]tu|tu as|avoir)|peux[- ]tu m['’]expliquer|qu['’]en penses[- ]tu)\b",
            lower
        )) and not any(w in lower for w in ["libre", "dispo", "quand", "#"])

        # Salutations & politesses pures
        is_general_salutation = bool(re.match(r"^(bonjour|bonsoir|salut|hello|coucou|merci|merci beaucoup|c'est parfait|parfait merci|super merci|qui es[- ]tu|présente[- ]toi)[ !.?]*$", lower))

        if is_direct_dialogue or is_meta_question or is_general_salutation:
            return {
                "intent": "coordinator_dialogue" if not is_general_salutation else "general_chat",
                "is_referring_to_active_client": is_referring_to_active_client,
                "is_regeneration": False,
                "is_open_consultation": False,
                "refinement_action": None,
                "pinned_panel_ids": [],
                "excluded_panel_ids": [],
                "client_name": client_fast,
                "target_id": None,
                "locations": [],
                "axes": [],
                "target_periods": [],
                "province": None,
                "direction": None,
                "sector": None,
                "contexte_pref": None,
                "count_requested": None,
                "is_admin": False
            }

        # Fast-path Consultation ouverte pour un client (ex: "Que proposerais-tu pour Marjorie Toma")
        if client_fast and any(w in lower for w in [
            "que proposerais-tu", "que proposes-tu", "tu conseilles", "tu recommandes",
            "quelle recommandation", "quelle stratégie", "qu'est-ce qu'on", "fais-moi une proposition",
            "une idée", "que penses-tu", "tu en penses quoi"
        ]):
            return {
                "intent": "campaign_proposal",
                "is_open_consultation": True,
                "is_regeneration": False,
                "refinement_action": None,
                "pinned_panel_ids": [],
                "excluded_panel_ids": [],
                "client_name": client_fast,
                "target_id": None,
                "locations": [],
                "axes": [],
                "target_periods": [],
                "province": None,
                "direction": None,
                "sector": None,
                "contexte_pref": None,
                "count_requested": 5,
                "is_admin": False
            }

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

        # Fast-path Régénération de sélection (ex: "refais ma sélection", "mets à jour la sélection", "régénère le plan")
        regeneration_phrases = [
            "refais ma sélection", "refais la sélection", "refais selection", "refais ma selection",
            "mets à jour ma sélection", "mets à jour la sélection", "mettre à jour la sélection",
            "régénère le plan", "regenere le plan", "recalcule la sélection", "relance la sélection",
            "actualise la sélection", "actualise le plan", "génère avec ça", "fais la sélection avec ça",
            "refais le plan", "actualise mon plan"
        ]
        if any(p in lower for p in regeneration_phrases):
            return {
                "intent": "campaign_proposal",
                "is_regeneration": True,
                "refinement_action": None,
                "pinned_panel_ids": [],
                "excluded_panel_ids": [],
                "client_name": client_fast,
                "target_id": None,
                "locations": [],
                "axes": [],
                "target_periods": [],
                "province": None,
                "direction": None,
                "sector": None,
                "contexte_pref": None,
                "count_requested": 5,
                "is_admin": is_admin,
            }

        # Fast-path Validation / Épinglage d'un panneau (ex: "ok pour la 108", "garde la 108", "je prends la 108", "valide le 108")
        # Ne pas intercepter si le message définit une nouvelle campagne complète (ex: "Campagne de 5 faces à Gembloux...")
        is_campaign_msg = any(k in lower for k in ["campagne", "plan média", "plan media", "pack"])
        pin_match = re.search(r"(?:ok\s+pour|je\s+prends|garde|ajoute|valide|on\s+prend|retenons|retenir|choisis|choisit)\s+(?:la|le|le\s+panneau|la\s+remorque|panneau|remorque)?\s*#?([1-5]\d{2})\b", lower)
        if pin_match and not is_campaign_msg:
            pid = pin_match.group(1)
            return {
                "intent": "refine_campaign",
                "refinement_action": "pin_panel",
                "is_regeneration": False,
                "pinned_panel_ids": [pid],
                "excluded_panel_ids": [],
                "client_name": client_fast,
                "target_id": pid,
                "locations": [],
                "axes": [],
                "target_periods": [],
                "province": None,
                "direction": None,
                "sector": None,
                "contexte_pref": None,
                "count_requested": 5,
                "is_admin": is_admin,
            }

        # Fast-path Ajout d'une ou plusieurs faces au plan en cours (ex: "ajoute une face chaque mois près d'éghezee", "ajoute 1 face à Eghezée", "ajoute 2 faces")
        add_face_match = re.search(r"(?:ajoute|ajouter|mets|mettre|prévois|rajoute|rajouter)\s+(?:une|un|1|2|3|deux|trois|\d+)?\s*(?:autre\s+)?(?:face|faces|panneau|panneaux|remorque|remorques)\b", lower)
        if add_face_match:
            delta = 1
            if any(w in lower for w in ["2 faces", "deux faces", "2 remorques", "2 panneaux"]):
                delta = 2
            elif any(w in lower for w in ["3 faces", "trois faces", "3 remorques", "3 panneaux"]):
                delta = 3

            target_locs = []
            loc_match = re.search(r"(?:près|proche|autour|à|vers|sur)\s+(?:d'|de\s+)?([A-Za-z0-9À-ÿ\s'-]+?)(?:\s+(?:chaque\s+mois|par\s+mois|en|\.|\?|$)|$)", lower)
            if loc_match:
                cand = loc_match.group(1).strip().title()
                if len(cand) >= 3 and cand.lower() not in ["chaque", "mois", "face", "remorque", "panneau", "mon", "ma", "notre"]:
                    target_locs.append(cand)

            for city in ["namur", "wavre", "nivelles", "ottignies", "liège", "charleroi", "mons", "gembloux", "perwez", "jodoigne", "ciney", "dinant", "éghezée", "eghezee", "andenne", "marche", "hamois"]:
                if city in lower:
                    c_clean = "Éghezée" if "eghez" in city else city.capitalize()
                    if c_clean not in target_locs:
                        target_locs.append(c_clean)

            return {
                "intent": "refine_campaign",
                "refinement_action": "add_face",
                "delta_count": delta,
                "is_regeneration": False,
                "pinned_panel_ids": [],
                "excluded_panel_ids": [],
                "client_name": client_fast,
                "target_id": None,
                "locations": target_locs,
                "axes": [],
                "target_periods": [],
                "province": None,
                "direction": None,
                "sector": None,
                "contexte_pref": None,
                "count_requested": delta,
                "is_admin": is_admin,
            }

        # Fast-path Exclusion / Retrait d'un panneau (ex: "pas la 323", "enlève le 323", "sans la 323", "retire le 323")
        excl_match = re.search(r"(?:pas|enlève|enleve|sans|retire|supprime)\s+(?:la|le|le\s+panneau|la\s+remorque|panneau|remorque)?\s*#?([1-5]\d{2})\b", lower)
        if excl_match:
            pid = excl_match.group(1)
            return {
                "intent": "refine_campaign",
                "refinement_action": "exclude_panel",
                "is_regeneration": False,
                "pinned_panel_ids": [],
                "excluded_panel_ids": [pid],
                "client_name": client_fast,
                "target_id": pid,
                "locations": [],
                "axes": [],
                "target_periods": [],
                "province": None,
                "direction": None,
                "sector": None,
                "contexte_pref": None,
                "count_requested": 5,
                "is_admin": is_admin,
            }

        # Fast-path Élargissement géographique vers une commune (ex: "élargis vers wavre", "étends vers wavre", "ajoute wavre", "et à wavre ?")
        expand_match = re.search(r"(?:élargis|elargis|étends|etends|ajoute|regarde\s+aussi|cherche\s+aussi)\s+(?:vers|à|a|sur|la\s+zone\s+de\s+|la\s+zone\s+)?([A-Za-z0-9À-ÿ\s'-]+)", lower)
        if not expand_match and re.match(r"^et\s+(?:à|a|vers|sur)\s+([A-Za-z0-9À-ÿ\s'-]+)", lower):
            expand_match = re.search(r"^et\s+(?:à|a|vers|sur)\s+([A-Za-z0-9À-ÿ\s'-]+)", lower)
        if expand_match:
            exp_loc = expand_match.group(1).strip().strip("?.,!").title()
            is_km = bool(re.search(r"\b\d+\s*km\b", exp_loc.lower())) or "km" in exp_loc.lower()
            is_generic_expand = is_km or exp_loc.lower() in ["zone", "la zone", "alentours", "les alentours", "peripherie", "périphérie", "la périphérie", "communes voisines", "le secteur"]
            exp_locs = [] if is_generic_expand else ([exp_loc] if (exp_loc and len(exp_loc) >= 3 and not any(w in exp_loc.lower() for w in ["mois", "face", "panneau", "remorque", "client", "km"])) else [])
            if is_generic_expand or exp_locs:
                return {
                    "intent": "refine_campaign",
                    "refinement_action": "expand_zone",
                    "is_regeneration": False,
                    "pinned_panel_ids": [],
                    "excluded_panel_ids": [],
                    "client_name": client_fast,
                    "target_id": None,
                    "locations": exp_locs,
                    "axes": [],
                    "target_periods": [],
                    "province": None,
                    "direction": None,
                    "sector": None,
                    "contexte_pref": None,
                    "count_requested": 5,
                    "is_admin": is_admin,
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

        history_context = ""
        if conversation_history:
            turns = []
            for h in conversation_history[-6:]:
                role = "Utilisateur" if h.get("role") == "user" else "Assistant M Move"
                t = h.get("text") or (h.get("parts")[0].get("text") if h.get("parts") else "")
                if t:
                    turns.append(f"{role}: {t[:250]}")
            if turns:
                history_context = "HISTORIQUE RÉCENT DES ÉCHANGES :\n" + "\n".join(turns) + "\n\n"

        prompt_text = f"{history_context}Dernier message de l'utilisateur : \"{user_message}\""
        if active_context:
            prompt_text += f"\nContexte actif de la sélection / campagne : {json.dumps(active_context, ensure_ascii=False)}"

        payload = {
            "system_instruction": {
                "parts": [{"text": EXTRACTION_SYSTEM_PROMPT}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt_text}]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
                "maxOutputTokens": 600,
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
                    if "is_referring_to_active_client" not in extracted:
                        extracted["is_referring_to_active_client"] = is_referring_to_active_client
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
            if len(candidate_poi) >= 3 and candidate_poi.lower() not in ["namur", "wavre", "panneau", "remorque", "moi", "vous", "nous", "zone", "alentours", "peripherie", "périphérie", "communes", "secteur", "selection", "sélection"]:
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

        count = None
        c_match = re.search(r"(\d+)\s*(?:panneaux|panneau|remorques|remorque|faces|face|emplacements|emplacement|spots|spot)", lower)
        if c_match:
            try:
                count = int(c_match.group(1))
            except ValueError:
                pass

        # Détection des intentions
        is_referring_to_active_client = bool(re.search(
            r"\b(pour lui|pour elle|pour ce client|pour cette cliente|pour l'annonceur|pour cet annonceur|son activit[ée]|sa zone|ses besoins)\b",
            lower
        ))
        dialogue_triggers = [
            "pris en compte l'annonceur", "pris en compte le client", "tenu compte de l'annonceur", "tenu compte du client",
            "pris en compte son", "tenu compte de son", "pris en compte ce client", "tenu compte de ce client",
            "adapté à son activité", "adapte a son activite", "adapté pour lui", "adapte pour lui",
            "adapté pour elle", "adapte pour elle", "adapté à ce client", "adapte a ce client",
            "pourquoi me proposer tout", "pourquoi proposer tout", "pourquoi toute la wallonie",
            "pourquoi me proposer ces faces", "pourquoi proposer toutes ces faces", "pourquoi toutes ces faces",
            "pourquoi ces faces", "pourquoi ces remorques", "pourquoi ces panneaux", "pourquoi autant de faces",
            "pourquoi ces choix", "pourquoi ce choix",
            "qui est l'annonceur", "qui est le client", "quel est le client", "quel est l'annonceur",
            "que sais-tu sur", "que sait-on sur", "connais-tu ce client", "quel est son secteur",
            "que dit l'agent", "que propose l'agent", "comment travaillent tes agents", "qui sont tes agents",
            "comment est composé ton équipe", "comment est compose ton equipe",
            "que me conseilles-tu", "qu'est-ce que tu me conseilles", "que conseilles-tu",
            "comment on procède", "comment procéder", "qu'est-ce qu'on fait maintenant", "quelle est la suite", "quelle est la prochaine étape",
            "comment tu sélectionnes", "comment tu choisis", "comment sont calculés", "comment tu calcules"
        ]
        is_direct_dialogue = any(t in lower for t in dialogue_triggers)
        is_meta_question = bool(re.search(
            r"^(as[- ]tu|est[- ]ce que tu|tu as (pensé|pris|vérifié|tenu)|pourquoi (as[- ]tu|tu as|avoir)|peux[- ]tu m['’]expliquer|qu['’]en penses[- ]tu)\b",
            lower
        )) and not any(w in lower for w in ["libre", "dispo", "quand", "#"])
        is_general_salutation = bool(re.match(r"^(bonjour|bonsoir|salut|hello|coucou|merci|merci beaucoup|c'est parfait|parfait merci|super merci|qui es[- ]tu|présente[- ]toi)[ !.?]*$", lower))

        is_dispo = any(k in lower for k in ["dispo", "dispos", "disponibilit", "libre", "libres", "quand", "prochain", "prochaine", "prochaines", "date", "dates"])
        is_explicit_campaign = (
            any(k in lower for k in ["campagne", "plan média", "plan media", "pack", "selection de campagne", "sélection de campagne"])
            or ("face" in lower and count is not None and count > 1 and not is_dispo)
        )

        # Détection des sélections ou validations de remorques
        pin_triggers = [
            "retient", "retiens", "retenir", "prend", "prends", "prendre", "choisit", "choisis", "choisir",
            "sélectionne", "selectionne", "sélectionner", "selectionner", "garde", "gardons", "garder",
            "valide", "validons", "valider", "ok pour", "go pour", "on part sur", "part sur", "retenu", "retenue",
            "conserve", "conservons", "retenons"
        ]
        exclude_triggers = [
            "sans", "enlève", "enleve", "enlever", "retire", "retirer", "supprime", "supprimer",
            "pas la", "pas le", "pas les", "refuse", "rejette"
        ]

        has_pin_trigger = any(t in lower for t in pin_triggers)
        has_exclude_trigger = any(t in lower for t in exclude_triggers)

        # Extraction des identifiants numériques de remorques (2 ou 3 chiffres, ex: 108, 309, 310)
        found_ids = []
        # 1. Préfixes explicites (#, n°, remorque, panneau, face, la, le)
        for m in re.finditer(r"(?:#|n°|no|panneau|remorque|face|la\s+|le\s+|les\s+)(\d{2,3})\b", lower):
            num = m.group(1)
            if num not in found_ids:
                found_ids.append(num)

        # 2. Si un verbe de choix ou rejet est présent, capturer tous les nombres 2-3 chiffres dans la phrase
        if has_pin_trigger or has_exclude_trigger:
            for m in re.finditer(r"\b(\d{2,3})\b", lower):
                num = m.group(1)
                if num not in found_ids and int(num) >= 10 and num not in ["20", "30", "50"]:
                    found_ids.append(num)

        client_name = extract_client_name_regex(msg)

        pinned_panel_ids = []
        excluded_panel_ids = []
        refinement_action = None
        is_regeneration = False

        is_open_consultation = False
        is_motivation_query = any(k in lower for k in [
            "motive-moi ta proposition", "motive moi ta proposition", "motive ta proposition",
            "motive-moi tes choix", "motive moi tes choix", "motive tes choix", "motive cette proposition",
            "motive-moi", "motive moi", "motive ta", "motive tes", "motive",
            "pourquoi ce choix", "pourquoi ces choix", "pourquoi cette proposition",
            "pourquoi ces panneaux", "pourquoi ces remorques", "pourquoi ces faces", "pourquoi ces emplacements",
            "pourquoi ceux-là", "pourquoi ceux la", "pourquoi ceux ci", "pourquoi ceux-ci",
            "justifie ton choix", "justifie tes choix", "justifie ta proposition", "justifie cette sélection",
            "explique-moi tes choix", "explique moi tes choix", "explique tes choix", "explique ton choix",
            "explique-moi ta sélection", "explique moi ta sélection", "explique ta sélection",
            "explique cette sélection", "explique cette proposition", "explique la proposition",
            "argumente ta sélection", "argumente ta proposition", "peux-tu argumenter", "peux tu argumenter",
            "quelle est la logique", "pourquoi avoir choisi", "qu'est-ce qui motive", "qu est ce qui motive"
        ])

        if is_motivation_query:
            intent = "motivate_proposal"
        elif client_name and any(w in lower for w in [
            "que proposerais-tu", "que proposes-tu", "tu conseilles", "tu recommandes",
            "quelle recommandation", "quelle stratégie", "qu'est-ce qu'on", "fais-moi une proposition",
            "une idée", "que penses-tu", "tu en penses quoi"
        ]):
            is_open_consultation = True
            intent = "campaign_proposal"
            if count is None:
                count = 5
        elif is_explicit_campaign:
            intent = "campaign_proposal"
            if count is None:
                count = 5
            if has_exclude_trigger and found_ids:
                excluded_panel_ids = found_ids
            if has_pin_trigger and found_ids:
                pinned_panel_ids = found_ids
        elif has_exclude_trigger and found_ids:
            excluded_panel_ids = found_ids
            refinement_action = "exclude_panel"
            intent = "refine_campaign"
        elif has_pin_trigger and found_ids:
            pinned_panel_ids = found_ids
            refinement_action = "pin_panel"
            intent = "refine_campaign"
        elif any(k in lower for k in ["élargis", "elargis", "élargir", "elargir", "alentours", "périphérie", "peripherie", "communes voisines", "ajoute", "ajouter", "regarde aussi"]):
            refinement_action = "expand_zone"
            intent = "check_availability" if is_dispo else "refine_campaign"
        elif any(k in lower for k in ["refais", "actualise", "régénère", "regenere", "mets à jour", "met a jour", "recalcule"]):
            is_regeneration = True
            intent = "campaign_proposal"
        elif is_dispo and not any(k in lower for k in ["campagne", "plan média", "plan media"]):
            intent = "check_availability"
        elif is_direct_dialogue or is_meta_question:
            intent = "coordinator_dialogue"
        elif is_general_salutation:
            intent = "general_chat"
        elif client_name and not locations and not periods and not axes and len(msg.strip().split()) <= 6:
            intent = "set_client_name"
        elif is_dispo:
            intent = "check_availability"
        else:
            intent = "search_panels"

        target_id = found_ids[0] if (len(found_ids) == 1 and not pinned_panel_ids and not excluded_panel_ids) else None

        return {
            "intent": intent,
            "is_referring_to_active_client": is_referring_to_active_client,
            "is_open_consultation": is_open_consultation,
            "refinement_action": refinement_action,
            "is_regeneration": is_regeneration,
            "pinned_panel_ids": pinned_panel_ids,
            "excluded_panel_ids": excluded_panel_ids,
            "client_name": client_name,
            "target_id": target_id,
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
